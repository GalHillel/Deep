import pytest
import asyncio
import os
import tempfile
import struct
import zlib
from pathlib import Path
from deep.network.daemon import DeepGitDaemon
from deep.network.protocol import AsyncPktLineStream
from deep.core.repository import DEEP_GIT_DIR

@pytest.fixture
def repo_with_daemon(tmp_path, monkeypatch):
    dg_dir = tmp_path / DEEP_GIT_DIR
    dg_dir.mkdir(parents=True, exist_ok=True)
    (dg_dir / "objects").mkdir(parents=True, exist_ok=True)
    (dg_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (dg_dir / "tmp").mkdir(parents=True, exist_ok=True)
    (dg_dir / "HEAD").write_text("ref: refs/heads/main\n")
    
    # Mock permissions to allow testing handle_push
    from deep.core.access import AccessManager
    monkeypatch.setattr(AccessManager, "has_permission", lambda self, user, perm: True)

    daemon = DeepGitDaemon(tmp_path, port=0) # port 0 for random port
    return daemon, tmp_path

async def connect_to_daemon(daemon):
    server = await asyncio.start_server(daemon.handle_client, '127.0.0.1', 0)
    addr = server.sockets[0].getsockname()
    
    reader, writer = await asyncio.open_connection(addr[0], addr[1])
    stream = AsyncPktLineStream(reader, writer)
    
    # Read greeting
    await stream.read_pkt() # v1
    await stream.read_pkt() # capabilities
    
    return stream, server

async def read_pkt_robust(stream: AsyncPktLineStream) -> bytes:
    """Read packets until a non-flush packet is found."""
    while True:
        pkt = await stream.read_pkt()
        if pkt is not None:
            return pkt

@pytest.mark.anyio
async def test_push_arity_validation(repo_with_daemon):
    daemon, _ = repo_with_daemon
    stream, server = await connect_to_daemon(daemon)
    
    # Send malformed push (too few args)
    await stream.write(b"push refs/heads/main")
    await stream.flush()
    
    resp = await read_pkt_robust(stream)
    assert b"error invalid push arguments" in resp
    
    server.close()
    await server.wait_closed()

@pytest.mark.anyio
async def test_max_pack_size_limit(repo_with_daemon):
    daemon, _ = repo_with_daemon
    stream, server = await connect_to_daemon(daemon)
    
    # 1. Start push
    await stream.write(b"push refs/heads/main 0000 1111")
    await stream.flush()
    
    # 2. Send oversized pack header
    oversized = daemon.MAX_PACK_SIZE + 1024
    await stream.write(f"packfile {oversized}".encode("ascii"))
    await stream.flush()
    
    resp = await read_pkt_robust(stream)
    assert b"error packfile too large" in resp
    
    server.close()
    await server.wait_closed()

@pytest.mark.anyio
async def test_sanitized_error_handling(repo_with_daemon):
    daemon, _ = repo_with_daemon
    stream, server = await connect_to_daemon(daemon)
    
    # Trigger an internal error by sending something that causes a crash in a handler
    # e.g. select with missing arg
    await stream.write(b"select")
    await stream.flush()
    
    resp = await read_pkt_robust(stream)
    # Should be a clean "internal server error", not a Python traceback
    assert b"error internal server error" in resp
    
    server.close()
    await server.wait_closed()

@pytest.mark.anyio
async def test_streaming_unpack_sanity(repo_with_daemon):
    daemon, tmp_path = repo_with_daemon
    stream, server = await connect_to_daemon(daemon)
    
    # Create a small valid pack
    # Header: PACK, v1, 1 object
    # Obj: blob "hello"
    content = b"blob 5\x00hello"
    comp = zlib.compress(content)
    # entry: type 1 (blob), size
    entry_header = struct.pack(">BQ", 1, len(comp))
    
    body = bytearray()
    body.extend(b"PACK")
    body.extend(struct.pack(">I", 1)) # v1
    body.extend(struct.pack(">I", 1)) # 1 obj
    body.extend(entry_header)
    body.extend(comp)
    
    import hashlib
    trailer = hashlib.sha1(body).digest()
    body.extend(trailer)
    
    new_sha = hashlib.sha1(content).hexdigest()
    
    # Send push
    await stream.write(f"push refs/heads/main {'0'*40} {new_sha}".encode("ascii"))
    await stream.flush()
    
    await stream.write(f"packfile {len(body)}".encode("ascii"))
    # DO NOT flush here, it adds 0000 to the stream which handle_push will read as body start
    
    # Stream the body
    stream.writer.write(body)
    await stream.writer.drain()
    
    resp = await read_pkt_robust(stream)
    assert b"ok push successful" in resp
    
    # Verify object exists
    dg_dir = tmp_path / DEEP_GIT_DIR
    assert (dg_dir / "objects" / new_sha[:2] / new_sha[2:]).exists()
    
    server.close()
    await server.wait_closed()

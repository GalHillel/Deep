import pytest
import subprocess
import sys
import os
import time
import socket
import struct
import zlib
import hashlib
from pathlib import Path

from deep.network.protocol import encode_pkt
from deep.core.repository import DEEP_GIT_DIR

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture
def repo_with_subprocess_daemon(tmp_path):
    dg_dir = tmp_path / DEEP_GIT_DIR
    dg_dir.mkdir(parents=True, exist_ok=True)
    (dg_dir / "objects").mkdir(parents=True, exist_ok=True)
    (dg_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (dg_dir / "tmp").mkdir(parents=True, exist_ok=True)
    (dg_dir / "HEAD").write_text("ref: refs/heads/main\n")
    
    port = get_free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["PYTHONUNBUFFERED"] = "1"
    env["DEEP_INSECURE_SKIP_AUTH"] = "1"
    
    proc = subprocess.Popen(
        [sys.executable, "-m", "deep.main", "daemon", "--port", str(port)],
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(1.5) # Give it plenty of time on Windows
    
    yield port, tmp_path
    
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

def communicate(port, commands: list[bytes]) -> list[bytes]:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        # Consume greeting (v1 + capabilities + flush)
        s.recv(4096) 
        
        for cmd in commands:
            if cmd == b"0000":
                s.sendall(b"0000")
            else:
                s.sendall(encode_pkt(cmd))
        
        data = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk: break
                data += chunk
        except socket.timeout:
            pass
        return [data]

def test_push_arity_validation(repo_with_subprocess_daemon):
    port, _ = repo_with_subprocess_daemon
    resps = communicate(port, [b"push refs/heads/main", b"0000"])
    assert any(b"error invalid push arguments" in r for r in resps)

def test_max_pack_size_limit(repo_with_subprocess_daemon):
    port, _ = repo_with_subprocess_daemon
    from deep.network.daemon import DeepGitDaemon
    oversized = DeepGitDaemon.MAX_PACK_SIZE + 1024
    resps = communicate(port, [
        b"push refs/heads/main 0000 1111",
        b"0000",
        f"packfile {oversized}".encode("ascii")
    ])
    assert any(b"error packfile too large" in r for r in resps)

def test_sanitized_error_handling(repo_with_subprocess_daemon):
    port, _ = repo_with_subprocess_daemon
    resps = communicate(port, [b"select", b"0000"])
    assert any(b"error internal server error" in r for r in resps)

def test_streaming_unpack_sanity(repo_with_subprocess_daemon):
    port, tmp_path = repo_with_subprocess_daemon
    
    content = b"blob 5\x00hello"
    comp = zlib.compress(content)
    entry_header = struct.pack(">BQ", 1, len(comp))
    
    body = bytearray()
    body.extend(b"PACK")
    body.extend(struct.pack(">I", 1)) # v1
    body.extend(struct.pack(">I", 1)) # 1 obj
    body.extend(entry_header)
    body.extend(comp)
    body.extend(hashlib.sha1(body).digest())
    
    new_sha = hashlib.sha1(content).hexdigest()
    
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.recv(4096) # handshake
        
        # 1. Send push
        s.sendall(encode_pkt(f"push refs/heads/main {'0'*40} {new_sha}".encode("ascii")))
        
        # 2. Send packfile header
        s.sendall(encode_pkt(f"packfile {len(body)}".encode("ascii")))
        
        # 3. Stream body
        s.sendall(body)
        
        # 4. Read response
        s.settimeout(5)
        resp = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk: break
                resp += chunk
        except socket.timeout:
            pass
            
        assert b"ok push successful" in resp
    
    # Verify object exists
    dg_dir = tmp_path / DEEP_GIT_DIR
    assert (dg_dir / "objects" / new_sha[:2] / new_sha[2:]).exists()

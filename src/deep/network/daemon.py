"""
deep.network.daemon
~~~~~~~~~~~~~~~~~~~~~~~
DeepBridge Distributed Daemon using asyncio.

Handles push/fetch requests via PKT-LINE and packfiles.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from deep.storage.objects import (
    read_object,
    Commit,
    Tree,
    get_reachable_objects,
)
from deep.storage.pack import unpack, create_pack
from deep.core.refs import update_branch, resolve_head, list_branches, get_branch
from deep.core.constants import DEEP_DIR
from deep.network.protocol import AsyncPktLineStream, AsyncSidebandStream, BAND_DATA, BAND_PROGRESS, BAND_ERROR


class DeepGitDaemon:
    """Async TCP server for DeepBridge remote operations."""

    def __init__(self, repo_root: Path, host: str = "0.0.0.0", port: int = 8888):
        self.repo_root = repo_root
        self.dg_dir = repo_root / DEEP_DIR
        self.host = host
        self.port = port
        self.server: Optional[asyncio.AbstractServer] = None

    async def start(self):
        """Start the TCP server."""
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        addr = self.server.sockets[0].getsockname()
        print(f"DeepGit Daemon listening on {addr}")
        try:
            async with self.server:
                await self.server.serve_forever()
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        except Exception as e:
            # On Windows, shutdown can cause noisy AttributeError/RuntimeError in asyncio internals
            if "NoneType" not in str(e) and "stopped" not in str(e):
                raise

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle an incoming client connection."""
        addr = writer.get_extra_info('peername')
        stream = AsyncPktLineStream(reader, writer)
        try:
            # 1. Handshake
            await stream.write(b"deep v1")
            await stream.write(b"capabilities: push fetch packfile-v1 auth select sideband-v2")
            await stream.flush()

            # 2. Auth & Protocol Stage
            current_user = "anonymous"
            dg_dir = self.dg_dir # Default
            
            from deep.core.user import UserManager
            from deep.core.access import AccessManager
            user_manager = UserManager(self.dg_dir) # Use root dg_dir for user storage
            
            # command_loop
            while True:
                line = await stream.read_pkt()
                if line is None: # Flush packet
                    continue
                if not line: # Empty packet or EOF (IncompleteReadError will be raised for real EOF)
                    continue
                
                parts = line.decode("ascii").split()
                if not parts: continue
                cmd = parts[0]
                
                if cmd == "select":
                    repo_name = parts[1]
                    # platform support
                    repos_base = (self.repo_root / "repos").resolve()
                    platform_repo = (repos_base / repo_name / DEEP_DIR).resolve()
                    try:
                        platform_repo.relative_to(repos_base)
                    except ValueError:
                        await stream.write(f"error invalid repo path: {repo_name}".encode("ascii"))
                        await stream.flush()
                        continue
                        
                    if platform_repo.exists():
                        dg_dir = platform_repo
                        await stream.write(f"ok selected: {repo_name}".encode("ascii"))
                    else:
                        await stream.write(f"error repo not found: {repo_name}".encode("ascii"))
                    await stream.flush()
                
                elif cmd == "auth":
                    token = parts[1]
                    user = user_manager.authenticate_token(token)
                    if user:
                        current_user = user.username
                        await stream.write(f"ok authenticated as: {current_user}".encode("ascii"))
                    else:
                        await stream.write(b"error invalid token")
                    await stream.flush()
                
                elif cmd == "push":
                    # Check write permission
                    access = AccessManager(dg_dir)
                    if not access.has_permission(current_user, "write"):
                        await stream.write(f"error permission denied for {current_user}".encode("ascii"))
                        await stream.flush()
                        # To avoid stream desync, we must close the connection on push permission error
                        # as we don't want to consume a potentially huge packfile.
                        break
                    await self.handle_push(stream, dg_dir, parts[1:])
                
                elif cmd == "fetch":
                    # Check read permission
                    access = AccessManager(dg_dir)
                    if not access.has_permission(current_user, "read"):
                        await stream.write(f"error permission denied for {current_user}".encode("ascii"))
                        await stream.flush()
                        continue
                    await self.handle_fetch(stream, dg_dir, parts[1:])
                
                elif cmd == "ls-refs":
                    await self.handle_ls_refs(stream, dg_dir, parts[1:])
                
                elif cmd == "quit":
                    break
                else:
                    await stream.write(f"error unknown command: {cmd}".encode("ascii"))
                    await stream.flush()

        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionAbortedError, OSError, asyncio.TimeoutError) as e:
            # Handle common network errors gracefully, especially WinError 64 on Windows
            if isinstance(e, OSError) and getattr(e, "winerror", None) != 64:
                print(f"Daemon Network Error: {e}", file=sys.stderr)
            # Treat as clean disconnect
        except Exception as e:
            # Clean error response for client, full trace for server logs
            import traceback
            print(f"Daemon Error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            try:
                if not writer.is_closing():
                    await stream.write(f"error internal server error".encode("ascii"))
                    await stream.flush()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                # Ignore errors during final closure
                pass

    MAX_PACK_SIZE = 500 * 1024 * 1024 # 500MB Limit

    async def handle_push(self, stream: AsyncPktLineStream, dg_dir: Path, args: list[str]):
        """Handle a push request: updates and packfile."""
        if len(args) < 3:
            await stream.write(b"error invalid push arguments: missing ref, old_sha, or new_sha")
            await stream.flush()
            return

        ref_name, old_sha, new_sha = args[0], args[1], args[2]
        
        # 1. Expect packfile header (may follow a flush from some clients)
        next_pkt = await stream.read_pkt()
        while next_pkt is None: # Consume flushes
            next_pkt = await stream.read_pkt()

        if not next_pkt or not next_pkt.startswith(b"packfile "):
            await stream.write(b"error expected packfile header")
            await stream.flush()
            return
            
        try:
            pack_size = int(next_pkt[9:].decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            await stream.write(b"error malformed packfile header")
            await stream.flush()
            return

        if pack_size > self.MAX_PACK_SIZE:
            await stream.write(b"error packfile too large (max 500MB)")
            await stream.flush()
            return

        # 1. Stream pack data to temporary file
        tmp_dir = dg_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=str(tmp_dir), delete=False) as tmp_pack:
            tmp_pack_path = Path(tmp_pack.name)
            try:
                bytes_left = pack_size
                chunk_size = 64 * 1024 # 64KB
                while bytes_left > 0:
                    to_read = min(bytes_left, chunk_size)
                    chunk = await asyncio.wait_for(stream.reader.read(to_read), timeout=30.0)
                    if not chunk:
                        raise asyncio.IncompleteReadError(chunk, pack_size - bytes_left)
                    tmp_pack.write(chunk)
                    bytes_left -= len(chunk)
                    await asyncio.sleep(0.01) # Yield to event loop
                tmp_pack.flush()
                tmp_pack.close()

                # 2. Quarantine Unpack from File
                with tempfile.TemporaryDirectory(dir=str(dg_dir / "tmp")) as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    tmp_objects = tmp_path / "objects"
                    tmp_objects.mkdir()
                    
                    try:
                        with open(tmp_pack_path, "rb") as f:
                            # Run synchronous unpack in a separate thread to avoid blocking the event loop
                            await asyncio.to_thread(unpack, f, tmp_objects)
                        
                        read_object(tmp_objects, new_sha)
                        
                        # 3. Atomically move objects to main store
                        moved_count = 0
                        for xx_dir in tmp_objects.iterdir():
                            if not xx_dir.is_dir() or len(xx_dir.name) != 2:
                                continue
                            for yy_file in xx_dir.iterdir():
                                sha = xx_dir.name + yy_file.name
                                dest = dg_dir / "objects" / sha[:2] / sha[2:]
                                if not dest.exists():
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    shutil.move(str(yy_file), str(dest))
                                    moved_count += 1
                        
                        # 4. Update branch
                        branch_name = ref_name.rsplit("/", 1)[-1]
                        await asyncio.to_thread(update_branch, dg_dir, branch_name, new_sha)
                        
                        # 5. Trigger CI/CD Pipeline
                        try:
                            from deep.core.pipeline import PipelineRunner
                            import threading
                            runner = PipelineRunner(dg_dir)
                            pipeline_run = runner.create_run(new_sha)
                            if pipeline_run.jobs:
                                threading.Thread(target=runner.run_pipeline, args=(pipeline_run,), daemon=True).start()
                                msg = f"ok push successful: {moved_count} objects moved. CI run {pipeline_run.run_id} started."
                            else:
                                msg = f"ok push successful: {moved_count} objects moved. (no CI config)"
                            await stream.write(msg.encode("ascii"))
                        except Exception as ci_err:
                            await stream.write(f"ok push successful: {moved_count} objects moved. (CI trigger failed)".encode("ascii"))
                    except Exception as e:
                        await stream.write(f"error push failed: processing error".encode("ascii"))
            finally:
                if tmp_pack_path.exists():
                    tmp_pack_path.unlink()
        
        await stream.flush()

    async def handle_fetch(self, stream: AsyncPktLineStream, dg_dir: Path, args: list[str]):
        """Handle a fetch request: send missing objects."""
        if not args:
            await stream.write(b"error missing fetch sha")
            await stream.flush()
            return

        target_sha = args[0]
        max_depth = None
        filter_spec = None
        
        # Parse extra arguments
        i = 1
        while i < len(args):
            if args[i] == "--depth" and i + 1 < len(args):
                max_depth = int(args[i+1])
                i += 2
            elif args[i] == "--filter" and i + 1 < len(args):
                filter_spec = args[i+1]
                i += 2
            else:
                i += 1

        try:
            # We must send all reachable objects (commit, trees, blobs)
            if "--sideband" in args:
                sb_stream = AsyncSidebandStream(stream.reader, stream.writer)
                await sb_stream.send_progress("Counting objects...")
                shas = await asyncio.to_thread(get_reachable_objects, dg_dir / "objects", [target_sha], max_depth, filter_spec)
                await sb_stream.send_progress(f"Found {len(shas)} objects. Compressing...")
                pack_data = await asyncio.to_thread(create_pack, dg_dir / "objects", shas)
                await sb_stream.send_progress("Sending packfile...")
                await sb_stream.send_data(f"packfile {len(pack_data)}".encode("ascii"))
                await sb_stream.send_data(pack_data)
            else:
                shas = await asyncio.to_thread(get_reachable_objects, dg_dir / "objects", [target_sha], max_depth, filter_spec)
                pack_data = await asyncio.to_thread(create_pack, dg_dir / "objects", shas)
                await stream.write(f"packfile {len(pack_data)}".encode("ascii"))
                stream.writer.write(pack_data)
                await stream.writer.drain()
        except Exception as e:
            if "--sideband" in args:
                sb_stream = AsyncSidebandStream(stream.reader, stream.writer)
                await sb_stream.send_error(str(e))
            else:
                await stream.write(f"error fetch failed: {e}".encode("ascii"))
                await stream.flush()

    async def handle_ls_refs(self, stream: AsyncPktLineStream, dg_dir: Path, args: list[str]):
        """List all refs in the repository."""
        branches = list_branches(dg_dir)
        if not branches:
            # Fallback for empty repo with just HEAD
            if (dg_dir / "refs" / "heads" / "main").exists():
                branches = ["main"]
        
        for branch in branches:
            sha = get_branch(dg_dir, branch)
            if sha:
                await stream.write(f"{sha} refs/heads/{branch}".encode("ascii"))
        await stream.flush()



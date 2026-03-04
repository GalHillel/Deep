"""
deep_git.network.daemon
~~~~~~~~~~~~~~~~~~~~~~~
Deep Git Distributed Daemon using asyncio.

Handles push/fetch requests via PKT-LINE and packfiles.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from deep_git.core.objects import read_object, Commit
from deep_git.core.pack import unpack, create_pack
from deep_git.core.refs import update_branch, resolve_head, list_branches, get_branch
from deep_git.core.repository import DEEP_GIT_DIR
from deep_git.network.protocol import AsyncPktLineStream


class DeepGitDaemon:
    """Async TCP server for Deep Git remote operations."""

    def __init__(self, repo_root: Path, host: str = "127.0.0.1", port: int = 8888):
        self.repo_root = repo_root
        self.dg_dir = repo_root / DEEP_GIT_DIR
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
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle an incoming client connection."""
        addr = writer.get_extra_info('peername')
        stream = AsyncPktLineStream(reader, writer)
        try:
            # 1. Handshake
            await stream.write(b"deepgit v1")
            await stream.write(b"capabilities: push fetch packfile-v1")
            await stream.flush()

            # 2. Command Loop
            while True:
                line = await stream.read_pkt()
                if not line: # Flush or EOF
                    break
                
                cmd_parts = line.decode("ascii").split()
                if not cmd_parts:
                    continue
                
                cmd = cmd_parts[0]
                if cmd == "push":
                    await self.handle_push(stream, cmd_parts[1:])
                elif cmd == "fetch":
                    await self.handle_fetch(stream, cmd_parts[1:])
                elif cmd == "quit":
                    break
                else:
                    await stream.write(f"error unknown command: {cmd}".encode("ascii"))
                    await stream.flush()

        except Exception as e:
            # Silent failure for now, could log to file
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_push(self, stream: AsyncPktLineStream, args: list[str]):
        """Handle a push request: updates and packfile."""
        if not args:
            await stream.write(b"error missing push instructions")
            await stream.flush()
            return

        ref_name, old_sha, new_sha = args[0], args[1], args[2]
        
        next_pkt = await stream.read_pkt()
        if not next_pkt or not next_pkt.startswith(b"packfile "):
            await stream.write(b"error expected packfile")
            await stream.flush()
            return
            
        pack_size = int(next_pkt[9:].decode("ascii"))
        pack_data = await stream.reader.readexactly(pack_size)
        
        # 1. Quarantine Unpack
        with tempfile.TemporaryDirectory(dir=str(self.dg_dir)) as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_objects = tmp_path / "objects"
            tmp_objects.mkdir()
            
            try:
                unpack(pack_data, tmp_objects)
                read_object(tmp_objects, new_sha)
                
                # 3. Atomically move objects to main store
                moved_count = 0
                for xx_dir in tmp_objects.iterdir():
                    if not xx_dir.is_dir() or len(xx_dir.name) != 2:
                        continue
                    for yy_file in xx_dir.iterdir():
                        sha = xx_dir.name + yy_file.name
                        dest = self.dg_dir / "objects" / sha[:2] / sha[2:]
                        if not dest.exists():
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(yy_file), str(dest))
                            moved_count += 1
                
                # 4. Update branch
                branch_name = ref_name.rsplit("/", 1)[-1]
                update_branch(self.dg_dir, branch_name, new_sha)
                
                await stream.write(f"ok push successful: {moved_count} objects moved".encode("ascii"))
            except Exception as e:
                await stream.write(f"error push failed: {e}".encode("ascii"))
        
        await stream.flush()

    async def handle_fetch(self, stream: AsyncPktLineStream, args: list[str]):
        """Handle a fetch request: send missing objects."""
        if not args:
            await stream.write(b"error missing fetch sha")
            await stream.flush()
            return
            
        target_sha = args[0]
        try:
            pack_data = create_pack(self.dg_dir / "objects", [target_sha])
            await stream.write(f"packfile {len(pack_data)}".encode("ascii"))
            stream.writer.write(pack_data)
            await stream.writer.drain()
        except Exception as e:
            await stream.write(f"error fetch failed: {e}".encode("ascii"))
            await stream.flush()


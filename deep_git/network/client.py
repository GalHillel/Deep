"""
deep_git.network.client
~~~~~~~~~~~~~~~~~~~~~~~
Deep Git Remote Client for interacting with deepgit daemons.
"""

from __future__ import annotations

import socket
import io
from pathlib import Path
from typing import List, Optional

from deep_git.core.objects import Commit, read_object, Tree
from deep_git.core.pack import create_pack, unpack
from deep_git.network.protocol import PktLineStream, encode_pkt, decode_pkt


class RemoteClient:
    """Synchronous client for Deep Git remote operations."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.reader: Optional[io.BufferedReader] = None
        self.writer: Optional[io.BufferedWriter] = None
        self.stream: Optional[PktLineStream] = None

    def connect(self):
        """Connect to the daemon and consume handshake."""
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.reader = self.sock.makefile('rb')
        self.writer = self.sock.makefile('wb')
        self.stream = PktLineStream(self.reader, self.writer)
        
        # Consume handshake
        banner = self.stream.read_pkt()
        if not banner or b"deepgit v1" not in banner:
            raise ConnectionError(f"Unexpected server banner: {banner}")
            
        caps = self.stream.read_pkt()
        # Consume the flush-pkt that terminates the handshake/discovery phase
        flush = self.stream.read_pkt()
        if flush is not None:
             # If it wasn't a flush, we might be out of sync, but let's be lenient
             pass

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str):
        """Discovers missing objects and pushes a packfile."""
        shas_to_push = self._discover_objects(objects_dir, old_sha, new_sha)
        if not shas_to_push:
            # print("Everything up-to-date")
            return "Everything up-to-date"

        pack_data = create_pack(objects_dir, shas_to_push)
        
        # Send push command
        cmd = f"push {ref} {old_sha} {new_sha}".encode("ascii")
        self.stream.write(cmd)
        
        # Send packfile header
        header = f"packfile {len(pack_data)}".encode("ascii")
        self.stream.write(header)
        
        # Send raw pack data
        self.sock.sendall(pack_data)
        
        # Read response
        resp = self.stream.read_pkt()
        if not resp or not resp.startswith(b"ok "):
            raise RuntimeError(f"Push failed: {resp}")
            
        return resp.decode("ascii")

    def fetch(self, objects_dir: Path, target_sha: str):
        """Fetches objects for target_sha and its ancestors."""
        cmd = f"fetch {target_sha}".encode("ascii")
        self.stream.write(cmd)
        
        # Read packfile header
        header_pkt = self.stream.read_pkt()
        if not header_pkt or not header_pkt.startswith(b"packfile "):
            raise RuntimeError(f"Fetch failed: expected packfile header, got {header_pkt}")
            
        pack_size = int(header_pkt[9:].decode("ascii"))
        
        # Read raw pack data (might be multiple reads)
        pack_data = bytearray()
        while len(pack_data) < pack_size:
            chunk = self.reader.read(min(pack_size - len(pack_data), 65536))
            if not chunk:
                raise EOFError("Premature EOF during fetch packfile")
            pack_data.extend(chunk)
            
        # Extract
        count = unpack(bytes(pack_data), objects_dir)
        return count

    def _discover_objects(self, objects_dir: Path, old_sha: str, new_sha: str) -> List[str]:
        """BFS to find all objects reachable from new_sha that aren't in old_sha's history."""
        # This is a simplified version: send everything reachable from new_sha 
        # that we can't find in a (theoretical) shared base.
        # For Phase 20, we'll collect all objects for the new commits.
        
        if old_sha == new_sha:
            return []
            
        seen = set()
        queue = [new_sha]
        to_pack = []
        
        while queue:
            sha = queue.pop(0)
            if sha == old_sha or sha == "0"*40 or sha in seen:
                continue
                
            seen.add(sha)
            to_pack.append(sha)
            
            obj = read_object(objects_dir, sha)
            if isinstance(obj, Commit):
                queue.append(obj.tree_sha)
                for p in obj.parent_shas:
                    queue.append(p)
            elif isinstance(obj, Tree):
                for entry in obj.entries:
                    queue.append(entry.sha)
                    
        return to_pack

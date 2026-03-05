"""
deep.network.client
~~~~~~~~~~~~~~~~~~~~~~~
Deep Git Remote Client for interacting with deep daemons.
"""

from __future__ import annotations

import socket
import io
from pathlib import Path
from typing import List, Optional, Dict
import re
import subprocess
import shutil
import tempfile

from deep.storage.objects import Commit, read_object, Tree
from deep.storage.pack import create_pack, unpack
from deep.network.protocol import PktLineStream, encode_pkt, decode_pkt


class RemoteClient:
    """Synchronous client for Deep Git remote operations."""

    def __init__(self, url: str, auth_token: Optional[str] = None):
        self.url = url
        self.host, self.port, self.repo_name = self._parse_url(url)
        self.auth_token = auth_token
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
        if not banner or b"deep v1" not in banner:
            raise ConnectionError(f"Unexpected server banner: {banner}")
            
        caps = self.stream.read_pkt()
        # Non-flush following caps might be our Auth/Platform commands
        
        # 1. Select repository if specified in URL
        if self.repo_name:
            self.stream.write(f"select {self.repo_name}".encode("ascii"))
            resp = self.stream.read_pkt()
            if not resp or not resp.startswith(b"ok "):
                raise RuntimeError(f"Repository selection failed: {resp}")

        # 2. Authenticate if token provided
        if self.auth_token:
            self.stream.write(f"auth {self.auth_token}".encode("ascii"))
            resp = self.stream.read_pkt()
            if not resp or not resp.startswith(b"ok "):
                raise RuntimeError(f"Authentication failed: {resp}")

        # Consume handshake flush packet (0000)
        # The daemon sends: banner, chips, 0000. 
        # We must consume the flush to clear the stream for next command.
        self.stream.read_until_flush()

        # Optional begin-pkt for future version proofing
        # self.stream.write(b"begin")
        # self.stream.flush()

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

    def ls_refs(self) -> Dict[str, str]:
        """List remote refs using the ls-refs command."""
        self.stream.write(b"ls-refs")
        pkts = self.stream.read_until_flush()
        
        refs = {}
        for pkt in pkts:
            line = pkt.decode("ascii")
            if " " in line:
                sha, ref = line.split(" ", 1)
                refs[ref] = sha
        return refs

    def fetch(self, objects_dir: Path, target_sha: str, depth: int | None = None, filter_spec: str | None = None):
        """Fetches objects for target_sha and its ancestors."""
        cmd_parts = [f"fetch {target_sha}"]
        if depth is not None:
            cmd_parts.append(f"--depth {depth}")
        if filter_spec is not None:
            cmd_parts.append(f"--filter {filter_spec}")
            
        cmd = " ".join(cmd_parts).encode("ascii")
        self.stream.write(cmd)
        
        # Read packfile header
        header_pkt = self.stream.read_pkt()
        if not header_pkt or not header_pkt.startswith(b"packfile "):
            raise RuntimeError(f"Fetch failed: expected packfile header, got {header_pkt}")
            
        pack_size = int(header_pkt[9:].decode("ascii"))
        
        # Read raw pack data (might be multiple reads)
        pack_data = bytearray()
        print(f"DEBUG client: expecting to read {pack_size} bytes")
        while len(pack_data) < pack_size:
            chunk = self.reader.read(min(pack_size - len(pack_data), 65536))
            if not chunk:
                print(f"DEBUG client: EOF at {len(pack_data)} bytes")
                raise EOFError("Premature EOF during fetch packfile")
            pack_data.extend(chunk)
            print(f"DEBUG client: read chunk of {len(chunk)} bytes. Total: {len(pack_data)}/{pack_size}")
            
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

    def _parse_url(self, url: str) -> tuple[str, int, Optional[str]]:
        """Parse host:port/repo or deep://host:port/repo URLs."""
        if url.startswith("deep://"):
            url = url[7:]
            
        repo_name = None
        if "/" in url:
            url, repo_name = url.split("/", 1)
            
        if ":" in url:
            host, port_str = url.split(":", 1)
            return host, int(port_str), repo_name
        
        # Default port
        return url, 8888, repo_name

class GitBridge:
    """Bridge to standard Git remotes using the 'git' CLI."""
    def __init__(self, url: str):
        self.url = url

    def connect(self):
        """No-op for bridge."""
        pass

    def disconnect(self):
        """No-op for bridge."""
        pass

    def ls_refs(self) -> Dict[str, str]:
        """Use 'git ls-remote' to discover refs."""
        try:
            result = subprocess.run(["git", "ls-remote", self.url], 
                                   capture_output=True, text=True, check=True)
            refs = {}
            for line in result.stdout.splitlines():
                if not line: continue
                sha, ref = line.split(None, 1)
                refs[ref] = sha
            return refs
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git ls-remote failed: {e.stderr}")

    def fetch(self, objects_dir: Path, target_sha: str, depth: int | None = None, filter_spec: str | None = None):
        """Use 'git clone --bare' to a temp dir and import objects."""
        print(f"GitBridge: Fetching {target_sha} from {self.url}...")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                cmd = ["git", "clone", "--bare", self.url, "repo"]
                if depth:
                    cmd.extend(["--depth", str(depth)])
                if filter_spec:
                    cmd.extend(["--filter", filter_spec])
                
                subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, check=True)
                
                remote_objs = tmp_path / "repo" / "objects"
                print(f"GitBridge: Cloned to {tmp_path / 'repo'}")
                
                # Unpack the pack files in the temp repo
                pack_dir = remote_objs / "pack"
                packs = list(pack_dir.glob("*.pack"))
                print(f"GitBridge: Found {len(packs)} pack files.")
                
                # Move packs out of the way so unpack-objects doesn't skip them
                temp_pack_dir = tmp_path / "temp_packs"
                temp_pack_dir.mkdir()
                
                for p in packs:
                    moved_p = temp_pack_dir / p.name
                    shutil.move(p, moved_p)
                    print(f"GitBridge: Unpacking {moved_p.name}...")
                    subprocess.run(["git", "unpack-objects"], 
                                   input=moved_p.read_bytes(), cwd=tmp_path / "repo",
                                   capture_output=True, check=True)
                
                # Now copy loose objects to our store
                count = 0
                found_loose = list(remote_objs.glob("??/*"))
                print(f"GitBridge: Found {len(found_loose)} loose objects after unpacking.")
                
                from concurrent.futures import ThreadPoolExecutor
                def copy_worker(obj_file: Path):
                    sha = obj_file.parent.name + obj_file.name
                    dest = objects_dir / sha[:2] / sha[2:]
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(obj_file, dest)
                        return 1
                    return 0

                if found_loose:
                    max_workers = min(os.cpu_count() or 4, len(found_loose))
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        results = list(executor.map(copy_worker, found_loose))
                        count = sum(results)
                
                print(f"GitBridge: Imported {count} objects.")
                return count
            except subprocess.CalledProcessError as e:
                print(f"GitBridge Error: {e.stdout}\n{e.stderr}")
                raise RuntimeError(f"Git fetch bridge failed: {e.stderr}")

def get_remote_client(url: str, auth_token: Optional[str] = None):
    """Factory to return either RemoteClient or GitBridge based on URL."""
    if url.startswith("deep://") or (":" in url and not ("//" in url or "@" in url)):
        return RemoteClient(url, auth_token=auth_token)
    else:
        return GitBridge(url)

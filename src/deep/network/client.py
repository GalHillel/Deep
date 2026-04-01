"""
deep.network.client
~~~~~~~~~~~~~~~~~~~~~~~
Transport client for interacting with remote repositories.

Provides transport clients for native protocol operations (SSH + HTTPS)
and RemoteClient for Deep daemon connections.

All operations are pure-Python with zero external VCS dependencies.
"""

from __future__ import annotations

import os
import socket
import io
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Set, Any
from collections import deque
import re
import sys

from deep.storage.objects import Commit, read_object, Tree, Blob
from deep.storage.pack import create_pack, unpack
from deep.network.protocol import PktLineStream, SidebandStream, encode_pkt, decode_pkt, BAND_DATA, BAND_PROGRESS, BAND_ERROR


class DeepRemoteError(Exception):
    """Raised when a Deep remote operation fails."""
    pass


class RemoteClient:
    """Synchronous client for Deep daemon remote operations."""

    def __init__(self, url: str, auth_token: Optional[str] = None):
        self.url = url
        self.host, self.port, self.repo_name = self._parse_url(url)
        self.auth_token = auth_token
        self.sock: Optional[socket.socket] = None
        self.reader: Optional[io.BufferedReader] = None
        self.writer: Optional[io.BufferedWriter] = None
        self.stream: Optional[PktLineStream] = None
        self.server_caps: Set[str] = set()
        self._obj_cache: Dict[str, Any] = {}

    def _get_obj(self, objects_dir: Path, sha: str) -> Any:
        if sha not in self._obj_cache:
            self._obj_cache[sha] = read_object(objects_dir, sha)
        return self._obj_cache[sha]

    def _parse_url(self, url: str) -> tuple[str, int, Optional[str]]:
        if url.startswith("deep://"):
            url = url[7:]
            
        repo_name = None
        if "/" in url:
            url, repo_name = url.split("/", 1)
            
        if ":" in url:
            host, port_str = url.split(":", 1)
            return host, int(port_str), repo_name
        
        return url, 8888, repo_name

    def connect(self):
        """Connect to the daemon and consume handshake."""
        if self.sock:
            return
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.reader = self.sock.makefile('rb')
        self.writer = self.sock.makefile('wb')
        self.stream = PktLineStream(self.reader, self.writer)
        
        # Consume handshake
        banner = self.stream.read_pkt()
        if not banner or b"deep v1" not in banner:
            raise ConnectionError(f"Unexpected server banner: {banner}")
            
        caps_pkt = self.stream.read_pkt()
        if caps_pkt and caps_pkt.startswith(b"capabilities: "):
            cap_str = caps_pkt[14:].decode("ascii")
            self.server_caps = set(cap_str.split())

        if self.repo_name:
            self.stream.write(f"select {self.repo_name}".encode("ascii"))
            resp = self.stream.read_pkt()
            if not resp or not resp.startswith(b"ok "):
                raise RuntimeError(f"Repository selection failed: {resp}")

        if self.auth_token:
            self.stream.write(f"auth {self.auth_token}".encode("ascii"))
            resp = self.stream.read_pkt()
            if not resp or not resp.startswith(b"ok "):
                raise RuntimeError(f"Authentication failed: {resp}")

        self.stream.read_until_flush()

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def _get_obj(self, objects_dir: Path, sha: str) -> Any:
        if sha not in self._obj_cache:
            self._obj_cache[sha] = read_object(objects_dir, sha)
        return self._obj_cache[sha]

    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str):
        self.connect()
        shas_to_push = _discover_objects(objects_dir, old_sha, new_sha)
        if not shas_to_push:
            return "Everything up-to-date"

        pack_data = create_pack(objects_dir, shas_to_push)
        
        cmd = f"push {ref} {old_sha} {new_sha}".encode("ascii")
        self.stream.write(cmd)
        
        header = f"packfile {len(pack_data)}".encode("ascii")
        self.stream.write(header)
        
        self.sock.sendall(pack_data)
        
        resp = self.stream.read_pkt()
        if not resp or not resp.startswith(b"ok "):
            raise RuntimeError(f"Push failed: {resp}")
            
        return resp.decode("ascii")

    def ls_refs(self) -> Dict[str, str]:
        self.connect()
        self.stream.write(b"ls-refs")
        pkts = self.stream.read_until_flush()
        
        refs = {}
        for pkt in pkts:
            line = pkt.decode("ascii", errors="replace")
            if " " in line:
                sha, ref = line.split(" ", 1)
                refs[ref] = sha
        return refs

    def ls_remote(self) -> Dict[str, str]:
        """Alias for ls_refs for protocol parity."""
        return self.ls_refs()

    def clone(self, objects_dir: Path, depth: Optional[int] = None, filter_spec: Optional[str] = None, shallow_since: Optional[str] = None) -> tuple[dict[str, str], str]:
        """Clone a remote repository."""
        self.connect()
        try:
            refs = self.ls_refs()
            if not refs:
                return {}, "HEAD"
            
            # Simple heuristic for HEAD
            latest_sha = refs.get("HEAD", "")
            head_ref = "refs/heads/main"
            if not latest_sha:
                for r, s in refs.items():
                    if r.startswith("refs/heads/"):
                        latest_sha = s
                        head_ref = r
                        break
            
            self.fetch(objects_dir, want_shas=[latest_sha] if latest_sha else [], depth=depth, filter_spec=filter_spec, shallow_since=shallow_since)
            return refs, head_ref
        finally:
            self.disconnect()

    def fetch(self, objects_dir: Path, want_shas: Optional[List[str]] = None, have_shas: Optional[List[str]] = None, depth: Optional[int] = None, filter_spec: Optional[str] = None, shallow_since: Optional[str] = None) -> int:
        """Standardized fetch for protocol compatibility."""
        self.connect()
        try:
            if not want_shas:
                # Discover all refs and fetch them
                refs = self.ls_refs()
                target_shas = list(refs.values())
            else:
                target_shas = [want_shas] if isinstance(want_shas, str) else want_shas
            
            count = 0
            for sha in target_shas:
                if sha == "0"*40: continue
                # We reuse the existing _fetch_single (renamed from fetch)
                count += self._fetch_single(objects_dir, sha, depth=depth, filter_spec=filter_spec, shallow_since=shallow_since)
            return count
        finally:
            self.disconnect()

    def _fetch_single(self, objects_dir: Path, target_sha: str, depth: int | None = None, filter_spec: str | None = None, shallow_since: str | None = None):
        """Internal fetch for a single SHA."""
        # Previous fetch logic...
        cmd_parts = [f"fetch {target_sha}"]
        if depth is not None:
            cmd_parts.append(f"--depth {depth}")
        if shallow_since is not None:
            cmd_parts.append(f"--shallow-since {shallow_since}")
        if filter_spec is not None:
            cmd_parts.append(f"--filter {filter_spec}")
            
        use_sideband = "sideband-v2" in self.server_caps
        if use_sideband:
            cmd_parts.append("--sideband")
            
        cmd = " ".join(cmd_parts).encode("ascii")
        self.stream.write(cmd)
        
        if use_sideband:
            from deep.network.protocol import SidebandStream, BAND_DATA, BAND_PROGRESS, BAND_ERROR
            sb_stream = SidebandStream(self.reader, self.writer)
            pack_data = bytearray()
            pack_size = 0
            
            while True:
                frame = sb_stream.read_frame()
                if not frame: break
                band, payload = frame
                
                if band == BAND_PROGRESS:
                    print(f"Remote: {payload.decode('utf-8', errors='replace')}")
                elif band == BAND_ERROR:
                    raise RuntimeError(f"Server Error: {payload.decode('utf-8', errors='replace')}")
                elif band == BAND_DATA:
                    if not pack_data and payload.startswith(b"packfile "):
                        pack_size = int(payload[9:].decode("ascii"))
                        continue
                    pack_data.extend(payload)
                    if pack_size and len(pack_data) >= pack_size:
                        break
            
            if not pack_data:
                raise RuntimeError("Fetch failed: no pack data received")
            
            from deep.storage.pack import unpack
            count = unpack(bytes(pack_data), objects_dir)
            return count

        header_pkt = self.stream.read_pkt()
        if not header_pkt or not header_pkt.startswith(b"packfile "):
            raise RuntimeError(f"Fetch failed: expected packfile header, got {header_pkt}")
            
        pack_size = int(header_pkt[9:].decode("ascii"))
        
        pack_data = bytearray()
        while len(pack_data) < pack_size:
            chunk = self.reader.read(min(pack_size - len(pack_data), 65536))
            if not chunk:
                raise EOFError("Premature EOF during fetch packfile")
            pack_data.extend(chunk)
            
        from deep.storage.pack import unpack
        count = unpack(bytes(pack_data), objects_dir)
        return count

        from deep.storage.pack import unpack
        count = unpack(bytes(pack_data), objects_dir)
        return count


def _discover_objects(objects_dir: Path, old_sha: str, new_sha: str) -> List[str]:
    """Discover all objects reachable from new_sha but not from old_sha."""
    if old_sha == new_sha:
        return []
        
    seen = set()
    queue = deque([new_sha])
    to_pack = []
    
    while queue:
        sha = queue.popleft()
        if not sha or sha == old_sha or sha == "0"*40 or sha in seen:
            continue
            
        seen.add(sha)
        to_pack.append(sha)
        
        try:
            obj = read_object(objects_dir, sha)
            if isinstance(obj, Commit):
                if obj.tree_sha:
                    queue.append(obj.tree_sha)
                for p in obj.parent_shas:
                    queue.append(p)
            elif isinstance(obj, Tree):
                for entry in obj.entries:
                    queue.append(entry.sha)
        except (FileNotFoundError, ValueError):
            pass
                
    return to_pack


class LocalClient:
    """Client for local filesystem repository operations."""

    def __init__(self, path: str):
        self.repo_root = Path(path).resolve()
        self.dg_dir = self.repo_root / ".deep"
        if not self.repo_root.exists():
            raise FileNotFoundError(f"Local path does not exist: {self.repo_root}")
        if not self.dg_dir.exists():
            raise FileNotFoundError(f"Not a Deep repository (missing .deep): {self.repo_root}")

    def ls_remote(self) -> Dict[str, str]:
        from deep.core.refs import list_branches, get_branch
        branches = list_branches(self.dg_dir)
        refs = {}
        # Add all branches
        for b in list_branches(self.dg_dir):
            sha = get_branch(self.dg_dir, b)
            if sha:
                refs[f"refs/heads/{b}"] = sha
        
        # Resolve HEAD
        from deep.core.refs import resolve_head
        head_sha = resolve_head(self.dg_dir)
        if head_sha:
            refs["HEAD"] = head_sha
            
        return refs

    def clone(self, objects_dir: Path, depth: Optional[int] = None, filter_spec: Optional[str] = None, shallow_since: Optional[str] = None) -> tuple[dict[str, str], str]:
        refs = self.ls_remote()
        head_sha = refs.get("HEAD", "")
        if head_sha:
            self.fetch(objects_dir, want_shas=[head_sha], depth=depth, filter_spec=filter_spec, shallow_since=shallow_since)
        
        # Determine head_ref
        head_ref = "refs/heads/main"
        for r, s in refs.items():
            if r.startswith("refs/heads/") and s == head_sha:
                head_ref = r
                break
        
        return refs, head_ref

    def fetch(self, objects_dir: Path, want_shas: Optional[List[str]] = None, have_shas: Optional[List[str]] = None, depth: Optional[int] = None, filter_spec: Optional[str] = None, shallow_since: Optional[str] = None) -> int:
        from deep.storage.objects import get_reachable_objects
        from deep.storage.pack import create_pack, unpack
        
        if not want_shas:
            refs = self.ls_remote()
            want_shas = list(refs.values())
        
        # Get all objects from source repo
        src_objects_dir = self.dg_dir / "objects"
        reachable_shas = get_reachable_objects(src_objects_dir, want_shas, depth, filter_spec, shallow_since)
        
        # Create pack from source and unpack to destination
        pack_data = create_pack(src_objects_dir, reachable_shas)
        count = unpack(io.BytesIO(pack_data), objects_dir)
        return count

    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str) -> str:
        """Push local changes to another local repository."""
        from deep.storage.pack import create_pack, unpack
        from deep.core.refs import update_branch
        
        # 1. Prepare objects to send
        reachable_shas = _discover_objects(objects_dir, old_sha, new_sha)
        if not reachable_shas:
            return "Everything up-to-date"
            
        # 2. Pack and unpack into the target repo
        pack_data = create_pack(objects_dir, reachable_shas)
        target_objects_dir = self.dg_dir / "objects"
        unpack(io.BytesIO(pack_data), target_objects_dir)
        
        # 3. Update the ref in the target repo
        if ref.startswith("refs/heads/"):
            branch_name = ref[len("refs/heads/"):]
            from deep.core.refs import update_branch
            update_branch(self.dg_dir, branch_name, new_sha)
        elif ref.startswith("refs/tags/"):
            tag_name = ref[len("refs/tags/"):]
            from deep.core.refs import create_tag, delete_tag
            try:
                create_tag(self.dg_dir, tag_name, new_sha)
            except FileExistsError:
                # Overwrite if forced (though local client doesn't explicitly check force arg here, 
                # we can use the same logic as branch updates)
                delete_tag(self.dg_dir, tag_name)
                create_tag(self.dg_dir, tag_name, new_sha)
        return f"ok push {ref} succeeded"


def get_remote_client(url: str, auth_token: Optional[str] = None):
    """Factory to return the appropriate client for a URL."""
    if os.environ.get("DEEP_PROTOCOL_FALLBACK") == "1":
        return RemoteClient(url, auth_token=auth_token)

    is_deep = url.startswith("deep://")
    
    # Check for Windows path or Unix absolute path or existing directory
    is_local = (
        os.path.isdir(url) or 
        url.startswith("/") or 
        (len(url) > 1 and url[1] == ":" and url[2] in "/\\") or
        "\\" in url
    )
    
    if is_local:
        return LocalClient(url)

    is_classic_daemon = (
        ":" in url
        and not ("://" in url or "@" in url)
    )

    if is_deep or is_classic_daemon:
        return RemoteClient(url, auth_token=auth_token)
    else:
        from deep.network.smart_protocol import SmartTransportClient
        return SmartTransportClient(url, token=auth_token)
"""
deep.network.client
~~~~~~~~~~~~~~~~~~~~~~~
Git Transport Client for interacting with remote repositories.

Provides GitTransportClient for native Git protocol operations (SSH + HTTPS)
and RemoteClient for Deep daemon connections.

The DeepBridge (git CLI wrapper) has been REMOVED and replaced with
the pure-Python GitTransportClient.
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


class DeepBridgeError(Exception):
    """Raised when a Deep bridge operation fails."""
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
        shas_to_push = self._discover_objects(objects_dir, old_sha, new_sha)
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

    def clone(self, objects_dir: Path, depth: Optional[int] = None, filter_spec: Optional[str] = None) -> tuple[dict[str, str], str]:
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
            
            self.fetch(objects_dir, want_shas=[latest_sha] if latest_sha else [], depth=depth, filter_spec=filter_spec)
            return refs, head_ref
        finally:
            self.disconnect()

    def fetch(self, objects_dir: Path, want_shas: Optional[List[str]] = None, have_shas: Optional[List[str]] = None, depth: Optional[int] = None, filter_spec: Optional[str] = None) -> int:
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
                count += self._fetch_single(objects_dir, sha, depth=depth, filter_spec=filter_spec)
            return count
        finally:
            self.disconnect()

    def _fetch_single(self, objects_dir: Path, target_sha: str, depth: int | None = None, filter_spec: str | None = None):
        """Internal fetch for a single SHA."""
        # Previous fetch logic...
        cmd_parts = [f"fetch {target_sha}"]
        if depth is not None:
            cmd_parts.append(f"--depth {depth}")
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

    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str) -> str:
        """Standardized push for protocol compatibility."""
        self.connect()
        try:
            shas_to_push = self._discover_objects(objects_dir, old_sha, new_sha)
            if not shas_to_push:
                return "Everything up-to-date"

            from deep.storage.pack import create_pack
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
        finally:
            self.disconnect()

    def _discover_objects(self, objects_dir: Path, old_sha: str, new_sha: str) -> List[str]:
        if old_sha == new_sha:
            return []
            
        seen = set()
        queue = deque([new_sha])
        to_pack = []
        
        while queue:
            sha = queue.popleft()
            if sha == old_sha or sha == "0"*40 or sha in seen:
                continue
                
            seen.add(sha)
            to_pack.append(sha)
            
            obj = self._get_obj(objects_dir, sha)
            if isinstance(obj, Commit):
                if obj.tree_sha:
                    queue.append(obj.tree_sha)
                for p in obj.parent_shas:
                    queue.append(p)
            elif isinstance(obj, Tree):
                for entry in obj.entries:
                    queue.append(entry.sha)
                    
        return to_pack

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


def get_remote_client(url: str, auth_token: Optional[str] = None):
    """Factory to return the appropriate client for a URL."""
    if os.environ.get("DEEP_PROTOCOL_FALLBACK") == "1":
        return RemoteClient(url, auth_token=auth_token)

    is_deep = url.startswith("deep://")
    is_classic_daemon = (
        ":" in url
        and not ("://" in url or "@" in url or
                (len(url) > 1 and url[1] == ":" and url[2] in "/\\"))
    )

    if is_deep or is_classic_daemon:
        if os.environ.get("DEEP_DEBUG"):
            print(f"[DEEP_DEBUG] get_remote_client: returning RemoteClient for {url}", file=sys.stderr)
        return RemoteClient(url, auth_token=auth_token)
    else:
        if os.environ.get("DEEP_DEBUG"):
            print(f"[DEEP_DEBUG] get_remote_client: returning GitTransportClient for {url}", file=sys.stderr)
        from deep.network.git_protocol import GitTransportClient
        return GitTransportClient(url, token=auth_token)
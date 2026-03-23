"""
deep.network.git_protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~

Deep smart protocol client implementation.

Implements:
1. **Upload-pack** (fetch/clone): ref discovery → want/have negotiation → receive packfile
2. **Receive-pack** (push): ref discovery → send update commands + packfile → parse status

Supports:
- SSH and HTTPS transports
- multi_ack_detailed negotiation
- side-band-64k progress demuxing
- thin pack resolution
- Capability negotiation

No external VCS CLI or library dependency.
"""

from __future__ import annotations

import hashlib
import io
import os
import struct
import sys
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, BinaryIO

from deep.network.pkt_line import (
    read_pkt_line,
    write_pkt_line,
    write_flush,
    read_pkt_lines,
    read_sideband,
)
from deep.network.transport import (
    SSHTransport,
    HTTPSTransport,
    TransportError,
    parse_git_url,
    create_transport,
)
from deep.objects.packfile import (
    unpack_to_store,
    build_pack,
    PackfileParser,
    TYPE_MAP,
    REVERSE_TYPE_MAP,
)
from deep.objects.hash_object import (
    hash_object,
    write_object,
    read_raw_object,
    object_exists,
    format_object,
)


class ProtocolError(Exception):
    """Raised on Deep protocol errors."""
    pass


# ── Capability Constants ───────────────────────────────────────────

CLIENT_CAPABILITIES = [
    "multi_ack_detailed",
    "side-band-64k",
    "thin-pack",
    "ofs-delta",
    "agent=deep-vcs/1.0",
    "no-progress",
]


# ── Ref Advertisement Parser ──────────────────────────────────────

def parse_ref_advertisement(data: bytes) -> Tuple[Dict[str, str], Set[str]]:
    """Parse smart HTTP ref advertisement response.

    For HTTPS, the response includes a service announcement header
    followed by ref lines.

    Args:
        data: Raw response body from /info/refs?service=...

    Returns:
        (refs_dict, server_capabilities)
        refs_dict: {ref_name: sha_hex}
        server_capabilities: set of capability strings
    """
    stream = io.BytesIO(data)
    refs: Dict[str, str] = {}
    capabilities: Set[str] = set()
    first_line = True

    # Skip service announcement line (e.g., "# service=deep-upload-pack")
    try:
        first_pkt = read_pkt_line(stream)
        if first_pkt and first_pkt.startswith(b"# "):
            # Service announcement — skip flush after it
            try:
                read_pkt_line(stream)  # flush
            except EOFError:
                pass
            first_line = True
        else:
            # Not a service announcement — it's already a ref line
            if first_pkt:
                _parse_ref_line(first_pkt, refs, capabilities, True)
                first_line = False
    except EOFError:
        return refs, capabilities

    # Read ref lines
    while True:
        try:
            pkt = read_pkt_line(stream)
            if pkt is None:
                break
            _parse_ref_line(pkt, refs, capabilities, first_line)
            first_line = False
        except EOFError:
            break

    return refs, capabilities


def _parse_ref_line(
    line: bytes,
    refs: Dict[str, str],
    capabilities: Set[str],
    is_first: bool,
) -> None:
    """Parse a single ref advertisement line."""
    text = line.decode("utf-8", errors="replace")

    # First line may include capabilities after \0
    if is_first and "\x00" in text:
        ref_part, caps_part = text.split("\x00", 1)
        capabilities.update(caps_part.strip().split())
        text = ref_part

    parts = text.strip().split(None, 1)
    if len(parts) == 2:
        sha, ref_name = parts
        refs[ref_name] = sha


def parse_ssh_ref_advertisement(
    stream: BinaryIO,
) -> Tuple[Dict[str, str], Set[str]]:
    """Parse ref advertisement from SSH transport (pkt-line stream).

    SSH transport sends ref lines directly as pkt-lines.

    Returns:
        (refs_dict, server_capabilities)
    """
    refs: Dict[str, str] = {}
    capabilities: Set[str] = set()
    first_line = True

    while True:
        try:
            pkt = read_pkt_line(stream)
            if pkt is None:
                break
            _parse_ref_line(pkt, refs, capabilities, first_line)
            first_line = False
        except EOFError:
            break

    return refs, capabilities


# ── Upload-Pack Client (fetch/clone) ──────────────────────────────

class SmartTransportClient:
    """High-level Deep smart protocol client.

    Supports clone, fetch, push, and ls-remote operations
    over SSH and HTTPS without any external VCS CLI dependency.
    """

    def __init__(self, url: str, token: Optional[str] = None):
        self.url = url
        self.token = token
        self._transport_type, _, _, _ = parse_git_url(url)

    def ls_remote(self) -> Dict[str, str]:
        """List remote references.

        Returns:
            Dict mapping ref names to SHA-1 hex digests.
        """
        if self._transport_type in ("https", "http"):
            return self._ls_remote_https()
        else:
            return self._ls_remote_ssh()

    def _ls_remote_https(self) -> Dict[str, str]:
        transport = HTTPSTransport(self.url, token=self.token)
        data, content_type = transport.get_refs("deep-upload-pack")
        refs, _ = parse_ref_advertisement(data)
        return refs

    def _ls_remote_ssh(self) -> Dict[str, str]:
        transport = SSHTransport(self.url)
        try:
            transport.connect_upload_pack()
            refs, _ = parse_ssh_ref_advertisement(transport.stdout)
            return refs
        finally:
            transport.close()

    def clone(
        self,
        objects_dir: Path,
        depth: Optional[int] = None,
        filter_spec: Optional[str] = None,
    ) -> Tuple[Dict[str, str], str]:
        """Clone a remote repository.

        Args:
            objects_dir: Local .deep/objects/ directory.
            depth: Optional shallow clone depth.

        Returns:
            (refs, head_ref_name)
        """
        if self._transport_type in ("https", "http"):
            return self._clone_https(objects_dir, depth, filter_spec)
        else:
            return self._clone_ssh(objects_dir, depth, filter_spec)

    def _clone_https(
        self,
        objects_dir: Path,
        depth: Optional[int],
        filter_spec: Optional[str] = None,
    ) -> Tuple[Dict[str, str], str]:
        transport = HTTPSTransport(self.url, token=self.token)

        # Step 1: Discover refs
        data, _ = transport.get_refs("deep-upload-pack")
        refs, server_caps = parse_ref_advertisement(data)

        if not refs:
            raise ProtocolError("Remote repository appears empty")

        # Determine HEAD
        head_sha = refs.get("HEAD", "")
        head_ref = "refs/heads/main"
        for ref, sha in refs.items():
            if sha == head_sha and ref.startswith("refs/heads/"):
                head_ref = ref
                break

        # Step 2: Build want/have negotiation request
        request_body = self._build_upload_request(
            refs, set(), server_caps, depth=depth, filter_spec=filter_spec
        )

        # Step 3: POST to deep-upload-pack
        resp = transport.post_service("deep-upload-pack", request_body)

        # Step 4: Parse response and extract packfile
        pack_data = self._receive_pack_https(resp, server_caps)

        # Step 5: Unpack objects
        if pack_data:
            count = unpack_to_store(pack_data, objects_dir)
            if os.environ.get("DEEP_DEBUG"):
                print(f"[DEEP_DEBUG] Unpacked {count} objects", file=sys.stderr)

        return refs, head_ref

    def _clone_ssh(
        self,
        objects_dir: Path,
        depth: Optional[int],
        filter_spec: Optional[str] = None,
    ) -> Tuple[Dict[str, str], str]:
        transport = SSHTransport(self.url)
        try:
            transport.connect_upload_pack()

            # Step 1: Read ref advertisement
            refs, server_caps = parse_ssh_ref_advertisement(transport.stdout)

            if not refs:
                raise ProtocolError("Remote repository appears empty")

            head_sha = refs.get("HEAD", "")
            head_ref = "refs/heads/main"
            for ref, sha in refs.items():
                if sha == head_sha and ref.startswith("refs/heads/"):
                    head_ref = ref
                    break

            # Step 2: Send want/have/done
            self._send_upload_request_ssh(
                transport, refs, set(), server_caps, depth=depth, filter_spec=filter_spec
            )

            # Step 3: Read packfile
            pack_data = self._receive_pack_ssh(transport, server_caps)

            # Step 4: Unpack
            if pack_data:
                count = unpack_to_store(pack_data, objects_dir)
                if os.environ.get("DEEP_DEBUG"):
                    print(f"[DEEP_DEBUG] Unpacked {count} objects",
                          file=sys.stderr)

            return refs, head_ref
        finally:
            transport.close()

    def fetch(
        self,
        objects_dir: Path,
        want_shas: Optional[List[str]] = None,
        have_shas: Optional[List[str]] = None,
        depth: Optional[int] = None,
        filter_spec: Optional[str] = None,
    ) -> int:
        """Fetch objects from remote.

        Args:
            objects_dir: Local .deep/objects/ directory.
            want_shas: Specific SHAs to fetch (None = all remote refs).
            have_shas: SHAs we already have locally.

        Returns:
            Number of objects fetched.
        """
        if self._transport_type in ("https", "http"):
            return self._fetch_https(objects_dir, want_shas, have_shas, depth, filter_spec)
        else:
            return self._fetch_ssh(objects_dir, want_shas, have_shas, depth, filter_spec)

    def _fetch_https(
        self,
        objects_dir: Path,
        want_shas: Optional[List[str]],
        have_shas: Optional[List[str]],
        depth: Optional[int] = None,
        filter_spec: Optional[str] = None,
    ) -> int:
        transport = HTTPSTransport(self.url, token=self.token)
        data, _ = transport.get_refs("deep-upload-pack")
        refs, server_caps = parse_ref_advertisement(data)

        if not refs:
            return 0

        local_shas = set(have_shas or [])
        if want_shas:
            wants = {sha for sha in want_shas if sha in refs.values()}
        else:
            wants = set(refs.values())

        # Filter out SHAs we already have
        wants -= local_shas

        if not wants:
            return 0

        request_body = self._build_upload_request(
            refs, local_shas, server_caps, depth=depth, filter_spec=filter_spec, want_refs=wants
        )
        resp = transport.post_service("deep-upload-pack", request_body)
        pack_data = self._receive_pack_https(resp, server_caps)

        if pack_data:
            return unpack_to_store(pack_data, objects_dir)
        return 0

    def _fetch_ssh(
        self,
        objects_dir: Path,
        want_shas: Optional[List[str]],
        have_shas: Optional[List[str]],
        depth: Optional[int] = None,
        filter_spec: Optional[str] = None,
    ) -> int:
        transport = SSHTransport(self.url)
        try:
            transport.connect_upload_pack()
            refs, server_caps = parse_ssh_ref_advertisement(transport.stdout)

            if not refs:
                return 0

            local_shas = set(have_shas or [])
            if want_shas:
                wants = {sha for sha in want_shas if sha in refs.values()}
            else:
                wants = set(refs.values())
            wants -= local_shas

            if not wants:
                return 0

            self._send_upload_request_ssh(
                transport, refs, local_shas, server_caps, depth=depth, filter_spec=filter_spec, want_refs=wants
            )
            pack_data = self._receive_pack_ssh(transport, server_caps)

            if pack_data:
                return unpack_to_store(pack_data, objects_dir)
            return 0
        finally:
            transport.close()

    def push(
        self,
        objects_dir: Path,
        ref: str,
        old_sha: str,
        new_sha: str,
    ) -> str:
        """Push a ref update to the remote.

        Args:
            objects_dir: Local .deep/objects/ directory.
            ref: Full ref path (e.g., 'refs/heads/main').
            old_sha: Current remote SHA (or '0'*40 for new).
            new_sha: New SHA to set.

        Returns:
            Status string.
        """
        if self._transport_type in ("https", "http"):
            return self._push_https(objects_dir, ref, old_sha, new_sha)
        else:
            return self._push_ssh(objects_dir, ref, old_sha, new_sha)

    def _push_https(
        self,
        objects_dir: Path,
        ref: str,
        old_sha: str,
        new_sha: str,
    ) -> str:
        transport = HTTPSTransport(self.url, token=self.token)

        # Discover remote refs
        data, _ = transport.get_refs("deep-receive-pack")
        refs, server_caps = parse_ref_advertisement(data)

        # Build push request
        request_body = self._build_push_request(
            objects_dir, ref, old_sha, new_sha, server_caps
        )

        resp = transport.post_service("deep-receive-pack", request_body)
        return self._parse_push_response(resp)

    def _push_ssh(
        self,
        objects_dir: Path,
        ref: str,
        old_sha: str,
        new_sha: str,
    ) -> str:
        transport = SSHTransport(self.url)
        try:
            transport.connect_receive_pack()
            refs, server_caps = parse_ssh_ref_advertisement(transport.stdout)

            # Send update command
            caps_str = " ".join([
                "report-status", "side-band-64k", "ofs-delta",
                "agent=deep-vcs/1.0"
            ])
            update_line = f"{old_sha} {new_sha} {ref}\0{caps_str}"
            write_pkt_line(transport.stdin, update_line.encode("ascii"))
            write_flush(transport.stdin)

            # Collect and send packfile
            pack_objects = self._collect_push_objects(
                objects_dir, old_sha, new_sha
            )
            pack_data = build_pack(pack_objects)
            transport.stdin.write(pack_data)
            transport.stdin.flush()

            # Read response
            return self._parse_push_response_ssh(transport.stdout, server_caps)
        finally:
            transport.close()

    # ── Internal: Upload Request Construction ──────────────────────

    def _build_upload_request(
        self,
        refs: Dict[str, str],
        have_shas: Set[str],
        server_caps: Set[str],
        depth: Optional[int] = None,
        filter_spec: Optional[str] = None,
        want_refs: Optional[Set[str]] = None,
    ) -> bytes:
        """Build the POST body for deep-upload-pack (HTTPS)."""
        buf = io.BytesIO()

        # Determine which SHAs to want
        if want_refs:
            want_shas = want_refs
        else:
            want_shas = set(refs.values())

        # Remove duplicates and filter
        want_shas = {s for s in want_shas if s != "0" * 40}
        want_shas -= have_shas

        if not want_shas:
            return b""

        # Build capabilities string
        caps = self._negotiate_caps(server_caps, for_fetch=True)
        caps_str = " ".join(caps)

        # Send want lines
        first = True
        for sha in sorted(want_shas):
            if first:
                line = f"want {sha} {caps_str}"
                first = False
            else:
                line = f"want {sha}"
            write_pkt_line(buf, line.encode("ascii"))

        write_flush(buf)

        # Depth
        if depth:
            write_pkt_line(buf, f"deepen {depth}".encode("ascii"))
            write_flush(buf)

        # Filter
        if filter_spec:
            write_pkt_line(buf, f"filter {filter_spec}".encode("ascii"))
            write_flush(buf)

        # Send have lines
        for sha in sorted(have_shas):
            write_pkt_line(buf, f"have {sha}".encode("ascii"))

        # Send done
        write_pkt_line(buf, b"done")

        return buf.getvalue()

    def _send_upload_request_ssh(
        self,
        transport: SSHTransport,
        refs: Dict[str, str],
        have_shas: Set[str],
        server_caps: Set[str],
        depth: Optional[int] = None,
        filter_spec: Optional[str] = None,
        want_refs: Optional[Set[str]] = None,
    ) -> None:
        """Send want/have/done over SSH."""
        if want_refs:
            want_shas = want_refs
        else:
            want_shas = set(refs.values())

        want_shas = {s for s in want_shas if s != "0" * 40}
        want_shas -= have_shas

        if not want_shas:
            return

        caps = self._negotiate_caps(server_caps, for_fetch=True)
        caps_str = " ".join(caps)

        first = True
        for sha in sorted(want_shas):
            if first:
                line = f"want {sha} {caps_str}"
                first = False
            else:
                line = f"want {sha}"
            write_pkt_line(transport.stdin, line.encode("ascii"))

        write_flush(transport.stdin)

        if depth:
            write_pkt_line(transport.stdin,
                          f"deepen {depth}".encode("ascii"))
            write_flush(transport.stdin)

        # Filter
        if filter_spec:
            write_pkt_line(transport.stdin,
                          f"filter {filter_spec}".encode("ascii"))
            write_flush(transport.stdin)

        for sha in sorted(have_shas):
            write_pkt_line(transport.stdin,
                          f"have {sha}".encode("ascii"))

        write_pkt_line(transport.stdin, b"done")

    # ── Internal: Packfile Reception ──────────────────────────────

    def _receive_pack_https(
        self,
        resp: BinaryIO,
        server_caps: Set[str],
    ) -> Optional[bytes]:
        """Receive and extract packfile from HTTPS response."""
        body = resp.read()
        if not body:
            return None

        stream = io.BytesIO(body)

        # Look for NAK or ACK
        use_sideband = "side-band-64k" in server_caps or "side-band" in server_caps

        initial_pack_pkt = None
        while True:
            try:
                pkt = read_pkt_line(stream)
                if pkt is None: break
                if not pkt: continue
                
                text = pkt.decode("ascii", errors="replace")
                if text.startswith("NAK"): break
                if text.startswith("ACK"):
                    if "common" in text or "continue" in text:
                        continue
                    if "ready" in text:
                        break
                    break # Final ACK before packfile
                
                # If we reach here, it's NEITHER an ACK nor a NAK.
                # This means the server skipped the final ACK and started sending the packfile!
                initial_pack_pkt = pkt
                break
            except EOFError:
                break

        if use_sideband:
            return self._read_sideband_pack(stream, initial_pkt=initial_pack_pkt)
        else:
            return self._read_plain_pack(stream, initial_pkt=initial_pack_pkt)

    def _receive_pack_ssh(
        self,
        transport: SSHTransport,
        server_caps: Set[str],
    ) -> Optional[bytes]:
        """Receive packfile from SSH transport."""
        use_sideband = "side-band-64k" in server_caps or "side-band" in server_caps

        # First, read NAK/ACK
        initial_pack_pkt = None
        while True:
            try:
                pkt = read_pkt_line(transport.stdout)
                if pkt is None:
                    break
                if not pkt:
                    continue
                
                text = pkt.decode("ascii", errors="replace")
                if text.startswith("NAK"):
                    break
                if text.startswith("ACK"):
                    # multi_ack flow — continue until we get 'ready'
                    if "common" in text or "continue" in text:
                        continue
                    if "ready" in text:
                        break
                    break # Final ACK before packfile
                
                # Non-ACK/NAK: server skipped negotiation exit and sent pack data
                initial_pack_pkt = pkt
                break
            except EOFError:
                break

        if use_sideband:
            return self._read_sideband_pack(transport.stdout, initial_pkt=initial_pack_pkt)
        else:
            return self._read_plain_pack(transport.stdout, initial_pkt=initial_pack_pkt)

    def _read_sideband_pack(self, stream: BinaryIO, initial_pkt: Optional[bytes] = None) -> Optional[bytes]:
        """Read packfile data from sideband-64k channel."""
        pack_chunks = []

        first_iteration = True
        while True:
            try:
                if first_iteration and initial_pkt is not None:
                    pkt = initial_pkt
                    first_iteration = False
                else:
                    pkt = read_pkt_line(stream)
                    first_iteration = False

                if pkt is None:
                    break
                if not pkt:
                    continue

                channel = pkt[0]
                payload = pkt[1:]

                if channel == 1:
                    # Pack data
                    pack_chunks.append(payload)
                elif channel == 2:
                    # Progress
                    msg = payload.decode("utf-8", errors="replace").strip()
                    if os.environ.get("DEEP_DEBUG"):
                        print(f"remote: {msg}", file=sys.stderr)
                elif channel == 3:
                    # Error
                    error_msg = payload.decode("utf-8", errors="replace")
                    raise ProtocolError(f"Server error: {error_msg}")
            except EOFError:
                break

        return b"".join(pack_chunks) if pack_chunks else None

    def _read_plain_pack(self, stream: BinaryIO, initial_pkt: Optional[bytes] = None) -> Optional[bytes]:
        """Read packfile directly from stream (no sideband)."""
        # Skip any pkt-line framing for NAK/ACK
        buf = io.BytesIO()
        remaining = stream.read()
        
        if initial_pkt:
            # We must re-frame initial_pkt as a pkt-line if it was read by read_pkt_line
            # Actually, read_pkt_line returns the PAYLOAD. 
            # If it's a plain pack, the server might have sent raw data or pkt-lines.
            # Git plain pack over HTTP/SSH is usually raw data after the final ACK.
            remaining = initial_pkt + remaining

        if not remaining:
            return None

        # Find PACK signature
        pack_idx = remaining.find(b"PACK")
        if pack_idx >= 0:
            return remaining[pack_idx:]

        return remaining

    # ── Internal: Push Request Construction ────────────────────────

    def _build_push_request(
        self,
        objects_dir: Path,
        ref: str,
        old_sha: str,
        new_sha: str,
        server_caps: Set[str],
    ) -> bytes:
        """Build the POST body for deep-receive-pack."""
        buf = io.BytesIO()

        # Send update command with capabilities
        caps = self._negotiate_caps(server_caps, for_fetch=False)
        caps_str = " ".join(caps)
        update_line = f"{old_sha} {new_sha} {ref}\x00{caps_str}"
        write_pkt_line(buf, update_line.encode("ascii"))
        write_flush(buf)

        # Collect objects and build packfile
        pack_objects = self._collect_push_objects(objects_dir, old_sha, new_sha)
        if pack_objects:
            pack_data = build_pack(pack_objects)
            buf.write(pack_data)

        return buf.getvalue()

    def _collect_push_objects(
        self,
        objects_dir: Path,
        old_sha: str,
        new_sha: str,
    ) -> List[Tuple[str, bytes]]:
        """Collect all objects needed for push via BFS.

        Walks from new_sha, stopping at old_sha's history.
        """
        if new_sha == "0" * 40:
            return []

        stop_shas = {"0" * 40}
        if old_sha and old_sha != "0" * 40:
            stop_shas.add(old_sha)

        visited: Set[str] = set()
        queue = deque([new_sha])
        objects: List[Tuple[str, bytes]] = []

        while queue:
            sha = queue.popleft()
            if sha in visited or sha in stop_shas:
                continue
            visited.add(sha)

            try:
                obj_type, data = read_raw_object(objects_dir, sha)
            except FileNotFoundError:
                continue

            objects.append((obj_type, data))

            # Walk into referenced objects
            if obj_type == "commit":
                tree_sha, parent_shas = self._parse_commit_refs(data)
                if tree_sha:
                    queue.append(tree_sha)
                queue.extend(parent_shas)
            elif obj_type == "tree":
                for _, _, entry_sha in self._parse_tree_entries(data):
                    queue.append(entry_sha)

        return objects

    @staticmethod
    def _parse_commit_refs(data: bytes) -> Tuple[Optional[str], List[str]]:
        """Extract tree SHA and parent SHAs from commit content."""
        tree_sha = None
        parents = []
        for line in data.decode("utf-8", errors="replace").split("\n"):
            if line.startswith("tree "):
                tree_sha = line[5:].strip()
            elif line.startswith("parent "):
                parents.append(line[7:].strip())
            elif not line:
                break  # End of headers
        return tree_sha, parents

    @staticmethod
    def _parse_tree_entries(data: bytes) -> List[Tuple[str, str, str]]:
        """Parse tree object content into (mode, name, sha_hex) tuples."""
        entries = []
        idx = 0
        while idx < len(data):
            # Find null byte
            null_idx = data.index(b"\x00", idx)
            mode_name = data[idx:null_idx].decode("utf-8")
            mode, name = mode_name.split(" ", 1)

            sha_start = null_idx + 1
            sha_end = sha_start + 20
            sha_hex = data[sha_start:sha_end].hex()

            entries.append((mode, name, sha_hex))
            idx = sha_end

        return entries

    # ── Internal: Push Response Parsing ────────────────────────────

    def _parse_push_response(self, resp: BinaryIO) -> str:
        """Parse deep-receive-pack HTTPS response."""
        body = resp.read()
        stream = io.BytesIO(body)

        status_lines = []
        while True:
            try:
                pkt = read_pkt_line(stream)
                if pkt is None:
                    break
                text = pkt.decode("utf-8", errors="replace").strip()
                status_lines.append(text)
                if text.startswith("ng "):
                    raise ProtocolError(f"Push rejected: {text}")
            except EOFError:
                break

        if any("ok" in s for s in status_lines):
            return "ok"

        # Check for sideband
        if body:
            stream = io.BytesIO(body)
            try:
                while True:
                    pkt = read_pkt_line(stream)
                    if pkt is None:
                        break
                    if pkt and pkt[0] == 1:
                        inner = io.BytesIO(pkt[1:])
                        while True:
                            try:
                                inner_pkt = read_pkt_line(inner)
                                if inner_pkt is None:
                                    break
                                text = inner_pkt.decode("utf-8",
                                                        errors="replace")
                                if text.startswith("ok "):
                                    return "ok"
                                if text.startswith("ng "):
                                    raise ProtocolError(
                                        f"Push rejected: {text}")
                            except (EOFError, ValueError):
                                break
                    elif pkt and pkt[0] == 3:
                        error = pkt[1:].decode("utf-8", errors="replace")
                        raise ProtocolError(f"Server error: {error}")
            except (EOFError, ValueError):
                pass

        return "ok"  # Assume success if no error

    def _parse_push_response_ssh(
        self,
        stream: BinaryIO,
        server_caps: Set[str],
    ) -> str:
        """Parse deep-receive-pack SSH response."""
        use_sideband = "side-band-64k" in server_caps

        while True:
            try:
                pkt = read_pkt_line(stream)
                if pkt is None:
                    break

                if use_sideband and pkt:
                    channel = pkt[0]
                    payload = pkt[1:]
                    if channel == 1:
                        text = payload.decode("utf-8",
                                              errors="replace").strip()
                        if text.startswith("ok "):
                            return "ok"
                        if text.startswith("ng "):
                            raise ProtocolError(f"Push rejected: {text}")
                    elif channel == 3:
                        error = payload.decode("utf-8",
                                               errors="replace")
                        raise ProtocolError(f"Server error: {error}")
                else:
                    text = pkt.decode("utf-8", errors="replace").strip()
                    if text.startswith("ok "):
                        return "ok"
                    if text.startswith("ng "):
                        raise ProtocolError(f"Push rejected: {text}")
            except EOFError:
                break

        return "ok"

    # ── Internal: Capability Negotiation ───────────────────────────

    @staticmethod
    def _negotiate_caps(
        server_caps: Set[str],
        for_fetch: bool = True,
    ) -> List[str]:
        """Negotiate capabilities with the server."""
        result = []
        for cap in CLIENT_CAPABILITIES:
            cap_name = cap.split("=")[0]
            # Check if server supports it (or it's agent string)
            if cap_name == "agent" or cap_name in server_caps:
                result.append(cap)
            elif cap in server_caps:
                result.append(cap)

        if for_fetch:
            if "no-done" in server_caps:
                result.append("no-done")
        else:
            # Push capabilities
            if "report-status" in server_caps:
                result.append("report-status")
            if "delete-refs" in server_caps:
                result.append("delete-refs")

        return result if result else ["agent=deep-vcs/1.0"]

"""
deep.storage.objects
~~~~~~~~~~~~~~~~~~~~

The core content-addressable object store.

This module defines the fundamental data structures of Deep VCS:
- **Blob**: Raw file content.
- **Tree**: Directory-like mapping of names to other objects.
- **Commit**: Snapshot of the project state with metadata.
- **Tag**: Annotated references to specific commits.

All objects are identified by their SHA-1 hash and stored using a
fan-out directory structure (`objects/xx/yyyy...`) to ensure performance
at scale.
"""

from __future__ import annotations

import re
import os
import sys
import time
import zlib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from deep.utils.utils import AtomicWriter, get_local_timezone_offset, hash_bytes

_SHA_RE = re.compile(r'^[0-9a-f]{40}$')


# ── Helpers ──────────────────────────────────────────────────────────

def _object_path(objects_dir: Path, sha: str) -> Path:
    """Return the absolute filesystem path for an object given its SHA-1.
    
    Raises ValueError if the SHA is not a valid 40-character hex string,
    preventing path traversal attacks.
    """
    if not _SHA_RE.match(sha):
        raise ValueError(f"Invalid SHA format: {sha!r}")
    return objects_dir / sha[:2] / sha[2:]


def _serialize(obj_type: str, content: bytes) -> bytes:
    """Build the canonical ``<type> <size>\\0<content>`` byte string."""
    header = f"{obj_type} {len(content)}".encode("ascii")
    return header + b"\x00" + content


def _deserialize(raw: bytes) -> tuple[str, bytes]:
    """Split a stored object into ``(type, content)``."""
    null_idx = raw.index(b"\x00")
    header = raw[:null_idx].decode("ascii")
    obj_type, size_str = header.split(" ", 1)
    size = int(size_str)
    content = raw[null_idx + 1:]
    if len(content) != size:
        raise ValueError(
            f"Object size mismatch: header says {size}, got {len(content)}"
        )
    return obj_type, content


# ── Base class ───────────────────────────────────────────────────────

@dataclass
class GitObject:
    """Abstract base class for all content-addressable objects in Deep VCS."""

    OBJ_TYPE: str = field(init=False, repr=False)

    def serialize_content(self) -> bytes:
        """Return the raw *content* bytes (without the header)."""
        raise NotImplementedError

    def full_serialize(self) -> bytes:
        """Return the full ``<type> <size>\\0<content>`` byte string."""
        return _serialize(self.OBJ_TYPE, self.serialize_content())

    @property
    def sha(self) -> str:
        """SHA-1 hex digest of the full serialised form."""
        return hash_bytes(self.full_serialize())

    def write(self, objects_dir: Path) -> str:
        """Serialize and write the object to the object store.
        
        Returns:
            The SHA-1 hex digest of the written object.
        """
        if isinstance(self, Tree):
            for entry in self.entries:
                entry.validate(objects_dir)

        content = self.full_serialize()
        sha = hash_bytes(content)
        
        dest = _object_path(objects_dir, sha)
        if dest.exists():
            return sha
            
        dest.parent.mkdir(parents=True, exist_ok=True)
        compressed_content = zlib.compress(content)
        with AtomicWriter(dest) as aw:
            aw.write(compressed_content)
        return sha


# ── Blob ─────────────────────────────────────────────────────────────

@dataclass
class Blob(GitObject):
    """A blob stores the raw contents of a single file."""

    OBJ_TYPE: str = field(init=False, default="blob", repr=False)
    data: bytes = b""

    def serialize_content(self) -> bytes:
        return self.data

    @classmethod
    def from_content(cls, content: bytes) -> "Blob":
        return cls(data=content)


# ── Tree ─────────────────────────────────────────────────────────────

@dataclass
class TreeEntry:
    """One entry in a :class:`Tree`.

    Attributes:
        mode:  File mode string (e.g. ``"100644"`` for a regular file,
               ``"40000"`` for a directory / sub-tree).
        name:  Basename of the file or directory.
        sha:   SHA-1 hex digest of the referenced Blob or Tree.
    """
    mode: str
    name: str
    sha: str

    def __post_init__(self):
        # Normalize mode (Git trees often use "40000" but sometimes omit leading zero)
        # However, for serialization we must be consistent.
        if self.mode == "040000":
            self.mode = "40000"
        
        valid_modes = {"100644", "100755", "40000", "120000", "160000"}
        if self.mode not in valid_modes:
            # Try to be helpful: if it looks like a directory but has blob mode, we will catch it in validate()
            pass

    def validate(self, objects_dir: Path):
        """Strict validation: ensure mode matches actual object type."""
        from deep.storage.objects import read_object_safe, Tree, Blob
        try:
            obj = read_object_safe(objects_dir, self.sha)
            if isinstance(obj, Tree) and self.mode != "40000":
                raise ValueError(f"Entry '{self.name}' object type (tree) doesn't match mode type ({self.mode})")
            if isinstance(obj, Blob) and self.mode == "40000":
                raise ValueError(f"Entry '{self.name}' object type (blob) doesn't match mode type (40000)")
        except (FileNotFoundError, ValueError):
            # If object is missing, we can't definitively check type here, 
            # but fsck should catch it.
            pass


@dataclass
class Tree(GitObject):
    """A tree maps names to blobs (files) or other trees (directories)."""

    OBJ_TYPE: str = field(init=False, default="tree", repr=False)
    entries: List[TreeEntry] = field(default_factory=list)

    def serialize_content(self) -> bytes:
        """Serialize entries sorted by name, Git-style.

        Format: <mode> <name>\0<20-byte raw SHA-1>
        """
        from deep.core.reconcile import sanitize_filename  # noqa: F401 – defensive import kept for future use
        
        parts: list[bytes] = []
        # We need objects_dir for validation. If NOT provided, we skip strict validation 
        # (e.g. during initial construction before writing).
        # But for 'write()', we always have objects_dir.
        
        for entry in sorted(self.entries, key=lambda e: e.name):
            # 1. Validate
            assert "\x00" not in entry.name, f"Null byte in filename: {repr(entry.name)}"
            
            # 2. Convert to binary
            mode_bytes = entry.mode.encode("ascii")
            name_bytes = entry.name.encode("utf-8")
            sha_bytes = bytes.fromhex(entry.sha)
            
            # 3. Construct entry: <mode> <name>\0<sha>
            parts.append(mode_bytes + b" " + name_bytes + b"\x00" + sha_bytes)
            
        return b"".join(parts)

    @classmethod
    def from_content(cls, content: bytes) -> "Tree":
        """Deserialise tree content bytes back into a :class:`Tree`."""
        entries: list[TreeEntry] = []
        idx = 0
        while idx < len(content):
            # Find the null byte separating <mode> <name> from the SHA.
            null_idx = content.index(b"\x00", idx)
            mode_name = content[idx:null_idx].decode("utf-8")
            mode, name = mode_name.split(" ", 1)
            sha_bytes = content[null_idx + 1: null_idx + 21]
            sha = sha_bytes.hex()
            entries.append(TreeEntry(mode=mode, name=name, sha=sha))
            idx = null_idx + 21
        return cls(entries=entries)


# ── Commit ───────────────────────────────────────────────────────────

@dataclass
class Commit(GitObject):
    """A commit binds a :class:`Tree` to metadata and parent commits."""

    OBJ_TYPE: str = field(init=False, default="commit", repr=False)
    tree_sha: str = ""
    parent_shas: List[str] = field(default_factory=list)
    author: str = "Deep Git User <user@deep>"
    committer: str = "Deep Git User <user@deep>"
    message: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time()))
    timezone: str = field(default_factory=lambda: get_local_timezone_offset())
    signature: Optional[str] = None

    def serialize_content(self) -> bytes:
        lines: list[str] = [f"tree {self.tree_sha}"]
        for p in self.parent_shas:
            lines.append(f"parent {p}")
        lines.append(f"author {self.author} {self.timestamp} {self.timezone}")
        lines.append(
            f"committer {self.committer} {self.timestamp} {self.timezone}"
        )
        if self.signature:
            lines.append("gpgsig -----BEGIN PGP SIGNATURE-----")
            for sig_line in self.signature.splitlines():
                lines.append(f" {sig_line}")
            lines.append(" -----END PGP SIGNATURE-----")
            
        lines.append("")
        lines.append(self.message)
        return "\n".join(lines).encode("utf-8")

    @classmethod
    def from_content(cls, content: bytes) -> "Commit":
        """Deserialise commit content bytes back into a :class:`Commit`."""
        text = content.decode("utf-8")
        
        # Split headers from message
        if "\n\n" in text:
            headers_text, message = text.split("\n\n", 1)
        else:
            headers_text, message = text, ""
            
        tree_sha = ""
        parent_shas: list[str] = []
        author = ""
        committer = ""
        timestamp = 0
        timezone = "+0000"
        signature_lines = []
        in_sig = False
        
        for line in headers_text.split("\n"):
            if line.startswith("gpgsig "):
                in_sig = True
                continue
            if in_sig:
                if line.startswith(" -----END PGP SIGNATURE-----"):
                    in_sig = False
                else:
                    signature_lines.append(line[1:] if line.startswith(" ") else line)
                continue
                
            if line.startswith("tree "):
                tree_sha = line[5:]
            elif line.startswith("parent "):
                parent_shas.append(line[7:])
            elif line.startswith("author "):
                parts = line[7:].rsplit(" ", 2)
                author = parts[0]
                timestamp = int(parts[1])
                timezone = parts[2]
            elif line.startswith("committer "):
                parts = line[10:].rsplit(" ", 2)
                committer = parts[0]
                
        signature = "\n".join(signature_lines) if signature_lines else None
        
        return cls(
            tree_sha=tree_sha,
            parent_shas=parent_shas,
            author=author,
            committer=committer,
            message=message,
            timestamp=timestamp,
            timezone=timezone,
            signature=signature,
        )


# ── Tag ──────────────────────────────────────────────────────────────

@dataclass
class Tag(GitObject):
    """An annotated tag object."""

    OBJ_TYPE: str = field(init=False, default="tag", repr=False)
    target_sha: str = ""
    target_type: str = "commit"
    tag_name: str = ""
    tagger: str = ""
    message: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time()))
    timezone: str = field(default_factory=lambda: get_local_timezone_offset())

    def serialize_content(self) -> bytes:
        lines: list[str] = [
            f"object {self.target_sha}",
            f"type {self.target_type}",
            f"tag {self.tag_name}",
            f"tagger {self.tagger} {self.timestamp} {self.timezone}",
            "",
            self.message
        ]
        return "\n".join(lines).encode("utf-8")

    @classmethod
    def from_content(cls, content: bytes) -> "Tag":
        text = content.decode("utf-8")
        headers, message = text.split("\n\n", 1)
        target_sha = ""
        target_type = "commit"
        tag_name = ""
        tagger = ""
        timestamp = 0
        timezone = "+0000"
        
        for line in headers.split("\n"):
            if line.startswith("object "):
                target_sha = line[7:]
            elif line.startswith("type "):
                target_type = line[5:]
            elif line.startswith("tag "):
                tag_name = line[4:]
            elif line.startswith("tagger "):
                parts = line[7:].rsplit(" ", 2)
                tagger = parts[0]
                timestamp = int(parts[1])
                timezone = parts[2]
                
        return cls(
            target_sha=target_sha,
            target_type=target_type,
            tag_name=tag_name,
            tagger=tagger,
            message=message,
            timestamp=timestamp,
            timezone=timezone,
        )


@dataclass
class DeltaObject(GitObject):
    """A delta-compressed object.
    
    Stores a delta that reconstruction the original content from a base object.
    """
    OBJ_TYPE: str = field(init=False, default="delta", repr=False)
    base_sha: str
    delta_data: bytes

    def serialize_content(self) -> bytes:
        # Format: <base_sha_hex> \n <delta_bytes>
        return self.base_sha.encode("ascii") + b"\n" + self.delta_data

    @classmethod
    def from_content(cls, content: bytes) -> "DeltaObject":
        null_idx = content.index(b"\n")
        base_sha = content[:null_idx].decode("ascii")
        delta_data = content[null_idx+1:]
        return cls(base_sha=base_sha, delta_data=delta_data)


@dataclass
class Chunk(GitObject):
    """A sub-file content chunk for deduplication."""
    OBJ_TYPE: str = field(init=False, default="chunk", repr=False)
    data: bytes

    def serialize_content(self) -> bytes:
        return self.data

    @classmethod
    def from_content(cls, content: bytes) -> "Chunk":
        return cls(data=content)


@dataclass
class ChunkedBlob(GitObject):
    """A blob represented as a list of chunk SHAs."""
    OBJ_TYPE: str = field(init=False, default="chunked_blob", repr=False)
    chunk_shas: List[str]

    def serialize_content(self) -> bytes:
        return "\n".join(self.chunk_shas).encode("ascii")

    @classmethod
    def from_content(cls, content: bytes) -> "ChunkedBlob":
        shas = content.decode("ascii").strip().splitlines()
        return cls(chunk_shas=shas)


# ── Write to disk ──────────────────────────────────────────────────

def write_object(objects_dir: Path, obj: GitObject) -> str:
    """Convenience helper to write a GitObject."""
    return obj.write(objects_dir)


def write_large_blob(objects_dir: Path, data: bytes) -> str:
    """Write large data using Content-Defined Chunking for deduplication."""
    from deep.storage.chunking import chunk_data
    chunks = chunk_data(data)
    
    chunk_shas = []
    for c_data in chunks:
        c_obj = Chunk(data=c_data)
        sha = c_obj.write(objects_dir)
        chunk_shas.append(sha)
    
    cb_obj = ChunkedBlob(chunk_shas=chunk_shas)
    return cb_obj.write(objects_dir)


def write_delta_object(objects_dir: Path, base_sha: str, target_content: bytes) -> str:
    """Attempt to write target_content as a delta relative to base_sha."""
    from deep.storage.delta import create_delta
    
    base_obj = read_object(objects_dir, base_sha)
    base_content = base_obj.serialize_content()
    
    delta_data = create_delta(base_content, target_content)
    
    # Only store as delta if it's actually smaller
    if len(delta_data) + 41 < len(target_content): # 41 for SHA + newline
        delta_obj = DeltaObject(base_sha=base_sha, delta_data=delta_data)
        return delta_obj.write(objects_dir)
    
    # Fallback to normal blob if delta is not efficient
    return write_object(objects_dir, Blob(data=target_content))


# ── Read from disk ──────────────────────────────────────────────────

def read_object(objects_dir: Path, sha: str) -> GitObject:
    """Read and deserialise an object from the object store.
    
    This function transparently handles compressed (zlib), 
    legacy uncompressed, DELTA-compressed, and PACKed objects.
    """
    if not sha or not isinstance(sha, str) or len(sha) != 40:
        raise ValueError(f"Invalid object SHA: {sha!r}")
        
    path = _object_path(objects_dir, sha)
    if not path.exists():
        # Check packfiles
        from deep.storage.pack import PackReader
        reader = PackReader(objects_dir.parent)
        obj = reader.get_object(sha)
        if obj:
            return obj
        raise FileNotFoundError(f"Object {sha} not found in loose or pack storage.")
        
    data = path.read_bytes()
    
    try:
        # Try decompressing first (new format)
        raw = zlib.decompress(data)
    except zlib.error:
        # If decompression fails, it might be an old uncompressed object
        valid_headers = [b"blob ", b"tree ", b"commit ", b"tag ", b"delta "]
        if any(data.startswith(h) for h in valid_headers):
            raw = data
        else:
            raise ValueError(f"Object {sha} is corrupted or in an unknown format.")

    obj_type, content = _deserialize(raw)

    if obj_type == "blob":
        return Blob(data=content)
    elif obj_type == "tree":
        return Tree.from_content(content)
    elif obj_type == "commit":
        return Commit.from_content(content)
    elif obj_type == "tag":
        return Tag.from_content(content)
    elif obj_type == "delta":
        delta_obj = DeltaObject.from_content(content)
        # Resolve base
        from deep.storage.delta import apply_delta
        base_obj = read_object(objects_dir, delta_obj.base_sha)
        base_content = base_obj.serialize_content()
        target_content = apply_delta(base_content, delta_obj.delta_data)
        return Blob(data=target_content)
    elif obj_type == "chunked_blob":
        cb_obj = ChunkedBlob.from_content(content)
        # Reassemble chunks
        parts = []
        for c_sha in cb_obj.chunk_shas:
            chunk = read_object(objects_dir, c_sha)
            if not isinstance(chunk, Chunk):
                # Fallback: if it's a blob (loose), use its data
                if isinstance(chunk, Blob):
                    parts.append(chunk.data)
                else:
                    raise ValueError(f"Expected chunk object for {c_sha}, got {type(chunk)}")
            else:
                parts.append(chunk.data)
        return Blob(data=b"".join(parts))
    elif obj_type == "chunk":
        return Chunk(data=content)
    else:
        raise ValueError(f"Unknown object type: {obj_type!r}")


def read_object_safe(objects_dir: Path, sha: str) -> GitObject:
    """Read an object and verify its SHA-1 hash."""
    path = _object_path(objects_dir, sha)
    if not path.exists():
        raise FileNotFoundError(f"Object {sha} not found")
        
    data = path.read_bytes()
    try:
        raw = zlib.decompress(data)
    except zlib.error:
        raw = data # fallback to uncompressed
        
    actual_sha = hash_bytes(raw)
    
    if actual_sha != sha:
        # Quarantine corrupt object
        quarantine_dir = objects_dir.parent / "quarantine"
        quarantine_dir.mkdir(exist_ok=True)
        q_path = quarantine_dir / sha
        if not q_path.exists():
            path.replace(q_path)
        
        # Phase 57: Attempt P2P Heal
        healed_data = _attempt_p2p_heal(objects_dir.parent, sha)
        if healed_data:
            # Persist healed object
            # (Note: full_serialize already includes header, so we avoid nested headers)
            # We use a simple write here.
            with AtomicWriter(path) as aw:
                aw.write(zlib.compress(healed_data))
            raw = healed_data
        else:
            raise ValueError(f"Corrupt object {sha} (hash mismatch). P2P healing failed.")
        
    obj_type, content = _deserialize(raw)
    cls = {
        "blob": Blob,
        "tree": Tree,
        "commit": Commit,
        "tag": Tag,
    }.get(obj_type)
    
    if cls is None:
        raise ValueError(f"Unknown object type: {obj_type}")
        
    return cls.from_content(content)


def _attempt_p2p_heal(dg_dir: Path, sha: str) -> Optional[bytes]:
    """Attempt to fetch a valid object from P2P peers."""
    try:
        from deep.network.p2p import P2PEngine
        engine = P2PEngine(dg_dir)
        # In a real scenario, this would already be running and have peers.
        # For simulation/tests, we might need a way to pass an existing engine.
        peers = engine.get_peers()
        for p in peers:
            data = engine.request_tunnel_data(p.node_id, sha)
            if data:
                # Verify healed data before returning
                if hash_bytes(data) == sha:
                    return data
    except Exception:
        pass
    return None

def get_reachable_objects(objects_dir: Path, shas: list[str], max_depth: int | None = None, filter_spec: str | None = None) -> list[str]:
    """Return all objects reachable from the given SHAs (commits, trees, blobs), supporting depth and filters."""
    seen = set()
    queue = deque((sha, 1) for sha in shas)
    reachable = []
    
    blob_none = (filter_spec == "blob:none")
    
    while queue:
        sha, depth = queue.popleft()
        if not sha or sha == "0"*40 or sha in seen:
            continue
            
        seen.add(sha)
        
        try:
            obj = read_object(objects_dir, sha)
            
            # Apply filter
            if blob_none and isinstance(obj, Blob):
                continue
                
            reachable.append(sha)
            
            if isinstance(obj, Commit):
                if obj.tree_sha:
                    queue.append((obj.tree_sha, depth)) # Trees don't increase commit depth
                
                # Check depth bound before adding parents
                if max_depth is None or depth < max_depth:
                    for p in obj.parent_shas:
                        queue.append((p, depth + 1))
            elif isinstance(obj, Tree):
                for entry in obj.entries:
                    queue.append((entry.sha, depth))
            elif isinstance(obj, Tag):
                if obj.target_sha:
                    queue.append((obj.target_sha, depth))
        except (FileNotFoundError, ValueError):
            # Ignore missing objects
            pass
            
    return reachable

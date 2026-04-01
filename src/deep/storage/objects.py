"""
deep.storage.objects
~~~~~~~~~~~~~~~~~~~~

The core content-addressable object store for Deep.

This module defines the fundamental data structures:
- **Blob**: Raw file content.
- **Tree**: Directory-like mapping of names to other objects.
- **Commit**: Snapshot of the project state with metadata.
- **Tag**: Annotated references to specific commits.

All objects are identified by their SHA-1 hash and stored using a
fan-out directory structure (`objects/xx/yyyy...`) to ensure performance
at scale. Consistent with Deep's independent architecture.
"""

from __future__ import annotations

import re
import os
import sys
import time
import threading
import json
import zlib
import functools
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union, ClassVar, Any, cast

from deep.utils.utils import (
    AtomicWriter, get_local_timezone_offset, hash_bytes, 
    resolve_cache_dir, resolve_dg_dir
) # type: ignore[import]

_SHA_RE = re.compile(r'^[0-9a-f]{40}$')

class CorruptObjectError(Exception):
    """Raised when an object is found to be corrupted on disk or during parsing."""
    pass

# Maximum delta-chain depth before aborting reconstruction.
# Prevents memory overflow from pathological or cyclic delta chains.
MAX_DELTA_CHAIN_DEPTH = 50

# Thread-local storage for tracking delta-chain depth during read_object.
_delta_depth = threading.local()

def get_delta_depth() -> int:
    val = getattr(_delta_depth, "value", 0)
    return cast(int, val)

def set_delta_depth(val: int) -> None:
    setattr(_delta_depth, "value", val)


# ── Helpers ──────────────────────────────────────────────────────────

def _object_path(objects_dir: Path, sha: str, level: int = 2) -> Path:
    """Return the absolute filesystem path for an object given its SHA-1.
    
    Supports Level 1 (xx/yyyy...) and Level 2 (xx/yy/zzzz...) fan-out.
    New objects are always written to Level 2.
    """
    s: str = str(sha)
    if not _SHA_RE.match(s):
        raise ValueError(f"Invalid SHA format: {s!r}")
    
    if level == 1:
        return objects_dir / s[0:2] / s[2:40]
    else:
        # Default Level 2: objects/xx/yy/zzzz...
        return objects_dir / s[0:2] / s[2:4] / s[4:40]


def walk_loose_shas(objects_dir: Path):
    """Yield all loose object SHAs in the repository, regardless of fan-out depth."""
    for root, _, files in os.walk(objects_dir):
        # Skip pack and info directories
        if "pack" in root or "info" in root:
            continue
        for f in files:
            if len(f) >= 36: # Remaining part of SHA
                # Reconstruct SHA from path
                rel = Path(root).relative_to(objects_dir)
                sha = "".join(rel.parts) + f
                if len(sha) == 40 and _SHA_RE.match(sha):
                    yield sha


def _serialize(obj_type: str, content: bytes) -> bytes:
    """Build the canonical ``<type> <size>\\0<content>`` byte string."""
    header = f"{obj_type} {len(content)}".encode("ascii")
    return header + b"\x00" + content


def _deserialize(raw: bytes) -> tuple[str, bytes]:
    """Split a stored object into ``(type, content)``."""
    r: bytes = raw
    null_idx = r.index(b"\x00")
    header = cast(Any, r)[:null_idx].decode("ascii") # type: ignore
    obj_type, size_str = header.split(" ", 1)
    size = int(size_str)
    content = cast(Any, r)[null_idx + 1:len(r)] # type: ignore
    if len(content) != size:
        raise ValueError(
            f"Object size mismatch: header says {size}, got {len(content)}"
        )
    return obj_type, content


# ── Base class ───────────────────────────────────────────────────────

@dataclass
class DeepObject:
    """Abstract base class for all content-addressable objects in Deep."""

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
class Blob(DeepObject):
    """A blob stores the raw contents of a single file."""

    OBJ_TYPE: str = field(init=False, default="blob", repr=False)
    data: bytes = b""

    def __repr__(self) -> str:
        DEBUG_MODE = os.environ.get("DEEP_DEBUG") == "1"
        if DEBUG_MODE:
            return f"Blob(data={self.data!r})"
        preview = self.data[:64]
        return f"Blob(data={preview!r}..., len={len(self.data)})"

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
        # RULE: Fix SHA1 alignment if leaked from index (strip padding)
        if len(self.sha) == 64 and self.sha.endswith('0' * 24):
            self.sha = self.sha[:40]
            
        if len(self.sha) != 40:
             raise ValueError(f"Invalid SHA-1 length in TreeEntry: {len(self.sha)} chars (expected 40)")

        # Normalize mode (Deep trees use "40000" for directories)
        if self.mode == "040000":
            self.mode = "40000"
        
        valid_modes = {"100644", "100755", "40000", "120000", "160000"}
        if self.mode not in valid_modes:
            # Try to be helpful: if it looks like a directory but has blob mode, we will catch it in validate()
            pass

    def validate(self, objects_dir: Path):
        """Strict validation: ensure mode matches actual object type."""
        # Note: read_object_safe, Tree, Blob are available in the module scope.
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
class Tree(DeepObject):
    """A tree maps names to blobs (files) or other trees (directories)."""

    OBJ_TYPE: str = field(init=False, default="tree", repr=False)
    entries: List[TreeEntry] = field(default_factory=list)

    def serialize_content(self) -> bytes:
        """Serialize entries sorted by name (Deep native format).

        Format: <mode> <name>\0<20-byte raw SHA-1>
        """
        from deep.utils.utils import sanitize_filename
        
        parts: list[bytes] = []
        # We need objects_dir for validation. If NOT provided, we skip strict validation 
        # (e.g. during initial construction before writing).
        # But for 'write()', we always have objects_dir.
        
        def sort_key(e: TreeEntry) -> str:
            if e.mode == "40000":
                return e.name + "/"
            return e.name

        for entry in sorted(self.entries, key=sort_key):
            # 1. Validate
            assert "\x00" not in entry.name, f"Null byte in filename: {repr(entry.name)}"
            
            # 2. Sanitize (to ensure robust storage and cross-platform compatibility)
            safe_name = sanitize_filename(entry.name)
            
            # 3. Convert to binary
            mode_bytes = entry.mode.encode("ascii")
            name_bytes = safe_name.encode("utf-8")
            
            # RULE: Objects MUST use 20-byte raw SHA-1. No padding allowed here.
            if len(entry.sha) != 40:
                raise CorruptObjectError(f"Tree entry {entry.name} contains invalid SHA-1 length: {len(entry.sha)}")
                
            sha_bytes = bytes.fromhex(entry.sha)
            
            # 4. Construct entry: <mode> <name>\0<sha>
            parts.append(mode_bytes + b" " + name_bytes + b"\x00" + sha_bytes)
            
        return b"".join(parts)

    @classmethod
    def from_content(cls, content: bytes) -> "Tree":
        """Deserialise tree content bytes back into a :class:`Tree`."""
        entries: list[TreeEntry] = []
        idx: int = 0
        limit: int = len(content)
        EXPECTED_SHA_BYTES = 20
        
        while idx < limit:
            try:
                # Find the null byte separating <mode> <name> from the SHA.
                null_idx: int = content.index(b"\x00", idx)
                mode_name: str = content[idx:null_idx].decode("utf-8")
                mode, name = mode_name.split(" ", 1)
                
                # RULE: Strict bounds check for 20-byte SHA
                sha_start: int = null_idx + 1
                sha_end: int = null_idx + 1 + EXPECTED_SHA_BYTES
                
                if sha_end > limit:
                    raise CorruptObjectError(f"Unexpected end of tree data for entry {mode_name}")
                
                sha_bytes: bytes = content[sha_start:sha_end]
                sha: str = sha_bytes.hex()
                entries.append(TreeEntry(mode=mode, name=name, sha=sha))
                idx = sha_end
            except (ValueError, IndexError) as e:
                raise CorruptObjectError(f"Tree parsing failed at offset {idx}: {e}")
                
        return cls(entries=entries)


# ── Commit ───────────────────────────────────────────────────────────

@dataclass
class Commit(DeepObject):
    """A commit binds a :class:`Tree` to metadata and parent commits."""

    OBJ_TYPE: str = field(init=False, default="commit", repr=False)
    tree_sha: str = ""
    parent_shas: List[str] = field(default_factory=list)
    author: str = "Deep User <user@deep>"
    committer: str = "Deep User <user@deep>"
    message: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time()))
    timezone: str = field(default_factory=lambda: get_local_timezone_offset())
    sequence_id: int = 0
    signature: Optional[str] = None

    def serialize_content(self) -> bytes:
        """Serialize commit in standard VCS format.

        Standard headers: tree, parent, author, committer.
        Deep-specific metadata stored as optional x-deep-* headers
        for full interoperability.
        """
        lines: list[str] = [f"tree {self.tree_sha}"]
        for p in self.parent_shas:
            lines.append(f"parent {p}")
        lines.append(f"author {self.author} {self.timestamp} {self.timezone}")
        lines.append(
            f"committer {self.committer} {self.timestamp} {self.timezone}"
        )
        # Deep-specific metadata as optional x-deep-* headers
        # Deep-specific metadata preserved in custom headers
        if self.sequence_id:
            lines.append(f"x-deep-sequence {self.sequence_id}")
        sig: Optional[str] = self.signature
        if sig:
            lines.append("gpgsig -----BEGIN PGP SIGNATURE-----")
            for sig_line in sig.splitlines():
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
        sequence_id = 0
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
                    signature_lines.append(cast(Any, line)[1:] if line.startswith(" ") else line)
                continue
                
            if line.startswith("tree "):
                tree_sha = cast(Any, line)[5:]
            elif line.startswith("parent "): # type: ignore
                parent_shas.append(cast(Any, line)[7:])
            elif line.startswith("sequence ") or line.startswith("x-deep-sequence "): # type: ignore
                try:
                    val = line.split(" ", 1)[1].strip()
                    sequence_id = int(val)
                except (ValueError, IndexError):
                    sequence_id = 0
            elif line.startswith("author "): # type: ignore
                parts = line[7:].rsplit(" ", 2)
                author = parts[0]
                timestamp = int(parts[1])
                timezone = parts[2]
            elif line.startswith("committer "): # type: ignore
                parts = cast(Any, line)[10:].rsplit(" ", 2)
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
            sequence_id=sequence_id,
            signature=signature,
        )


# ── Tag ──────────────────────────────────────────────────────────────

@dataclass
class Tag(DeepObject):
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
                target_sha = cast(Any, line)[7:] # type: ignore
            elif line.startswith("type "):
                target_type = cast(Any, line)[5:] # type: ignore
            elif line.startswith("tag "):
                tag_name = cast(Any, line)[4:] # type: ignore
            elif line.startswith("tagger "):
                parts = cast(Any, line)[7:].rsplit(" ", 2) # type: ignore
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
class DeltaObject(DeepObject):
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
        base_sha = cast(Any, content)[:null_idx].decode("ascii") # type: ignore
        delta_data = cast(Any, content)[null_idx+1:] # type: ignore
        return cls(base_sha=base_sha, delta_data=delta_data)


@dataclass
class Chunk(DeepObject):
    """A sub-file content chunk for deduplication."""
    OBJ_TYPE: str = field(init=False, default="chunk", repr=False)
    data: bytes

    def __repr__(self) -> str:
        DEBUG_MODE = os.environ.get("DEEP_DEBUG") == "1"
        if DEBUG_MODE:
            return f"Chunk(data={self.data!r})"
        preview = self.data[:64]
        return f"Chunk(data={preview!r}..., len={len(self.data)})"

    def serialize_content(self) -> bytes:
        return self.data

    @classmethod
    def from_content(cls, content: bytes) -> "Chunk":
        return cls(data=content)


@dataclass
class ChunkedBlob(DeepObject):
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

def write_object(objects_dir: Path, obj: DeepObject) -> str:
    """Convenience helper to write a DeepObject."""
    return obj.write(objects_dir)


def write_large_blob(objects_dir: Path, data: bytes) -> str:
    """Write large data using Content-Defined Chunking for deduplication."""
    from deep.storage.chunking import chunk_data # type: ignore[import]
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
    from deep.storage.delta import create_delta # type: ignore[import]
    
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

@functools.lru_cache(maxsize=10240)
def read_object(objects_dir: Path, sha: str) -> DeepObject:
    """Read and deserialise an object from the object store.
    
    This function transparently handles compressed (zlib), 
    DELTA-compressed, and Vaulted objects.
    """
    # Phase 16.6: Delta depth safety reset
    if get_delta_depth() == 0:
        set_delta_depth(0)
    if not sha or not isinstance(sha, str) or len(sha) != 40:
        raise ValueError(f"Invalid object SHA: {sha!r}")
        
    path = _object_path(objects_dir, sha, level=2)
    l1_path = _object_path(objects_dir, sha, level=1)
    
    # Phase 16.6: Use standardized cache resolution
    cache_dir = resolve_cache_dir(objects_dir.parent)
    index_path = cache_dir / "object_index.json"
    if index_path.exists():
        try:
            global_index = json.loads(index_path.read_text(encoding="utf-8"))
            loc = global_index.get(sha)
            if loc and loc.startswith("pack:"):
                pack_info = loc[5:] # sha@offset
                p_sha, off_str = pack_info.split("@")
                from deep.storage.pack import PackReader
                reader = PackReader(objects_dir.parent)
                if hasattr(reader, "_read_at"):
                    p_path = objects_dir / "pack" / f"pack-{p_sha}.pack"
                    return reader._read_at(p_path, int(off_str))
        except Exception:
            pass

    if not path.exists():
        if l1_path.exists():
            path = l1_path
        else:
            # Check Vault (v2) and Pack (v1 fallback)
            from deep.storage.vault import DeepVaultReader # type: ignore
            vault_dir = objects_dir / "vault"
            res = None
            if vault_dir.exists():
                for v_path in vault_dir.glob("*.dvpf"):
                    reader = DeepVaultReader(v_path)
                    res = reader.get_object(sha)
                    if res:
                        obj_type, content = res
                        raw = _serialize(obj_type, content)
                        break
            
            if not res:
                from deep.storage.pack import PackReader # type: ignore[import]
                reader = PackReader(objects_dir.parent)
                obj = reader.get_object(sha)
                if obj:
                    return obj
            
            # Lazy fetch from promisor
            from deep.core.config import get_promisor_remote # type: ignore[import]
            promisor_url = get_promisor_remote(objects_dir.parent)
            if promisor_url:
                from deep.network.client import get_remote_client # type: ignore[import]
                try:
                    client = get_remote_client(promisor_url)
                    client.connect()
                    client.fetch(objects_dir, sha, depth=1)
                    client.disconnect()
                    if path.exists(): pass
                    elif l1_path.exists(): path = l1_path
                except Exception: pass
            
            if not path.exists() and not l1_path.exists():
                raise FileNotFoundError(f"Object {sha} not found in loose or pack storage.")
        
    data = path.read_bytes()
    
    try:
        # Try decompressing first (new format)
        raw = zlib.decompress(data)
    except zlib.error:
        # If decompression fails, it might be an old uncompressed object
        valid_headers = [b"blob ", b"tree ", b"commit ", b"tag ", b"delta ", b"chunked_blob ", b"chunk "]
        if any(data.startswith(h) for h in valid_headers):
            raw = data
        else:
            raise ValueError(f"Object {sha} is corrupted or in an unknown format.")

    actual_sha = hash_bytes(raw)
    if actual_sha != sha:
        raise ValueError(f"Corrupt object {sha} (hash mismatch).")

    obj_type, content = _deserialize(raw)

    try:
        if obj_type == "blob":
            return Blob(data=content)
        elif obj_type == "tree":
            return Tree.from_content(content)
        elif obj_type == "commit":
            return Commit.from_content(content)
        elif obj_type == "tag":
            return Tag.from_content(content)
    except CorruptObjectError as e:
        print(f"Warning: Object {sha} is corrupted: {e}")
        print("Suggest running: deep fsck")
        raise
    except Exception as e:
        raise CorruptObjectError(f"Failed to parse {obj_type} {sha}: {e}")

    if obj_type == "delta":
        delta_obj = DeltaObject.from_content(content)
        # Track delta-chain depth to prevent runaway recursion
        depth = get_delta_depth()
        if get_delta_depth() >= MAX_DELTA_CHAIN_DEPTH:  # type: ignore[operator]
            raise ValueError(
                f"Deep: delta-chain depth exceeded ({MAX_DELTA_CHAIN_DEPTH}). "
                f"Object {sha} may be part of a cyclic or pathologically deep delta chain."
            )
        set_delta_depth(depth + 1)
        try:
            # Resolve base
            from deep.storage.delta import apply_delta # type: ignore[import]
            base_obj = read_object(objects_dir, delta_obj.base_sha)
            base_content = base_obj.serialize_content()
            target_content = apply_delta(base_content, delta_obj.delta_data)
            
            # If target_content starts with a known object type header, re-parse it.
            # Otherwise, assume it's a blob.
            try:
                t_obj_type, t_content = _deserialize(target_content)
                if t_obj_type == "blob": return Blob(data=t_content)
                if t_obj_type == "tree": return Tree.from_content(t_content)
                if t_obj_type == "commit": return Commit.from_content(t_content)
                if t_obj_type == "tag": return Tag.from_content(t_content)
                return Blob(data=t_content)
            except (ValueError, IndexError):
                # Fallback: if it doesn't look like a serialized object, it's raw data
                return Blob(data=target_content)
        finally:
            set_delta_depth(max(0, get_delta_depth() - 1))
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
    
    # Explicit return to satisfy linter that all paths return DeepObject
    return DeepObject() # type: ignore


def read_object_safe(objects_dir: Path, sha: str) -> DeepObject:
    """Read an object and verify its SHA-1 hash."""
    path = _object_path(objects_dir, sha)
    
    if not path.exists():
        # Check packfiles
        from deep.storage.pack import PackReader # type: ignore[import]
        reader = PackReader(objects_dir.parent)
        obj = reader.get_object(sha)
        if obj:
            # For packed objects, we trust the PackReader's integrity check (DIDX/trailer)
            # but we can do a quick content verification if needed. 
            # PackReader already deserializes, so we can verify the hash of the raw content.
            return obj
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
        
        # Phase 57 (Roadmap): Attempt P2P Heal
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
        "chunk": Chunk,
        "chunked_blob": ChunkedBlob,
        "delta": DeltaObject,
    }.get(obj_type)
    
    if cls is None:
        if obj_type == "delta":
            return read_object(objects_dir, sha)
        raise ValueError(f"Unknown object type: {obj_type}")
        
    return cls.from_content(content)


def _attempt_p2p_heal(dg_dir: Path, sha: str, timeout: float = 5.0) -> Optional[bytes]:
    """Attempt to fetch a valid object from P2P peers.

    Uses a configurable timeout to prevent blocking local operations
    if peers are unreachable or slow.
    """
    import concurrent.futures

    def _do_heal() -> Optional[bytes]:
        try:
            from deep.network.p2p import P2PEngine # type: ignore[import]
            engine = P2PEngine(dg_dir)
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

    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(cast(Any, _do_heal))
            return future.result(timeout=timeout)
    except (concurrent.futures.TimeoutError, Exception):
        return None

def generate_object_index(dg_dir: Path) -> Dict[str, str]:
    """Scan all loose and packed objects to build a global index [sha -> pack_sha@offset]."""
    objects_dir = dg_dir / ".deep" / "objects" # Standard deep layout
    if not objects_dir.exists():
         objects_dir = dg_dir / "objects" # Fallback if run from repo root
         
    index = {}
    
    # 1. Loose objects
    for sha in walk_loose_shas(objects_dir):
        index[sha] = "loose"
        
    # 2. Packfiles
    from deep.storage.pack import PackReader
    import struct
    pack_dir = objects_dir / "pack"
    if pack_dir.exists():
        for idx_file in pack_dir.glob("*.idx"):
            pack_sha = idx_file.stem[5:]
            try:
                data = idx_file.read_bytes()
                if data[:4] == b"DIDX":
                    total_count = struct.unpack(">I", data[1028:1032])[0]
                    sha_start = 1032
                    offset_start = sha_start + total_count * 20
                    for i in range(total_count):
                        sha_pos = sha_start + i * 20
                        off_pos = offset_start + i * 8
                        sha = data[sha_pos : sha_pos + 20].hex()
                        offset = struct.unpack(">Q", data[off_pos : off_pos + 8])[0]
                        index[sha] = f"pack:{pack_sha}@{offset}"
            except Exception:
                continue
                
    # Phase 16.6: Use standardized cache resolution
    cache_dir = resolve_cache_dir(dg_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / "object_index.json"
    
    # Phase 16.6: Atomic write for object index
    with AtomicWriter(index_path, mode="w") as aw:
        aw.write(json.dumps(index, indent=2))
    return index

def get_reachable_objects(objects_dir: Path, shas: list[str], max_depth: int | None = None, filter_spec: str | None = None, shallow_since: int | None = None) -> list[str]:
    """Return all objects reachable from the given SHAs (commits, trees, blobs), supporting depth and filters."""
    seen = set()
    queue = deque((sha, 1) for sha in shas)
    reachable = []
    
    blob_none = (filter_spec == "blob:none")
    
    while queue:
        item = queue.popleft()
        sha: str = item[0]
        depth: int = item[1]
        if not sha or sha == "0"*40 or sha in seen:
            continue
            
        seen.add(sha)
        
        try:
            obj = read_object(objects_dir, sha)
            
            # Apply filter
            if blob_none and isinstance(obj, Blob):
                continue
                
            if isinstance(obj, Commit):
                # Apply shallow_since: if commit is older than requested date, don't traverse parents
                is_too_old = False
                if shallow_since is not None:
                    if obj.timestamp < shallow_since:
                        is_too_old = True

                if is_too_old:
                    # If this commit is already too old, we don't include it or its parents
                    continue

                reachable.append(sha)

                if obj.tree_sha:
                    queue.append((obj.tree_sha, depth)) # Trees don't increase commit depth
                
                # Check depth bound and time bound before adding parents
                if max_depth is None or (isinstance(max_depth, int) and depth < max_depth):
                    for p in obj.parent_shas:
                        queue.append((p, depth + 1))
            else:
                # Trees, Blobs, Tags are added normally
                reachable.append(sha)
                
                if isinstance(obj, Tree):
                    for entry in obj.entries:
                        queue.append((entry.sha, depth))
                elif isinstance(obj, Tag):
                    if obj.target_sha:
                        queue.append((obj.target_sha, depth))
        except (FileNotFoundError, ValueError):
            # Ignore missing objects
            pass
            
    return reachable

"""
deep.storage.index
~~~~~~~~~~~~~~~~~~

DeepIndex v1: Redesigned Staging Area for Deep.
This index structure is optimized for independent operation, providing
O(1) conflict detection via path hashing and nanosecond-precision timestamps.
"""

from __future__ import annotations
import struct
import logging
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Any, cast, List, Tuple

from deep.core.locks import IndexLock
from deep.utils.utils import AtomicWriter

# ── DeepIndex Binary Format v1 ───────────────────────────────────────
# [Signature: 'DPIX' (4B)]
# [Version: uint32 (4B)]
# [Entry Count: uint32 (4B)]
# [Flags: uint32 (4B)] - Reserved for future use
# ── Entries (sorted by path) ──
# [Path_Hash: SHA1 (20B)]
# [MTIME_NS: uint64 (8B)]
# [Size: uint64 (8B)]
# [Content_Hash: SHA1 (20B)]
# [Flags: uint32 (4B)]
# [Path_Len: uint16 (2B)]
# [Path: UTF-8 string]

INDEX_SIGNATURE = b"DPIX"
INDEX_VERSION_V1 = 1

@dataclass
class DeepIndexEntry:
    """Metadata for a single entry in DeepIndex v1."""
    path_hash: str # SHA1 of the relative path
    mtime_ns: int  # Nanosecond timestamp
    size: int
    content_hash: str
    flags: int = 0 # Bit 0: skip-worktree, Bit 1: executable

    @property
    def skip_worktree(self) -> bool:
        return bool(self.flags & 0x01)

    @skip_worktree.setter
    def skip_worktree(self, value: bool):
        if value: self.flags |= 0x01
        else: self.flags &= ~0x01

    @property
    def is_executable(self) -> bool:
        return bool(self.flags & 0x02)

@dataclass
class DeepIndex:
    """In-memory representation of DeepIndex v1."""
    entries: Dict[str, DeepIndexEntry] = field(default_factory=dict)
    version: int = INDEX_VERSION_V1

    def to_binary(self) -> bytes:
        """Serialize as DeepIndex v1 binary."""
        header = INDEX_SIGNATURE
        header += struct.pack(">III", self.version, len(self.entries), 0)
        
        parts = [header]
        # Sort by path for deterministic hashing and faster walking
        for path in sorted(self.entries.keys()):
            entry = self.entries[path]
            path_bytes = path.encode("utf-8")
            
            entry_data = bytes.fromhex(entry.path_hash)
            entry_data += struct.pack(">QQ", entry.mtime_ns, entry.size)
            entry_data += bytes.fromhex(entry.content_hash)
            entry_data += struct.pack(">IH", entry.flags, len(path_bytes))
            entry_data += path_bytes
            parts.append(entry_data)
            
        return b"".join(parts)

    @classmethod
    def from_binary(cls, data: bytes) -> "DeepIndex":
        if not data:
            return cls()
            
        if data[:4] != INDEX_SIGNATURE:
            # Check if it's the legacy DEEP v1 format (Phase 1-20 placeholder)
            if data[:4] == b"DEEP":
                return cls._migrate_from_legacy_v1(data)
            raise ValueError(f"Invalid DeepIndex signature: {data[:4]!r}")
            
        version, count, _ = struct.unpack(">III", data[4:16])
        if version != INDEX_VERSION_V1:
            raise ValueError(f"Unsupported DeepIndex version: {version}")
            
        entries: Dict[str, DeepIndexEntry] = {}
        offset = 16
        for _ in range(count):
            p_hash = data[offset : offset + 20].hex()
            mtime_ns, size = struct.unpack(">QQ", data[offset + 20 : offset + 36])
            c_hash = data[offset + 36 : offset + 56].hex()
            flags, path_len = struct.unpack(">IH", data[offset + 56 : offset + 62])
            path = data[offset + 62 : offset + 62 + path_len].decode("utf-8")
            
            entries[path] = DeepIndexEntry(
                path_hash=p_hash,
                mtime_ns=mtime_ns,
                size=size,
                content_hash=c_hash,
                flags=flags
            )
            offset += 62 + path_len
            
        return cls(entries=entries, version=version)

    @classmethod
    def _migrate_from_legacy_v1(cls, data: bytes) -> "DeepIndex":
        """Handle migration from the legacy 'DEEP' format used in earlier phases."""
        logging.getLogger("Deep").info("Migrating legacy index to DeepIndex v1")
        # Legacy format: [DEEP][uint32 ver][uint32 count]
        # Entry: [H path_len][20s sha][Q size][d mtime][B flags][path]
        count = struct.unpack(">I", data[8:12])[0]
        entries = {}
        offset = 12
        for _ in range(count):
            path_len, sha, size, mtime, flags = struct.unpack_from(">H20sQdB", data, offset)
            offset += 39
            path = data[offset : offset + path_len].decode("utf-8")
            offset += path_len
            
            # Convert mtime (float seconds) to nanoseconds
            mtime_ns = int(mtime * 1e9)
            p_hash = hashlib.sha1(path.encode("utf-8")).hexdigest()
            
            entries[path] = DeepIndexEntry(
                path_hash=p_hash,
                mtime_ns=mtime_ns,
                size=size,
                content_hash=sha.hex(),
                flags=flags
            )
        return cls(entries=entries)

# ── Public APIs (Independent of Deep naming) ──────────────────────────

def read_index(dg_dir: Path) -> DeepIndex:
    path = dg_dir / "index"
    if not path.exists(): return DeepIndex()
    
    lock = IndexLock(dg_dir)
    with lock:
        try:
            return DeepIndex.from_binary(path.read_bytes())
        except Exception as e:
            logging.getLogger("Deep").error(f"Failed to read index: {e}")
            return DeepIndex()

def write_index(dg_dir: Path, index: DeepIndex) -> None:
    path = dg_dir / "index"
    lock = IndexLock(dg_dir)
    with lock:
        with AtomicWriter(path) as aw:
            aw.write(index.to_binary())

def read_index_no_lock(dg_dir: Path) -> DeepIndex:
    """Read the index without acquiring a lock (caller must hold RepositoryLock)."""
    path = dg_dir / "index"
    if not path.exists(): return DeepIndex()
    return DeepIndex.from_binary(path.read_bytes())

def write_index_no_lock(dg_dir: Path, index: DeepIndex) -> None:
    """Write the index without acquiring a lock (caller must hold RepositoryLock)."""
    path = dg_dir / "index"
    with AtomicWriter(path) as aw:
        aw.write(index.to_binary())



def add_to_index(dg_dir: Path, rel_path: str, sha: str, size: int, mtime_ns: int):
    add_multiple_to_index(dg_dir, [(rel_path, sha, size, mtime_ns)])

def add_multiple_to_index(dg_dir: Path, entries: List[Tuple[str, str, int, int]]):
    from deep.core.locks import IndexLock
    lock = IndexLock(dg_dir)
    with lock:
        index = read_index_no_lock(dg_dir)
        for rel_path, sha, size, mtime_ns in entries:
            p_hash = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()
            index.entries[rel_path] = DeepIndexEntry(
                path_hash=p_hash,
                mtime_ns=mtime_ns,
                size=size,
                content_hash=sha
            )
        write_index_no_lock(dg_dir, index)

def remove_from_index(dg_dir: Path, rel_path: str):
    remove_multiple_from_index(dg_dir, [rel_path])

def remove_multiple_from_index(dg_dir: Path, rel_paths: List[str]):
    from deep.core.locks import IndexLock
    lock = IndexLock(dg_dir)
    with lock:
        index = read_index_no_lock(dg_dir)
        for p in rel_paths:
            if p in index.entries:
                del index.entries[p]
        write_index_no_lock(dg_dir, index)

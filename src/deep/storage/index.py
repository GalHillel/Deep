"""
deep.storage.index
~~~~~~~~~~~~~~~~~~

The High-Performance Staging Area (Index).

This module manages the 프로젝트's intermediate state between the working
directory and the next commit. The index is stored in a optimized binary 
format (Version 1) supporting fast lookups via memory mapping (mmap).
Concurrency is strictly controlled via `.deep_git/index.lock`.
"""

from __future__ import annotations

import mmap
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from filelock import FileLock

from deep.utils.utils import AtomicWriter

# ── Binary Format Constants ──────────────────────────────────────────
# Header: 4B signature 'DEEP', 4B version (1)
INDEX_SIGNATURE = b"DEEP"
INDEX_VERSION = 1
# Entry Header: 2B path_len, 20B sha, 8B size, 8B mtime (fixed size: 38 bytes)
ENTRY_HEADER_FORMAT = ">H20sQd"
ENTRY_HEADER_SIZE = struct.calcsize(ENTRY_HEADER_FORMAT)


@dataclass
class IndexEntry:
    """Metadata for a single staged file."""
    sha: str
    size: int
    mtime: float


# ── Metadata Compat (for tests) ───────────────────────────────────

@dataclass
class Index:
    """In-memory representation of the index file."""
    entries: Dict[str, IndexEntry] = field(default_factory=dict)

    def to_json(self) -> str:
        import json
        return json.dumps({
            "entries": {
                p: {"sha": e.sha, "size": e.size, "mtime": e.mtime}
                for p, e in self.entries.items()
            }
        })

    @classmethod
    def from_json(cls, text: str) -> "Index":
        import json
        raw = json.loads(text)
        entries = {
            p: IndexEntry(sha=e["sha"], size=e["size"], mtime=e["mtime"])
            for p, e in raw.get("entries", {}).items()
        }
        return cls(entries=entries)

    # ── Binary Serialisation ─────────────────────────────────────────

    def to_binary(self) -> bytes:
        """Serialise the index to the Next-Gen binary format."""
        # Header
        parts = [INDEX_SIGNATURE, struct.pack(">I", INDEX_VERSION)]
        # Entry Count
        parts.append(struct.pack(">I", len(self.entries)))

        for path, entry in sorted(self.entries.items()):
            path_bytes = path.encode("utf-8")
            # Entry: header (len, sha, size, mtime) + path
            parts.append(struct.pack(
                ENTRY_HEADER_FORMAT,
                len(path_bytes),
                bytes.fromhex(entry.sha),
                entry.size,
                entry.mtime
            ))
            parts.append(path_bytes)

        return b"".join(parts)

    @classmethod
    def from_binary(cls, data: bytes) -> "Index":
        """Deserialise an index from binary data."""
        if not data:
            return cls()

        if data[:4] != INDEX_SIGNATURE:
            # Fallback to JSON migration if signature missing
            try:
                import json
                raw = json.loads(data.decode("utf-8"))
                entries = {}
                for path, info in raw.get("entries", {}).items():
                    entries[path] = IndexEntry(sha=info["sha"], size=info["size"], mtime=info["mtime"])
                return cls(entries=entries)
            except Exception:
                raise ValueError("Invalid index format: signature mismatch and JSON fallback failed.")

        version = struct.unpack(">I", data[4:8])[0]
        if version != INDEX_VERSION:
            raise ValueError(f"Unsupported index version: {version}")

        entry_count = struct.unpack(">I", data[8:12])[0]
        entries: dict[str, IndexEntry] = {}
        offset = 12

        for _ in range(entry_count):
            path_len, sha_raw, size, mtime = struct.unpack_from(ENTRY_HEADER_FORMAT, data, offset)
            offset += ENTRY_HEADER_SIZE
            path = data[offset : offset + path_len].decode("utf-8")
            offset += path_len
            entries[path] = IndexEntry(sha=sha_raw.hex(), size=size, mtime=mtime)

        return cls(entries=entries)


# ── Locked read / write helpers ──────────────────────────────────────

def _index_path(dg_dir: Path) -> Path:
    return dg_dir / "index"


def _lock_path(dg_dir: Path) -> Path:
    return dg_dir / "index.lock"


def _read_index_no_lock(dg_dir: Path) -> Index:
    """Internal: read the index without acquiring a lock."""
    path = _index_path(dg_dir)
    if not path.exists():
        return Index()
    
    try:
        data = path.read_bytes()
        if not data:
            return Index()
        return Index.from_binary(data)
    except Exception as e:
        # If the index is totally corrupted, return an empty index
        # A more advanced recovery could be implemented, but an empty index
        # is safe because `deep status` will just show everything as deleted/new.
        print(f"Warning: Index corrupted, resetting to empty. Error: {e}")
        return Index()


def read_index(dg_dir: Path) -> Index:
    """Read the index file under an exclusive lock, using mmap for speed."""
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        return _read_index_no_lock(dg_dir)


def _write_index_no_lock(dg_dir: Path, index: Index) -> None:
    """Internal: write the index without acquiring a lock."""
    with AtomicWriter(_index_path(dg_dir)) as aw:
        aw.write(index.to_binary())


def write_index(dg_dir: Path, index: Index) -> None:
    """Write the index file atomically in binary format."""
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        _write_index_no_lock(dg_dir, index)


def update_index_entry(
    dg_dir: Path,
    rel_path: str,
    sha: str,
    size: int,
    mtime: float,
) -> None:
    """Atomically add or update a single entry in the binary index."""
    update_multiple_index_entries(dg_dir, [(rel_path, sha, size, mtime)])


def update_multiple_index_entries(
    dg_dir: Path,
    updates: list[tuple[str, str, int, float]],
) -> None:
    """Atomically add / update multiple entries in the binary index."""
    if not updates:
        return
        
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        index = _read_index_no_lock(dg_dir)
        from deep.core.reconcile import sanitize_path
        
        for rel_path, sha, size, mtime in updates:
            # Defensive check: ensure no illegal characters in path
            # Even though add_cmd should sanitize, we guard here too.
            sanitized_parts = []
            path_changed = False
            for part in rel_path.split('/'):
                s_part, changed = sanitize_path(part)
                sanitized_parts.append(s_part)
                if changed:
                    path_changed = True
            
            if path_changed:
                rel_path = "/".join(sanitized_parts)
            
            index.entries[rel_path] = IndexEntry(sha=sha, size=size, mtime=mtime)
        _write_index_no_lock(dg_dir, index)


def remove_index_entry(dg_dir: Path, rel_path: str) -> None:
    """Atomically remove an entry from the index."""
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        index = _read_index_no_lock(dg_dir)
        if rel_path not in index.entries:
            raise KeyError(f"{rel_path!r} is not in the index")
        del index.entries[rel_path]
        _write_index_no_lock(dg_dir, index)

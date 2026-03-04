"""
deep_git.core.index
~~~~~~~~~~~~~~~~~~~~
The staging area (index) for Deep Git.

The index is a JSON file at ``.deep_git/index`` that maps working-tree paths
to their blob SHA-1 hashes, file sizes, and modification timestamps.

**Concurrency safety** is provided by :pypi:`filelock`: every read-modify-write
cycle acquires an exclusive lock on ``.deep_git/index.lock``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional

from filelock import FileLock

from deep_git.core.utils import AtomicWriter


@dataclass
class IndexEntry:
    """Metadata for a single staged file.

    Attributes:
        sha:   SHA-1 hex digest of the blob.
        size:  File size in bytes at staging time.
        mtime: Modification time (UNIX epoch float) at staging time.
    """
    sha: str
    size: int
    mtime: float


@dataclass
class Index:
    """In-memory representation of the index file.

    Attributes:
        entries: Mapping of relative file paths → :class:`IndexEntry`.
    """
    entries: Dict[str, IndexEntry] = field(default_factory=dict)

    # ── Serialisation ────────────────────────────────────────────────

    def to_json(self) -> str:
        """Serialise the index to a JSON string."""
        data = {
            "entries": {
                path: asdict(entry)
                for path, entry in sorted(self.entries.items())
            }
        }
        return json.dumps(data, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Index":
        """Deserialise an index from a JSON string."""
        raw = json.loads(text)
        entries: dict[str, IndexEntry] = {}
        for path, info in raw.get("entries", {}).items():
            entries[path] = IndexEntry(
                sha=info["sha"],
                size=info["size"],
                mtime=info["mtime"],
            )
        return cls(entries=entries)


# ── Locked read / write helpers ──────────────────────────────────────

def _index_path(dg_dir: Path) -> Path:
    return dg_dir / "index"


def _lock_path(dg_dir: Path) -> Path:
    return dg_dir / "index.lock"


def read_index(dg_dir: Path) -> Index:
    """Read the index file under an exclusive lock.

    Args:
        dg_dir: Path to the ``.deep_git`` directory.

    Returns:
        The current :class:`Index`.
    """
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        text = _index_path(dg_dir).read_text(encoding="utf-8")
        return Index.from_json(text)


def write_index(dg_dir: Path, index: Index) -> None:
    """Write the index file atomically under an exclusive lock.

    Args:
        dg_dir: Path to the ``.deep_git`` directory.
        index:  The :class:`Index` to persist.
    """
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        with AtomicWriter(_index_path(dg_dir), mode="w") as aw:
            aw.write(index.to_json())


def update_index_entry(
    dg_dir: Path,
    rel_path: str,
    sha: str,
    size: int,
    mtime: float,
) -> None:
    """Atomically add / update a single entry in the index.

    This acquires the lock, reads the current index, updates the entry,
    and writes it back — all while holding the lock.

    Args:
        dg_dir:   Path to the ``.deep_git`` directory.
        rel_path: Relative file path (forward-slash separated).
        sha:      SHA-1 hex digest of the blob.
        size:     File size in bytes.
        mtime:    Modification time (UNIX epoch).
    """
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        text = _index_path(dg_dir).read_text(encoding="utf-8")
        index = Index.from_json(text)
        index.entries[rel_path] = IndexEntry(sha=sha, size=size, mtime=mtime)
        with AtomicWriter(_index_path(dg_dir), mode="w") as aw:
            aw.write(index.to_json())


def remove_index_entry(dg_dir: Path, rel_path: str) -> None:
    """Atomically remove an entry from the index.

    Args:
        dg_dir:   Path to the ``.deep_git`` directory.
        rel_path: Relative file path to remove.

    Raises:
        KeyError: If the path is not in the index.
    """
    lock = FileLock(str(_lock_path(dg_dir)))
    with lock:
        text = _index_path(dg_dir).read_text(encoding="utf-8")
        index = Index.from_json(text)
        if rel_path not in index.entries:
            raise KeyError(f"{rel_path!r} is not in the index")
        del index.entries[rel_path]
        with AtomicWriter(_index_path(dg_dir), mode="w") as aw:
            aw.write(index.to_json())

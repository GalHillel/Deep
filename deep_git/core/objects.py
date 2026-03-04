"""
deep_git.core.objects
~~~~~~~~~~~~~~~~~~~~~
Content-addressable object model: **Blob**, **Tree**, and **Commit**.

Serialisation follows Git's wire format::

    <type> <size>\0<content>

Objects are stored under ``.deep_git/objects/<xx>/<yy…>`` where ``xx`` is the
first two hex characters of the SHA-1 hash and ``yy…`` is the remainder.
"""

from __future__ import annotations

import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from deep_git.core.utils import AtomicWriter, get_local_timezone_offset, hash_bytes


# ── Helpers ──────────────────────────────────────────────────────────

def _object_path(objects_dir: Path, sha: str) -> Path:
    """Return the path ``objects/<xx>/<yy…>`` for a given SHA-1 hex digest."""
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
    """Abstract base for all content-addressable objects."""

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
        """Persist this object to disk under *objects_dir*.

        Returns:
            The SHA-1 hex digest of the written object.
        """
        raw = self.full_serialize()
        sha = hash_bytes(raw)
        dest = _object_path(objects_dir, sha)
        if dest.exists():
            return sha  # already stored — content-addressable
        compressed = zlib.compress(raw)
        with AtomicWriter(dest) as aw:
            aw.write(compressed)
        return sha


# ── Blob ─────────────────────────────────────────────────────────────

@dataclass
class Blob(GitObject):
    """A blob stores the raw contents of a single file."""

    OBJ_TYPE: str = field(init=False, default="blob", repr=False)
    data: bytes = b""

    def serialize_content(self) -> bytes:
        return self.data


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


@dataclass
class Tree(GitObject):
    """A tree maps names to blobs (files) or other trees (directories)."""

    OBJ_TYPE: str = field(init=False, default="tree", repr=False)
    entries: List[TreeEntry] = field(default_factory=list)

    def serialize_content(self) -> bytes:
        """Serialize entries sorted by name, Git-style.

        Each entry is::

            <mode> <name>\\0<20-byte raw SHA-1>
        """
        parts: list[bytes] = []
        for entry in sorted(self.entries, key=lambda e: e.name):
            sha_bytes = bytes.fromhex(entry.sha)
            parts.append(
                f"{entry.mode} {entry.name}".encode("utf-8")
                + b"\x00"
                + sha_bytes
            )
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
    author: str = "Deep Git User <user@deepgit>"
    committer: str = "Deep Git User <user@deepgit>"
    message: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time()))
    timezone: str = field(default_factory=get_local_timezone_offset)

    def serialize_content(self) -> bytes:
        lines: list[str] = [f"tree {self.tree_sha}"]
        for p in self.parent_shas:
            lines.append(f"parent {p}")
        lines.append(f"author {self.author} {self.timestamp} {self.timezone}")
        lines.append(
            f"committer {self.committer} {self.timestamp} {self.timezone}"
        )
        lines.append("")
        lines.append(self.message)
        return "\n".join(lines).encode("utf-8")

    @classmethod
    def from_content(cls, content: bytes) -> "Commit":
        """Deserialise commit content bytes back into a :class:`Commit`."""
        text = content.decode("utf-8")
        headers, message = text.split("\n\n", 1)
        tree_sha = ""
        parent_shas: list[str] = []
        author = ""
        committer = ""
        timestamp = 0
        timezone = "+0000"
        for line in headers.split("\n"):
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
        return cls(
            tree_sha=tree_sha,
            parent_shas=parent_shas,
            author=author,
            committer=committer,
            message=message,
            timestamp=timestamp,
            timezone=timezone,
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
    timezone: str = field(default_factory=get_local_timezone_offset)

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


# ── Read from disk ──────────────────────────────────────────────────

def read_object(objects_dir: Path, sha: str) -> GitObject:
    """Read and deserialise an object from the object store."""
    path = _object_path(objects_dir, sha)
    compressed = path.read_bytes()
    raw = zlib.decompress(compressed)
    obj_type, content = _deserialize(raw)

    if obj_type == "blob":
        return Blob(data=content)
    elif obj_type == "tree":
        return Tree.from_content(content)
    elif obj_type == "commit":
        return Commit.from_content(content)
    elif obj_type == "tag":
        return Tag.from_content(content)
    else:
        raise ValueError(f"Unknown object type: {obj_type!r}")

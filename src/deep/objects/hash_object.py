"""
deep.objects.hash_object
~~~~~~~~~~~~~~~~~~~~~~~~

Git-compatible object hashing, reading and writing.

Objects are stored in the canonical Git format:
    <type> <size>\0<content>

Hashed with SHA-1 and stored zlib-compressed under:
    .deep/objects/xx/yyyy...  (Level 1 fan-out, Git-compatible)
"""

from __future__ import annotations

import hashlib
import os
import zlib
from pathlib import Path
from typing import Tuple, Optional


def hash_object(data: bytes, obj_type: str = "blob") -> str:
    """Compute the SHA-1 hash of a Git object.

    Args:
        data: Raw content bytes (without header).
        obj_type: Object type string ("blob", "tree", "commit", "tag").

    Returns:
        40-character lowercase hex SHA-1 digest.
    """
    header = f"{obj_type} {len(data)}".encode("ascii")
    store = header + b"\x00" + data
    return hashlib.sha1(store).hexdigest()


def format_object(data: bytes, obj_type: str = "blob") -> bytes:
    """Format data as a Git object (header + null + content).

    Returns:
        The full serialized object bytes.
    """
    header = f"{obj_type} {len(data)}".encode("ascii")
    return header + b"\x00" + data


def write_object(objects_dir: Path, data: bytes, obj_type: str = "blob") -> str:
    """Write a Git-format object to the object store.

    Uses Level 1 fan-out (xx/yyyy...) matching Git's standard layout.

    Args:
        objects_dir: Path to the objects directory (.deep/objects/).
        data: Raw content bytes (without header).
        obj_type: Object type string.

    Returns:
        40-character hex SHA-1 of the written object.
    """
    store = format_object(data, obj_type)
    sha = hashlib.sha1(store).hexdigest()

    # Git-compatible Level 1 fan-out: objects/xx/yyyy...
    dest = objects_dir / sha[0:2] / sha[2:]
    if dest.exists():
        return sha

    dest.parent.mkdir(parents=True, exist_ok=True)
    compressed = zlib.compress(store)

    # Atomic write via temp file
    tmp_path = dest.with_suffix(".tmp")
    try:
        tmp_path.write_bytes(compressed)
        os.replace(str(tmp_path), str(dest))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return sha


def read_raw_object(objects_dir: Path, sha: str) -> Tuple[str, bytes]:
    """Read a raw Git object from the object store.

    Tries Level 1 fan-out first (xx/yyyy...), then Level 2 (xx/yy/zzzz...).

    Args:
        objects_dir: Path to the objects directory.
        sha: 40-character hex SHA-1 digest.

    Returns:
        Tuple of (obj_type, content_bytes).

    Raises:
        FileNotFoundError: If object is not found in loose storage.
        ValueError: If object is corrupted.
    """
    if not sha or len(sha) != 40:
        raise ValueError(f"Invalid SHA: {sha!r}")

    # Try Level 1 fan-out (Git standard)
    path = objects_dir / sha[0:2] / sha[2:]
    if not path.exists():
        # Try Level 2 fan-out (Deep legacy)
        path = objects_dir / sha[0:2] / sha[2:4] / sha[4:]
        if not path.exists():
            raise FileNotFoundError(f"Object {sha} not found")

    raw_compressed = path.read_bytes()
    try:
        raw = zlib.decompress(raw_compressed)
    except zlib.error:
        # Might be uncompressed (legacy)
        raw = raw_compressed

    # Verify hash
    actual_sha = hashlib.sha1(raw).hexdigest()
    if actual_sha != sha:
        raise ValueError(f"Corrupt object {sha}: hash mismatch (got {actual_sha})")

    # Parse header
    null_idx = raw.index(b"\x00")
    header = raw[:null_idx].decode("ascii")
    obj_type, size_str = header.split(" ", 1)
    size = int(size_str)
    content = raw[null_idx + 1:]
    if len(content) != size:
        raise ValueError(f"Object {sha}: size mismatch (header={size}, actual={len(content)})")

    return obj_type, content


def write_raw_object(objects_dir: Path, sha: str, compressed_data: bytes) -> None:
    """Write already-compressed object data directly to the store.

    Used when importing objects from packfiles where we already have
    the compressed representation.
    """
    dest = objects_dir / sha[0:2] / sha[2:]
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = dest.with_suffix(".tmp")
    try:
        tmp_path.write_bytes(compressed_data)
        os.replace(str(tmp_path), str(dest))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def object_exists(objects_dir: Path, sha: str) -> bool:
    """Check if an object exists in the store (loose only)."""
    if not sha or len(sha) != 40:
        return False
    # Level 1
    if (objects_dir / sha[0:2] / sha[2:]).exists():
        return True
    # Level 2 (Deep legacy)
    if (objects_dir / sha[0:2] / sha[2:4] / sha[4:]).exists():
        return True
    return False

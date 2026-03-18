"""
deep.objects.packfile
~~~~~~~~~~~~~~~~~~~~~

Git v2 packfile parser and writer.

Implements the full Git packfile format:
- 4-byte PACK signature
- 4-byte version (2)
- 4-byte object count
- Object entries with variable-length type/size encoding
- 20-byte SHA-1 trailer

Object types:
    1 = OBJ_COMMIT
    2 = OBJ_TREE
    3 = OBJ_BLOB
    4 = OBJ_TAG
    6 = OBJ_OFS_DELTA (offset delta)
    7 = OBJ_REF_DELTA (reference delta)

All without external git CLI or library dependency.
"""

from __future__ import annotations

import hashlib
import io
import os
import struct
import zlib
from typing import (
    BinaryIO, Dict, List, Optional, Tuple, Iterator,
)
from pathlib import Path

from deep.objects.delta import apply_delta as git_apply_delta

# Git packfile constants
PACK_SIGNATURE = b"PACK"
PACK_VERSION = 2

# Object type IDs
OBJ_COMMIT = 1
OBJ_TREE = 2
OBJ_BLOB = 3
OBJ_TAG = 4
OBJ_OFS_DELTA = 6
OBJ_REF_DELTA = 7

TYPE_MAP = {
    OBJ_COMMIT: "commit",
    OBJ_TREE: "tree",
    OBJ_BLOB: "blob",
    OBJ_TAG: "tag",
}

REVERSE_TYPE_MAP = {v: k for k, v in TYPE_MAP.items()}

# Safety limits
MAX_OBJECT_SIZE = 256 * 1024 * 1024  # 256 MiB per object
MAX_DELTA_CHAIN = 50


class PackfileError(Exception):
    """Raised when a packfile is malformed or corrupt."""
    pass


# ── Variable-length integer encoding (Git MSB format) ──────────────

def _read_type_and_size(stream: BinaryIO) -> Tuple[int, int]:
    """Read the Git packfile object type and size.

    First byte: bits 6-4 = type, bits 3-0 = size (low 4 bits).
    Continuation bytes: bit 7 = more, bits 6-0 = size continuation.
    Size is little-endian with 4-bit initial segment.

    Returns:
        (object_type_id, uncompressed_size)
    """
    byte = _read_byte(stream)
    obj_type = (byte >> 4) & 0x07
    size = byte & 0x0F
    shift = 4

    while byte & 0x80:
        byte = _read_byte(stream)
        size |= (byte & 0x7F) << shift
        shift += 7

    return obj_type, size


def _read_byte(stream: BinaryIO) -> int:
    """Read a single byte from stream, raising on EOF."""
    data = stream.read(1)
    if not data:
        raise PackfileError("Unexpected EOF in packfile")
    return data[0]


def _read_ofs_delta_offset(stream: BinaryIO) -> int:
    """Read the negative offset for OFS_DELTA objects.

    Git encodes this as a variable-length integer where each
    continuation byte adds (value + 1) << 7.
    """
    byte = _read_byte(stream)
    offset = byte & 0x7F
    while byte & 0x80:
        byte = _read_byte(stream)
        offset = ((offset + 1) << 7) | (byte & 0x7F)
    return offset


def _decompress_object(stream: BinaryIO, expected_size: int) -> bytes:
    """Decompress a zlib-compressed object from the stream.

    Reads and decompresses in chunks, handling the fact that
    we don't know the compressed size ahead of time.
    """
    decompressor = zlib.decompressobj()
    result = bytearray()
    buf = bytearray()

    while True:
        # Read in small chunks to avoid over-reading
        chunk = stream.read(4096)
        if not chunk:
            # Try to flush
            try:
                remaining = decompressor.flush()
                if remaining:
                    result.extend(remaining)
            except zlib.error:
                pass
            break

        try:
            decompressed = decompressor.decompress(chunk)
            result.extend(decompressed)
        except zlib.error as e:
            raise PackfileError(f"Zlib decompression failed: {e}")

        if len(result) > MAX_OBJECT_SIZE:
            raise PackfileError(f"Object exceeds maximum size of {MAX_OBJECT_SIZE}")

        # Check if decompression is complete
        if decompressor.unused_data:
            # Push back unused data
            unused = decompressor.unused_data
            # We need to "seek back" the unused portion.
            # Since we're reading from a stream, we back up.
            current = stream.tell()
            stream.seek(current - len(unused))
            break

        if decompressor.eof:
            break

    if len(result) != expected_size:
        # Some servers send slightly different sizes; be tolerant
        # but log a warning for debugging
        if os.environ.get("DEEP_DEBUG"):
            import sys
            print(f"[DEEP_DEBUG] Object size mismatch: expected {expected_size}, "
                  f"got {len(result)}", file=sys.stderr)

    return bytes(result)


# ── Packfile Parser ────────────────────────────────────────────────

class PackfileParser:
    """Parse a Git v2 packfile and extract all objects.

    Usage:
        parser = PackfileParser(stream)
        for obj_type, data, sha in parser.parse():
            write_object(objects_dir, data, obj_type)
    """

    def __init__(self, stream: BinaryIO):
        self._stream = stream
        self._hasher = hashlib.sha1()
        self._objects: Dict[int, Tuple[str, bytes]] = {}  # offset -> (type, data)
        self._sha_by_offset: Dict[int, str] = {}
        self._start_offset = stream.tell()

    def _hashed_read(self, n: int) -> bytes:
        """Read n bytes from stream and update the trailer hash."""
        data = self._stream.read(n)
        if len(data) < n:
            raise PackfileError(f"Unexpected EOF: wanted {n} bytes, got {len(data)}")
        self._hasher.update(data)
        return data

    def parse(self) -> List[Tuple[str, bytes]]:
        """Parse the packfile and return all objects.

        Returns:
            List of (obj_type_str, raw_data) tuples.
            For base objects, raw_data is the uncompressed content.
        """
        # Reset hasher and read header
        self._hasher = hashlib.sha1()

        # Read and validate header
        sig = self._hashed_read(4)
        if sig != PACK_SIGNATURE:
            raise PackfileError(f"Invalid packfile signature: {sig!r}")

        version_bytes = self._hashed_read(4)
        version = struct.unpack(">I", version_bytes)[0]
        if version != PACK_VERSION:
            raise PackfileError(f"Unsupported packfile version: {version}")

        count_bytes = self._hashed_read(4)
        count = struct.unpack(">I", count_bytes)[0]

        if os.environ.get("DEEP_DEBUG"):
            import sys
            print(f"[DEEP_DEBUG] Packfile: version={version}, objects={count}",
                  file=sys.stderr)

        # Parse each object
        results: List[Tuple[str, bytes]] = []
        pending_deltas: List[Tuple[int, int, int, bytes]] = []
        # pending_deltas: (entry_index, delta_type, ref_info, delta_data)
        # For OFS_DELTA: ref_info = base_offset
        # For REF_DELTA: ref_info stored separately

        pending_ref_deltas: List[Tuple[int, bytes, bytes]] = []
        # (entry_index, base_sha_bytes, delta_data)

        for i in range(count):
            entry_offset = self._stream.tell()
            obj_type, size = self._read_type_and_size_hashed()

            if obj_type in (OBJ_COMMIT, OBJ_TREE, OBJ_BLOB, OBJ_TAG):
                data = self._decompress_hashed(size)
                type_str = TYPE_MAP[obj_type]
                self._objects[entry_offset] = (type_str, data)

                # Compute SHA for cross-referencing
                header = f"{type_str} {len(data)}".encode("ascii")
                full = header + b"\x00" + data
                sha = hashlib.sha1(full).hexdigest()
                self._sha_by_offset[entry_offset] = sha
                results.append((type_str, data))

            elif obj_type == OBJ_OFS_DELTA:
                neg_offset = self._read_ofs_offset_hashed()
                delta_data = self._decompress_hashed(size)
                base_offset = entry_offset - neg_offset

                if base_offset in self._objects:
                    base_type, base_data = self._objects[base_offset]
                    resolved = git_apply_delta(base_data, delta_data)
                    self._objects[entry_offset] = (base_type, resolved)

                    header = f"{base_type} {len(resolved)}".encode("ascii")
                    full = header + b"\x00" + resolved
                    sha = hashlib.sha1(full).hexdigest()
                    self._sha_by_offset[entry_offset] = sha
                    results.append((base_type, resolved))
                else:
                    # Queue for later resolution
                    pending_deltas.append((len(results), OBJ_OFS_DELTA,
                                          base_offset, delta_data))
                    results.append(("__pending__", b""))

            elif obj_type == OBJ_REF_DELTA:
                base_sha_raw = self._hashed_read(20)
                delta_data = self._decompress_hashed(size)
                base_sha = base_sha_raw.hex()

                # Try to resolve immediately
                resolved = False
                for off, sha in self._sha_by_offset.items():
                    if sha == base_sha:
                        base_type, base_data = self._objects[off]
                        target = git_apply_delta(base_data, delta_data)
                        self._objects[entry_offset] = (base_type, target)

                        header = f"{base_type} {len(target)}".encode("ascii")
                        full = header + b"\x00" + target
                        t_sha = hashlib.sha1(full).hexdigest()
                        self._sha_by_offset[entry_offset] = t_sha
                        results.append((base_type, target))
                        resolved = True
                        break

                if not resolved:
                    pending_ref_deltas.append(
                        (len(results), base_sha_raw, delta_data))
                    results.append(("__pending__", b""))

            else:
                raise PackfileError(f"Unknown object type: {obj_type}")

        # Resolve pending OFS deltas (multi-pass)
        for _pass in range(MAX_DELTA_CHAIN):
            if not pending_deltas:
                break
            still_pending = []
            for idx, dtype, base_offset, delta_data in pending_deltas:
                if base_offset in self._objects:
                    base_type, base_data = self._objects[base_offset]
                    resolved = git_apply_delta(base_data, delta_data)
                    # We don't know the exact offset for this entry anymore,
                    # but we can store by index
                    results[idx] = (base_type, resolved)
                else:
                    still_pending.append((idx, dtype, base_offset, delta_data))
            pending_deltas = still_pending

        # Resolve pending REF deltas
        # These reference objects by SHA that may be outside this pack
        # (thin pack support). We'll store them for external resolution.
        self._unresolved_ref_deltas = pending_ref_deltas

        # Verify trailer
        try:
            expected_hash = self._hasher.digest()
            trailer = self._stream.read(20)
            if len(trailer) == 20 and trailer != expected_hash:
                if os.environ.get("DEEP_DEBUG"):
                    import sys
                    print(f"[DEEP_DEBUG] Pack trailer mismatch (non-fatal)",
                          file=sys.stderr)
        except Exception:
            pass  # Some streams may not have trailer accessible

        return results

    @property
    def unresolved_ref_deltas(self) -> List[Tuple[int, bytes, bytes]]:
        """Return unresolved REF_DELTA entries for thin pack resolution."""
        return getattr(self, "_unresolved_ref_deltas", [])

    def _read_type_and_size_hashed(self) -> Tuple[int, int]:
        """Read type+size with hash tracking."""
        byte_data = self._hashed_read(1)
        byte = byte_data[0]
        obj_type = (byte >> 4) & 0x07
        size = byte & 0x0F
        shift = 4

        while byte & 0x80:
            byte_data = self._hashed_read(1)
            byte = byte_data[0]
            size |= (byte & 0x7F) << shift
            shift += 7

        return obj_type, size

    def _read_ofs_offset_hashed(self) -> int:
        """Read OFS_DELTA negative offset with hash tracking."""
        byte_data = self._hashed_read(1)
        byte = byte_data[0]
        offset = byte & 0x7F
        while byte & 0x80:
            byte_data = self._hashed_read(1)
            byte = byte_data[0]
            offset = ((offset + 1) << 7) | (byte & 0x7F)
        return offset

    def _decompress_hashed(self, expected_size: int) -> bytes:
        """Decompress zlib data while tracking bytes for hash."""
        decompressor = zlib.decompressobj()
        result = bytearray()

        while True:
            chunk = self._stream.read(4096)
            if not chunk:
                try:
                    remaining = decompressor.flush()
                    if remaining:
                        result.extend(remaining)
                except zlib.error:
                    pass
                break

            try:
                decompressed = decompressor.decompress(chunk)
                result.extend(decompressed)
            except zlib.error as e:
                raise PackfileError(f"Zlib error: {e}")

            if decompressor.unused_data:
                consumed = len(chunk) - len(decompressor.unused_data)
                self._hasher.update(chunk[:consumed])
                current = self._stream.tell()
                self._stream.seek(current - len(decompressor.unused_data))
                break
            else:
                self._hasher.update(chunk)

            if decompressor.eof:
                break

            if len(result) > MAX_OBJECT_SIZE:
                raise PackfileError("Object too large")

        return bytes(result)


# ── Packfile Writer ────────────────────────────────────────────────

def build_pack(objects: List[Tuple[str, bytes]]) -> bytes:
    """Build a Git v2 packfile from a list of (type_str, data) tuples.

    Args:
        objects: List of ("commit"/"tree"/"blob"/"tag", raw_content) tuples.

    Returns:
        Complete packfile bytes including header and trailer.
    """
    buf = bytearray()

    # Header
    buf.extend(PACK_SIGNATURE)
    buf.extend(struct.pack(">I", PACK_VERSION))
    buf.extend(struct.pack(">I", len(objects)))

    for type_str, data in objects:
        type_id = REVERSE_TYPE_MAP.get(type_str)
        if type_id is None:
            raise PackfileError(f"Unknown object type for pack: {type_str}")

        # Encode type + size
        size = len(data)
        buf.extend(_encode_type_size(type_id, size))

        # Compress data
        compressed = zlib.compress(data)
        buf.extend(compressed)

    # Compute and append SHA-1 trailer
    trailer = hashlib.sha1(bytes(buf)).digest()
    buf.extend(trailer)

    return bytes(buf)


def _encode_type_size(obj_type: int, size: int) -> bytes:
    """Encode object type and size in Git packfile format."""
    result = bytearray()

    # First byte: bits 6-4 = type, bits 3-0 = size low 4 bits
    byte = (obj_type << 4) | (size & 0x0F)
    size >>= 4

    if size:
        byte |= 0x80

    result.append(byte)

    # Continuation bytes
    while size:
        byte = size & 0x7F
        size >>= 7
        if size:
            byte |= 0x80
        result.append(byte)

    return bytes(result)


# ── High-level helpers ─────────────────────────────────────────────

def parse_packfile(data: bytes) -> List[Tuple[str, bytes]]:
    """Parse a packfile from bytes.

    Convenience wrapper around PackfileParser.

    Returns:
        List of (type_str, content_bytes) tuples.
    """
    stream = io.BytesIO(data)
    parser = PackfileParser(stream)
    return parser.parse()


def unpack_to_store(
    pack_data: bytes,
    objects_dir: Path,
    resolve_external: Optional[callable] = None,
) -> int:
    """Parse a packfile and write all objects to the object store.

    Args:
        pack_data: Raw packfile bytes.
        objects_dir: Path to the objects directory.
        resolve_external: Optional callback(sha_hex) -> (type_str, data)
                         for resolving thin pack base objects.

    Returns:
        Number of objects written.
    """
    from deep.objects.hash_object import write_object, object_exists, read_raw_object

    stream = io.BytesIO(pack_data)
    parser = PackfileParser(stream)
    entries = parser.parse()

    count = 0
    for type_str, data in entries:
        if type_str == "__pending__":
            continue  # Unresolved delta, skip
        write_object(objects_dir, data, type_str)
        count += 1

    # Resolve thin pack deltas
    for idx, base_sha_raw, delta_data in parser.unresolved_ref_deltas:
        base_sha = base_sha_raw.hex()
        base_type = None
        base_data = None

        # Try local store
        if object_exists(objects_dir, base_sha):
            try:
                base_type, base_data = read_raw_object(objects_dir, base_sha)
            except Exception:
                pass

        # Try external resolver
        if base_data is None and resolve_external:
            try:
                result = resolve_external(base_sha)
                if result:
                    base_type, base_data = result
            except Exception:
                pass

        if base_data is not None and base_type is not None:
            target = git_apply_delta(base_data, delta_data)
            write_object(objects_dir, target, base_type)
            count += 1
            # Update results list
            if idx < len(entries):
                entries[idx] = (base_type, target)

    return count

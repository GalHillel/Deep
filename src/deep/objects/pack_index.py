"""
deep.objects.pack_index
~~~~~~~~~~~~~~~~~~~~~~~

Git pack index (.idx) file format, version 2.

Provides:
- PackIndex: read and query existing .idx files
- PackIndexWriter: create new .idx files from packfile data

Index format (v2):
    4-byte magic: ff 74 4f 63
    4-byte version: 2
    256 x 4-byte fanout table
    N x 20-byte SHA-1 entries (sorted)
    N x 4-byte CRC32 entries
    N x 4-byte offset entries (MSB set = large offset table)
    Large offset entries (8-byte, if any)
    20-byte packfile SHA-1
    20-byte index SHA-1
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple


IDX_MAGIC = b"\xff\x74\x4f\x63"
IDX_VERSION = 2


class PackIndex:
    """Read and query a Git pack index file."""

    def __init__(self, idx_path: Path):
        self._path = idx_path
        self._data = idx_path.read_bytes()
        self._validate()
        self._count = self._get_count()

    def _validate(self) -> None:
        if len(self._data) < 8:
            raise ValueError("Index file too small")
        if self._data[:4] != IDX_MAGIC:
            raise ValueError(f"Invalid index magic: {self._data[:4]!r}")
        version = struct.unpack(">I", self._data[4:8])[0]
        if version != IDX_VERSION:
            raise ValueError(f"Unsupported index version: {version}")

    def _get_count(self) -> int:
        """Total number of objects (from fanout[255])."""
        offset = 8 + 255 * 4
        return struct.unpack(">I", self._data[offset:offset + 4])[0]

    @property
    def count(self) -> int:
        return self._count

    def find_offset(self, sha_hex: str) -> Optional[int]:
        """Find the packfile offset for a given SHA-1.

        Returns:
            The byte offset into the packfile, or None if not found.
        """
        sha_bytes = bytes.fromhex(sha_hex)
        first_byte = sha_bytes[0]

        # Get bounds from fanout table
        fanout_base = 8
        if first_byte == 0:
            start = 0
        else:
            start = struct.unpack(
                ">I", self._data[fanout_base + (first_byte - 1) * 4:
                                  fanout_base + first_byte * 4]
            )[0]
        end = struct.unpack(
            ">I", self._data[fanout_base + first_byte * 4:
                              fanout_base + (first_byte + 1) * 4]
        )[0]

        # SHA table starts after fanout (8 + 256*4 = 1032)
        sha_table_start = 1032
        # Binary search
        lo, hi = start, end
        while lo < hi:
            mid = (lo + hi) // 2
            entry_sha = self._data[sha_table_start + mid * 20:
                                    sha_table_start + (mid + 1) * 20]
            if entry_sha == sha_bytes:
                return self._get_offset(mid)
            elif entry_sha < sha_bytes:
                lo = mid + 1
            else:
                hi = mid

        return None

    def _get_offset(self, index: int) -> int:
        """Get the packfile offset for the entry at the given position."""
        # CRC table: after SHA table
        crc_table_start = 1032 + self._count * 20
        # Offset table: after CRC table
        offset_table_start = crc_table_start + self._count * 4

        raw_offset = struct.unpack(
            ">I", self._data[offset_table_start + index * 4:
                              offset_table_start + (index + 1) * 4]
        )[0]

        if raw_offset & 0x80000000:
            # Large offset — look up in the 8-byte table
            large_idx = raw_offset & 0x7FFFFFFF
            large_offset_start = offset_table_start + self._count * 4
            return struct.unpack(
                ">Q", self._data[large_offset_start + large_idx * 8:
                                  large_offset_start + (large_idx + 1) * 8]
            )[0]

        return raw_offset

    def all_shas(self) -> List[str]:
        """Return all SHA-1 hex strings in the index (sorted)."""
        sha_start = 1032
        return [
            self._data[sha_start + i * 20:sha_start + (i + 1) * 20].hex()
            for i in range(self._count)
        ]


class PackIndexWriter:
    """Create a Git pack index (v2) from a list of (sha, offset, crc32) entries."""

    @staticmethod
    def create(
        entries: List[Tuple[str, int, int]],
        pack_sha: bytes,
    ) -> bytes:
        """Build a .idx file.

        Args:
            entries: List of (sha_hex, pack_offset, crc32) tuples.
            pack_sha: 20-byte SHA-1 of the packfile.

        Returns:
            Complete .idx file bytes.
        """
        # Sort entries by SHA
        sorted_entries = sorted(entries, key=lambda e: bytes.fromhex(e[0]))

        buf = bytearray()

        # Magic + version
        buf.extend(IDX_MAGIC)
        buf.extend(struct.pack(">I", IDX_VERSION))

        # Build fanout table
        fanout = [0] * 256
        for sha_hex, _, _ in sorted_entries:
            first_byte = int(sha_hex[:2], 16)
            fanout[first_byte] += 1

        # Convert to cumulative
        for i in range(1, 256):
            fanout[i] += fanout[i - 1]

        for count in fanout:
            buf.extend(struct.pack(">I", count))

        # SHA table
        for sha_hex, _, _ in sorted_entries:
            buf.extend(bytes.fromhex(sha_hex))

        # CRC32 table
        for _, _, crc in sorted_entries:
            buf.extend(struct.pack(">I", crc & 0xFFFFFFFF))

        # Offset table
        large_offsets = []
        for _, offset, _ in sorted_entries:
            if offset >= 0x80000000:
                large_idx = len(large_offsets)
                large_offsets.append(offset)
                buf.extend(struct.pack(">I", 0x80000000 | large_idx))
            else:
                buf.extend(struct.pack(">I", offset))

        # Large offset table
        for offset in large_offsets:
            buf.extend(struct.pack(">Q", offset))

        # Packfile SHA
        buf.extend(pack_sha)

        # Index SHA
        idx_sha = hashlib.sha1(bytes(buf)).digest()
        buf.extend(idx_sha)

        return bytes(buf)

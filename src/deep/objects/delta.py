"""
deep.objects.delta
~~~~~~~~~~~~~~~~~~

Git-compatible delta compression engine.

Implements the Git delta format used inside packfiles:
- Variable-length size encoding for source/target sizes
- COPY instructions (high bit set): copy from base object
- INSERT instructions (high bit clear): insert literal data

This is the standard Git OFS_DELTA / REF_DELTA undelta format.
"""

from __future__ import annotations

import struct
from typing import Tuple


def _read_varint_le(data: bytes, offset: int) -> Tuple[int, int]:
    """Read a Git-style variable-length integer (little-endian, MSB continuation).

    Each byte contributes 7 bits. The high bit indicates more bytes follow.

    Returns:
        (value, new_offset)
    """
    value = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("Truncated varint in delta")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            break
    return value, offset


def apply_delta(base: bytes, delta: bytes) -> bytes:
    """Apply a Git delta to a base object to produce the target.

    The delta format is:
    1. Source (base) size — varint
    2. Target size — varint
    3. Instructions stream:
       - If high bit set (0x80): COPY instruction
         Bits 0-3 select which offset bytes follow (1,2,4 byte positions)
         Bits 4-6 select which size bytes follow
       - If high bit clear and non-zero: INSERT instruction
         The byte value is the count of literal bytes to insert
       - Zero byte is reserved/invalid

    Args:
        base: The base object data.
        delta: The delta instruction stream.

    Returns:
        The reconstructed target data.

    Raises:
        ValueError: If the delta is malformed.
    """
    if not delta:
        raise ValueError("Empty delta")

    idx = 0

    # Read source size
    source_size, idx = _read_varint_le(delta, idx)
    if source_size != len(base):
        raise ValueError(
            f"Delta source size mismatch: expected {source_size}, got {len(base)}"
        )

    # Read target size
    target_size, idx = _read_varint_le(delta, idx)

    out = bytearray()

    while idx < len(delta):
        cmd = delta[idx]
        idx += 1

        if cmd & 0x80:
            # COPY instruction
            # Decode offset (up to 4 bytes, selected by bits 0-3)
            copy_offset = 0
            if cmd & 0x01:
                copy_offset = delta[idx]
                idx += 1
            if cmd & 0x02:
                copy_offset |= delta[idx] << 8
                idx += 1
            if cmd & 0x04:
                copy_offset |= delta[idx] << 16
                idx += 1
            if cmd & 0x08:
                copy_offset |= delta[idx] << 24
                idx += 1

            # Decode size (up to 3 bytes, selected by bits 4-6)
            copy_size = 0
            if cmd & 0x10:
                copy_size = delta[idx]
                idx += 1
            if cmd & 0x20:
                copy_size |= delta[idx] << 8
                idx += 1
            if cmd & 0x40:
                copy_size |= delta[idx] << 16
                idx += 1

            # Size of 0 means 0x10000 (65536) in Git's encoding
            if copy_size == 0:
                copy_size = 0x10000

            if copy_offset + copy_size > len(base):
                raise ValueError(
                    f"Delta copy out of bounds: offset={copy_offset}, "
                    f"size={copy_size}, base_len={len(base)}"
                )

            out.extend(base[copy_offset:copy_offset + copy_size])

        elif cmd > 0:
            # INSERT instruction: cmd is the number of literal bytes
            if idx + cmd > len(delta):
                raise ValueError("Delta insert extends past end of delta data")
            out.extend(delta[idx:idx + cmd])
            idx += cmd

        else:
            # cmd == 0 is reserved
            raise ValueError("Invalid delta command byte: 0x00")

    if len(out) != target_size:
        raise ValueError(
            f"Delta target size mismatch: expected {target_size}, got {len(out)}"
        )

    return bytes(out)


def create_delta(source: bytes, target: bytes) -> bytes:
    """Create a Git-format delta that transforms source into target.

    Uses a simple rolling-hash approach to find matching blocks.

    Args:
        source: The base content.
        target: The desired target content.

    Returns:
        Delta instruction bytes in Git format.
    """
    delta = bytearray()

    # Write source size
    delta.extend(_encode_varint_le(len(source)))
    # Write target size
    delta.extend(_encode_varint_le(len(target)))

    BLOCK_SIZE = 16
    if len(source) < BLOCK_SIZE or len(target) < BLOCK_SIZE:
        # Fall back to pure insert
        _emit_inserts(delta, target, 0, len(target))
        return bytes(delta)

    # Build hash index for source
    source_index: dict[int, list[int]] = {}
    PRIME = 0x01000193
    MASK = 0xFFFFFFFF

    def _hash_block(data: bytes, start: int, size: int) -> int:
        h = 0
        for i in range(start, start + size):
            h = ((h ^ data[i]) * PRIME) & MASK
        return h

    for i in range(0, len(source) - BLOCK_SIZE + 1, BLOCK_SIZE):
        h = _hash_block(source, i, BLOCK_SIZE)
        source_index.setdefault(h, []).append(i)

    t_idx = 0
    insert_start = 0

    while t_idx <= len(target) - BLOCK_SIZE:
        h = _hash_block(target, t_idx, BLOCK_SIZE)

        best_offset = -1
        best_length = 0

        if h in source_index:
            t_block = target[t_idx:t_idx + BLOCK_SIZE]
            for s_off in source_index[h]:
                if source[s_off:s_off + BLOCK_SIZE] == t_block:
                    # Extend match forward
                    match_len = BLOCK_SIZE
                    while (t_idx + match_len < len(target) and
                           s_off + match_len < len(source) and
                           target[t_idx + match_len] == source[s_off + match_len]):
                        match_len += 1
                    if match_len > best_length:
                        best_length = match_len
                        best_offset = s_off

        if best_length >= BLOCK_SIZE:
            # Emit pending inserts
            if t_idx > insert_start:
                _emit_inserts(delta, target, insert_start, t_idx)

            # Emit COPY
            _emit_copy(delta, best_offset, best_length)
            t_idx += best_length
            insert_start = t_idx
        else:
            t_idx += 1

    # Emit remaining inserts
    if insert_start < len(target):
        _emit_inserts(delta, target, insert_start, len(target))

    return bytes(delta)


def _encode_varint_le(value: int) -> bytes:
    """Encode an integer as Git-style variable-length LE bytes."""
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        result.append(byte)
        if not value:
            break
    return bytes(result)


def _emit_inserts(delta: bytearray, data: bytes, start: int, end: int) -> None:
    """Emit INSERT instructions for data[start:end]."""
    pos = start
    while pos < end:
        # Max insert size per instruction is 127 (7 bits, high bit must be 0)
        chunk_size = min(end - pos, 127)
        delta.append(chunk_size)
        delta.extend(data[pos:pos + chunk_size])
        pos += chunk_size


def _emit_copy(delta: bytearray, offset: int, size: int) -> None:
    """Emit a COPY instruction with Git's bitmask encoding."""
    cmd = 0x80
    offset_bytes = bytearray()
    size_bytes = bytearray()

    # Encode offset (up to 4 bytes)
    if offset & 0xFF:
        cmd |= 0x01
        offset_bytes.append(offset & 0xFF)
    if offset & 0xFF00:
        cmd |= 0x02
        offset_bytes.append((offset >> 8) & 0xFF)
    if offset & 0xFF0000:
        cmd |= 0x04
        offset_bytes.append((offset >> 16) & 0xFF)
    if offset & 0xFF000000:
        cmd |= 0x08
        offset_bytes.append((offset >> 24) & 0xFF)

    # Encode size (up to 3 bytes, 0 means 65536)
    actual_size = size
    if actual_size == 0x10000:
        actual_size = 0  # Special encoding

    if actual_size & 0xFF:
        cmd |= 0x10
        size_bytes.append(actual_size & 0xFF)
    if actual_size & 0xFF00:
        cmd |= 0x20
        size_bytes.append((actual_size >> 8) & 0xFF)
    if actual_size & 0xFF0000:
        cmd |= 0x40
        size_bytes.append((actual_size >> 16) & 0xFF)

    # Handle case where all offset and size bytes are zero
    # (offset=0, size=65536) -> cmd=0x80 only, which is "copy 65536 from 0"
    # That's still valid.

    delta.append(cmd)
    delta.extend(offset_bytes)
    delta.extend(size_bytes)

"""
deep.core.delta
~~~~~~~~~~~~~~~~~~~~~
Delta compression engine for space-efficient object storage.

Based on instruction-based diffs:
- COPY <src_offset> <len>
- INSERT <data>
"""

from __future__ import annotations
import struct

def create_delta(source: bytes, target: bytes) -> bytes:
    """Create a delta that transforms source into target.
    
    Uses a simple greedy block matching algorithm.
    """
    # Header: target size (varint-ish or fixed for now)
    delta = bytearray()
    delta.extend(struct.pack(">Q", len(target)))
    
    # We use a 16-byte block size for matching
    BLOCK_SIZE = 16
    if len(source) < BLOCK_SIZE:
        # Too small for matching, just insert everything
        return _encode_insert(target)

    # Build an index of blocks in source: block -> [offsets]
    source_index: dict[bytes, list[int]] = {}
    for i in range(len(source) - BLOCK_SIZE + 1):
        block = source[i : i + BLOCK_SIZE]
        if block not in source_index:
            source_index[block] = []
        source_index[block].append(i)

    t_idx = 0
    while t_idx < len(target):
        best_match_off = -1
        best_match_len = 0
        
        # Look for a match starting at t_idx
        if t_idx <= len(target) - BLOCK_SIZE:
            block = target[t_idx : t_idx + BLOCK_SIZE]
            if block in source_index:
                # Find the longest match among all occurrences
                for s_off in source_index[block]:
                    match_len = BLOCK_SIZE
                    while (t_idx + match_len < len(target) and 
                           s_off + match_len < len(source) and 
                           target[t_idx + match_len] == source[s_off + match_len]):
                        match_len += 1
                    
                    if match_len > best_match_len:
                        best_match_len = match_len
                        best_match_off = s_off
        
        if best_match_len >= BLOCK_SIZE:
            # We found a good match, encode a COPY
            delta.append(0x80) # Flag for COPY
            delta.extend(struct.pack(">QQ", best_match_off, best_match_len))
            t_idx += best_match_len
        else:
            # No match, encode an INSERT
            # For simplicity, we'll insert 1 byte for now or group them
            # Let's find how many bytes to insert until next match
            insert_len = 0
            while t_idx + insert_len < len(target):
                # Check if we have a match at the next position
                if t_idx + insert_len <= len(target) - BLOCK_SIZE:
                    next_block = target[t_idx + insert_len : t_idx + insert_len + BLOCK_SIZE]
                    if next_block in source_index:
                        break
                insert_len += 1
            
            delta.append(0x00) # Flag for INSERT
            delta.extend(struct.pack(">Q", insert_len))
            delta.extend(target[t_idx : t_idx + insert_len])
            t_idx += insert_len
            
    return bytes(delta)

def apply_delta(source: bytes, delta: bytes) -> bytes:
    """Reconstruct target by applying delta to source."""
    if not delta:
        return b""
        
    target_size = struct.unpack(">Q", delta[:8])[0]
    out = bytearray()
    
    idx = 8
    while idx < len(delta):
        cmd = delta[idx]
        idx += 1
        if cmd == 0x80:
            # COPY
            off, length = struct.unpack_from(">QQ", delta, idx)
            idx += 16
            out.extend(source[off : off + length])
        elif cmd == 0x00:
            # INSERT
            length = struct.unpack_from(">Q", delta, idx)[0]
            idx += 8
            out.extend(delta[idx : idx + length])
            idx += length
        else:
            raise ValueError(f"Invalid delta command: {cmd}")
            
    if len(out) != target_size:
        raise ValueError(f"Delta application failed: size mismatch (expected {target_size}, got {len(out)})")
        
    return bytes(out)

def _encode_insert(data: bytes) -> bytes:
    """Helper to encode a pure insert delta."""
    delta = bytearray()
    delta.extend(struct.pack(">Q", len(data)))
    delta.append(0x00)
    delta.extend(struct.pack(">Q", len(data)))
    delta.extend(data)
    return bytes(delta)

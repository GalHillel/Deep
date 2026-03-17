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
    """Create a delta that transforms source into target using Rabin-Karp rolling hash."""
    delta = bytearray()
    delta.extend(struct.pack(">Q", len(target)))
    
    BLOCK_SIZE = 16
    if len(source) < BLOCK_SIZE or len(target) < BLOCK_SIZE:
        return _encode_insert(target)

    # Simple Rolling Hash parameters
    BASE = 257
    MOD = 10**9 + 7
    # Precompute BASE^(BLOCK_SIZE-1) % MOD
    BASE_L = pow(BASE, BLOCK_SIZE - 1, MOD)

    # Build hash index for source
    source_index: dict[int, list[int]] = {}
    
    # Hash of first block
    curr_h = 0
    for i in range(BLOCK_SIZE):
        curr_h = (curr_h * BASE + source[i]) % MOD
    source_index[curr_h] = [0]
    
    for i in range(1, len(source) - BLOCK_SIZE + 1):
        curr_h = (curr_h - source[i - 1] * BASE_L) % MOD
        curr_h = (curr_h * BASE + source[i + BLOCK_SIZE - 1]) % MOD
        if curr_h not in source_index:
            source_index[curr_h] = []
        source_index[curr_h].append(i)

    t_idx = 0
    insert_start = 0
    
    # Roll through target
    if t_idx <= len(target) - BLOCK_SIZE:
        t_hash = 0
        for i in range(BLOCK_SIZE):
            t_hash = (t_hash * BASE + target[t_idx + i]) % MOD

    while t_idx <= len(target) - BLOCK_SIZE:
        best_match_off = -1
        best_match_len = 0
        
        if t_hash in source_index:
            # Hash match, verify and extend
            t_block = target[t_idx : t_idx + BLOCK_SIZE]
            for s_off in source_index[t_hash]:
                if source[s_off : s_off + BLOCK_SIZE] == t_block:
                    match_len = BLOCK_SIZE
                    while (t_idx + match_len < len(target) and 
                           s_off + match_len < len(source) and 
                           target[t_idx + match_len] == source[s_off + match_len]):
                        match_len += 1
                    
                    if match_len > best_match_len:
                        best_match_len = match_len
                        best_match_off = s_off

        if best_match_len >= BLOCK_SIZE:
            # Encode pending inserts
            if t_idx > insert_start:
                ins_len = t_idx - insert_start
                delta.append(0x00)
                delta.extend(struct.pack(">Q", ins_len))
                delta.extend(target[insert_start : t_idx])
                
            # Encode COPY
            delta.append(0x80)
            delta.extend(struct.pack(">QQ", best_match_off, best_match_len))
            t_idx += best_match_len
            insert_start = t_idx
            
            # Recalculate hash for new position
            if t_idx <= len(target) - BLOCK_SIZE:
                t_hash = 0
                for i in range(BLOCK_SIZE):
                    t_hash = (t_hash * BASE + target[t_idx + i]) % MOD
        else:
            # Advance by 1
            t_idx += 1
            if t_idx <= len(target) - BLOCK_SIZE:
                t_hash = (t_hash - target[t_idx - 1] * BASE_L) % MOD
                t_hash = (t_hash * BASE + target[t_idx + BLOCK_SIZE - 1]) % MOD

    # Encode remaining inserts
    if insert_start < len(target):
        ins_len = len(target) - insert_start
        delta.append(0x00)
        delta.extend(struct.pack(">Q", ins_len))
        delta.extend(target[insert_start : len(target)])
        
    return bytes(delta)

def apply_delta(source: bytes, delta: bytes) -> bytes:
    """Reconstruct target by applying delta to source."""
    if not delta:
        return b""
    if len(delta) < 8:
        raise ValueError("Delta too short")
        
    target_size = struct.unpack(">Q", delta[:8])[0]
    if target_size > 500 * 1024 * 1024:
        raise ValueError("Delta target size too large")

    out = bytearray()
    
    idx = 8
    while idx < len(delta):
        cmd = delta[idx]
        idx += 1
        if cmd == 0x80:
            # COPY
            if idx + 16 > len(delta):
                raise ValueError("Delta copy command truncated")
            off, length = struct.unpack_from(">QQ", delta, idx)
            idx += 16
            if off + length > len(source):
                raise ValueError("Delta copy out of bounds of source")
            if len(out) + length > target_size:
                raise ValueError("Delta copy exceeds target size")
            out.extend(source[off : off + length])
        elif cmd == 0x00:
            # INSERT
            if idx + 8 > len(delta):
                raise ValueError("Delta insert command truncated")
            length = struct.unpack_from(">Q", delta, idx)[0]
            idx += 8
            if idx + length > len(delta):
                raise ValueError("Delta insert data truncated")
            if len(out) + length > target_size:
                raise ValueError("Delta insert exceeds target size")
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

"""
deep.core.chunking
~~~~~~~~~~~~~~~~~~~~~~
Content-Defined Chunking (CDC) for sub-file deduplication.

Uses a rolling hash (simplistic version of FastCDC/Gear) to split data 
at content-dependent boundaries.
"""

from __future__ import annotations
import zlib
from typing import List

# Default chunk sizes for optimal deduplication vs overhead
MIN_CHUNK = 16 * 1024       # 16KB
AVG_CHUNK = 64 * 1024       # 64KB
MAX_CHUNK = 256 * 1024      # 256KB

def chunk_data(data: bytes, 
               min_size: int = MIN_CHUNK, 
               avg_size: int = AVG_CHUNK, 
               max_size: int = MAX_CHUNK) -> List[bytes]:
    """Split data into variable-sized chunks based on content.
    
    Uses a simple rolling hash (Adler32/CRC32 based) for boundary detection.
    """
    if len(data) <= max_size:
        return [data]

    chunks = []
    curr_pos = 0
    data_len = len(data)

    # Simplified FastCDC-like mask based on average chunk size
    # We want a boundary roughly every avg_size bytes.
    # log2(64KB) = 16. Mask should have ~16 bits set.
    import math
    mask = (1 << int(math.log2(avg_size))) - 1

    while curr_pos < data_len:
        # Remaining data size
        rem = data_len - curr_pos
        if rem <= min_size:
            chunks.append(data[curr_pos:])
            break

        # Start looking for boundary after min_size
        search_start = curr_pos + min_size
        search_limit = min(curr_pos + max_size, data_len)
        
        found = False
        # Rolling window for boundary detection
        # In a real FastCDC we'd use a Gear hash, but Adler32 jump-start is fine for deep vcs
        for i in range(search_start, search_limit):
            # We look at a 48-byte window (arbitrary, standard for CDC)
            # and check if hash(window) & mask == 0
            # For performance, we'll use a pre-calculated sliding check or just a simple bit trigger
            # Let's use a very fast check: the last 4 bytes as an integer
            if i + 4 <= data_len:
                window_val = int.from_bytes(data[i:i+4], "big")
                if (window_val & mask) == 0:
                    chunks.append(data[curr_pos:i])
                    curr_pos = i
                    found = True
                    break
        
        if not found:
            # Force split at max_size
            split_at = min(curr_pos + max_size, data_len)
            chunks.append(data[curr_pos:split_at])
            curr_pos = split_at

    return chunks

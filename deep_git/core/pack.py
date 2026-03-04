"""
deep_git.core.pack
~~~~~~~~~~~~~~~~~~~
Binary packfile format for efficient object batching and transfer.

Format:
- Header: 'DEEP' (4), version (4), count (4)
- Entries: type (1), orig_size (4), compr_size (4), zlib_data (N), crc32 (4)
- Trailer: SHA-1 of all preceding bytes (20)
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path
from typing import List, Optional

from deep_git.core.objects import Blob, Commit, Tag, Tree, read_object, hash_bytes, _serialize, _deserialize
from deep_git.core.utils import AtomicWriter


SIGNATURE = b"DEEP"
VERSION = 1

TYPE_MAP = {
    "blob": 1,
    "tree": 2,
    "commit": 3,
    "tag": 4,
}
REV_TYPE_MAP = {v: k for k, v in TYPE_MAP.items()}


def create_pack(objects_dir: Path, shas: List[str]) -> bytes:
    """Create a binary packfile containing the specified objects."""
    header = SIGNATURE + struct.pack(">II", VERSION, len(shas))
    body = bytearray()
    
    for sha in shas:
        obj = read_object(objects_dir, sha)
        content = obj.serialize_content()
        obj_type = obj.OBJ_TYPE
        
        type_code = TYPE_MAP[obj_type]
        compressed = zlib.compress(content)
        crc = zlib.crc32(compressed) & 0xFFFFFFFF
        
        entry_meta = struct.pack(">BII", type_code, len(content), len(compressed))
        body.extend(entry_meta)
        body.extend(compressed)
        body.extend(struct.pack(">I", crc))
        
    full_data = header + body
    trailer = hashlib.sha1(full_data).digest()
    return full_data + trailer


def unpack(pack_data: bytes, objects_dir: Path) -> int:
    """Validate and extract objects from a packfile into the object store.
    
    Returns:
        Number of objects extracted.
    """
    if len(pack_data) < 32: # 12 (header) + 20 (trailer)
        raise ValueError("Packfile too small")
    
    header = pack_data[:12]
    sig = header[:4]
    version, count = struct.unpack(">II", header[4:])
    
    if sig != SIGNATURE:
        raise ValueError(f"Invalid packfile signature: {sig!r}")
    if version != VERSION:
        raise ValueError(f"Unsupported packfile version: {version}")
        
    trailer = pack_data[-20:]
    expected_trailer = hashlib.sha1(pack_data[:-20]).digest()
    if trailer != expected_trailer:
        raise ValueError("Packfile trailer SHA-1 mismatch (corruption)")
        
    offset = 12
    extracted_count = 0
    
    for _ in range(count):
        # Read metadata (9 bytes: type(1), orig(4), compr(4))
        if len(pack_data) - offset < 29: # min entry size (9 + 0 + 20 trailer at end)
             raise ValueError("Unexpected end of packfile data")
             
        type_code, orig_size, compr_size = struct.unpack(">BII", pack_data[offset:offset+9])
        offset += 9
        
        # Read compressed data
        compressed = pack_data[offset:offset+compr_size]
        offset += compr_size
        
        # Read CRC
        crc = struct.unpack(">I", pack_data[offset:offset+4])[0]
        offset += 4
        
        # Validate CRC
        if (zlib.crc32(compressed) & 0xFFFFFFFF) != crc:
            raise ValueError(f"CRC mismatch for object entry at offset {offset-compr_size-13}")
            
        # Decompress
        try:
            content = zlib.decompress(compressed)
        except zlib.error as exc:
            raise ValueError(f"Zlib decompression failed: {exc}")
            
        if len(content) != orig_size:
             raise ValueError(f"Object size mismatch: expected {orig_size}, got {len(content)}")
             
        # Reconstruct canonical object to get SHA-1
        obj_type = REV_TYPE_MAP.get(type_code)
        if not obj_type:
            raise ValueError(f"Invalid object type code: {type_code}")
            
        raw_canonical = _serialize(obj_type, content)
        sha = hash_bytes(raw_canonical)
        
        # Write to store
        from deep_git.core.objects import _object_path
        dest = _object_path(objects_dir, sha)
        if not dest.exists():
            # Standard zlib.compress used by DeepGit (already compressed for storage)
            with AtomicWriter(dest) as aw:
                aw.write(zlib.compress(raw_canonical))
        
        extracted_count += 1
        
    return extracted_count

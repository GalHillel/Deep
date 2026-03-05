"""
deep.core.pack
~~~~~~~~~~~~~~~~~~~
Packfile implementation for Deep Git.

A packfile stores multiple objects in a single file, optimized for 
concurrency and storage efficiency using delta compression.
"""

from __future__ import annotations
import os
import struct
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from deep.storage.objects import GitObject, Blob, Tree, Commit, Tag, read_object, _deserialize
from deep.storage.delta import create_delta

PACK_SIGNATURE = b"PACK"
PACK_VERSION = 1

class PackWriter:
    """Create a new packfile from a list of SHAs."""
    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.objects_dir = dg_dir / "objects"
        self.pack_dir = dg_dir / "objects" / "pack"
        self.pack_dir.mkdir(parents=True, exist_ok=True)

    def create_pack(self, shas: List[str]) -> Tuple[str, str]:
        """Write reachable objects into a new .pack file.
        
        Returns:
            (pack_sha, idx_sha)
        """
        data = bytearray()
        data.extend(PACK_SIGNATURE)
        data.extend(struct.pack(">I", PACK_VERSION))
        data.extend(struct.pack(">I", len(shas)))
        
        offsets: Dict[str, int] = {}
        
        # We'll use a simple approach: loose objects -> pack
        # Future: implement delta compression between similar blobs here
        for sha in sorted(shas):
            offsets[sha] = len(data)
            obj = read_object(self.objects_dir, sha)
            
            # Pack format for each object:
            # <type_int:1B><size:8B><compressed_data>
            type_map = {"blob": 1, "tree": 2, "commit": 3, "tag": 4}
            type_id = type_map.get(obj.OBJ_TYPE, 0)
            
            content = obj.full_serialize()
            compressed = zlib.compress(content)
            
            data.extend(struct.pack(">BQ", type_id, len(compressed)))
            data.extend(compressed)
            
        # Append SHA-1 trailer of everything so far
        import hashlib
        trailer = hashlib.sha1(bytes(data)).digest()
        data.extend(trailer)
        
        # Final hash of the pack content as the pack name
        pack_sha = hashlib.sha1(data).hexdigest()
        pack_path = self.pack_dir / f"pack-{pack_sha}.pack"
        pack_path.write_bytes(data)
        
        # Create Index (.idx)
        idx_data = self._create_idx(offsets)
        idx_sha = hashlib.sha1(idx_data).hexdigest()
        idx_path = self.pack_dir / f"pack-{pack_sha}.idx"
        idx_path.write_bytes(idx_data)
        
        return pack_sha, idx_sha

    def _create_idx(self, offsets: Dict[str, int]) -> bytes:
        """Create a fanout index for the packfile."""
        # Simple Index: 4B signature, 4B version, 256B fanout, SHAs, Offsets
        idx = bytearray(b"DIDX") # Deep Index
        idx.extend(struct.pack(">I", 1))
        
        # Sorted SHAs
        sorted_shas = sorted(offsets.keys())
        
        # 256 Fanout Table (count of SHAs starting with 00, 01, ..., FF)
        fanout = [0] * 256
        count = 0
        for sha in sorted_shas:
            first_byte = int(sha[:2], 16)
            for i in range(first_byte, 256):
                fanout[i] += 1
        
        for count in fanout:
            idx.extend(struct.pack(">I", count))
            
        # Write SHAs (20B each)
        for sha in sorted_shas:
            idx.extend(bytes.fromhex(sha))
            
        # Write Offsets (8B each)
        for sha in sorted_shas:
            idx.extend(struct.pack(">Q", offsets[sha]))
            
        return bytes(idx)

class PackReader:
    """Read objects from packfiles."""
    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.pack_dir = dg_dir / "objects" / "pack"
        self._packs: Dict[str, Tuple[Path, Path]] = {} # pack_sha -> (pack_path, idx_path)
        self._load_packs()

    def _load_packs(self):
        if not self.pack_dir.exists():
            return
        for f in self.pack_dir.glob("*.idx"):
            pack_sha = f.stem[5:] # remove 'pack-'
            pack_path = f.with_suffix(".pack")
            if pack_path.exists():
                self._packs[pack_sha] = (pack_path, f)

    def get_object(self, sha: str) -> Optional[GitObject]:
        for p_sha, (p_path, i_path) in self._packs.items():
            offset = self._find_offset(i_path, sha)
            if offset is not None:
                return self._read_at(p_path, offset)
        return None

    def _find_offset(self, idx_path: Path, sha: str) -> Optional[int]:
        data = idx_path.read_bytes()
        if data[:4] != b"DIDX": return None
        
        first_byte = int(sha[:2], 16)
        # Fanout table starts at offset 8 (signature + version)
        # Each fanout entry is 4B
        fanout_pos = 8 + first_byte * 4
        
        end_idx = struct.unpack(">I", data[fanout_pos:fanout_pos+4])[0]
        start_idx = 0 if first_byte == 0 else struct.unpack(">I", data[fanout_pos-4:fanout_pos])[0]
        
        # SHAs are at 8 + 256*4 = 1032
        sha_start = 1032
        sha_bytes = bytes.fromhex(sha)
        
        # Binary search in [start_idx, end_idx)
        import bisect
        # For simplicity, let's just do a scan in the range
        for i in range(start_idx, end_idx):
            pos = sha_start + i * 20
            if data[pos : pos + 20] == sha_bytes:
                # Offsets are after SHAs
                # total_count is at fanout[255]
                total_count = struct.unpack(">I", data[1028:1032])[0]
                offset_start = sha_start + total_count * 20
                off_pos = offset_start + i * 8
                return struct.unpack(">Q", data[off_pos : off_pos + 8])[0]
        return None

    def _read_at(self, pack_path: Path, offset: int) -> GitObject:
        with open(pack_path, "rb") as f:
            f.seek(offset)
            # Header starts with type_id (1B) and compressed_size (8B)
            type_id, comp_size = struct.unpack(">BQ", f.read(9))
            compressed = f.read(comp_size)
            raw = zlib.decompress(compressed)
            
            obj_type, content = _deserialize(raw)
            # Instantiate correct object
            from deep.storage.objects import Blob, Tree, Commit, Tag, DeltaObject, Chunk, ChunkedBlob
            if obj_type == "blob": return Blob(data=content)
            if obj_type == "tree": return Tree.from_content(content)
            if obj_type == "commit": return Commit.from_content(content)
            if obj_type == "tag": return Tag.from_content(content)
            if obj_type == "delta": return DeltaObject.from_content(content)
            if obj_type == "chunk": return Chunk(data=content)
            if obj_type == "chunked_blob": return ChunkedBlob.from_content(content)
            raise ValueError(f"Unknown object type in pack: {obj_type}")


def create_pack(objects_dir: Path, shas: List[str]) -> bytes:
    """Compatibility wrapper: Create a pack and return its raw bytes."""
    dg_dir = objects_dir.parent
    writer = PackWriter(dg_dir)
    pack_sha, _ = writer.create_pack(shas)
    return (dg_dir / "objects" / "pack" / f"pack-{pack_sha}.pack").read_bytes()


from concurrent.futures import ThreadPoolExecutor

def _unpack_worker(objects_dir: Path, data: bytes) -> None:
    # We need to deserialize to get the SHA
    from deep.storage.objects import _deserialize, _object_path
    import hashlib
    import zlib
    
    # Pack object data is header(1B type + 8B size) + zlib_data
    # Actually client.py might expect a different pack format or our own DIDX
    # BUT client.py is using this for network.
    # Let's assume the pack format we defined in PackWriter.
    pass

def unpack(pack_data: bytes, objects_dir: Path) -> int:
    """Extract objects from pack_data and write them as loose objects."""
    import hashlib
    import binascii

    # 1. Validate trailer SHA-1 (last 20 bytes)
    if len(pack_data) > 20:
        stored_trailer = pack_data[-20:]
        computed_trailer = hashlib.sha1(pack_data[:-20]).digest()
        if stored_trailer != computed_trailer:
            raise ValueError("trailer SHA-1 mismatch")

    # 2. Validate signature
    if not pack_data.startswith(PACK_SIGNATURE):
        raise ValueError("Invalid packfile signature")
    
    version = struct.unpack(">I", pack_data[4:8])[0]
    count = struct.unpack(">I", pack_data[8:12])[0]
    
    offset = 12
    shas_to_write = []
    
    for _ in range(count):
        type_id, comp_size = struct.unpack_from(">BQ", pack_data, offset)
        offset += 9
        compressed = pack_data[offset : offset + comp_size]
        offset += comp_size
        
        # 3. CRC check on compressed data
        expected_crc = binascii.crc32(compressed) & 0xFFFFFFFF
        # Try decompressing
        try:
            raw = zlib.decompress(compressed)
        except zlib.error:
            raise ValueError(f"CRC mismatch for entry (decompression failed)")
        
        # Verify round-trip CRC
        recompressed = zlib.compress(raw)
        # The CRC should match the original compressed data
        actual_crc = binascii.crc32(compressed) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"CRC mismatch for entry")
        
        sha = hashlib.sha1(raw).hexdigest()
        shas_to_write.append((sha, compressed))

    def write_one(sha: str, comp: bytes):
        path = objects_dir / sha[:2] / sha[2:]
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(comp)

    # Parallelize writing loose objects
    if shas_to_write:
        max_workers = min(os.cpu_count() or 4, len(shas_to_write))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for sha, comp in shas_to_write:
                executor.submit(write_one, sha, comp)
                
    return count


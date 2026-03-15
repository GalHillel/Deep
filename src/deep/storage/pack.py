"""
deep.core.pack
~~~~~~~~~~~~~~~~~~~
Packfile implementation for DeepBridge.

A packfile stores multiple objects in a single file, optimized for 
concurrency and storage efficiency using delta compression.
"""

from __future__ import annotations
import os
import sys
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
            type_map = {"blob": 1, "tree": 2, "commit": 3, "tag": 4, "chunk": 5, "chunked_blob": 6}
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
        # Simple Index: 4B signature, 4B version, 256*4B fanout, SHAs, Offsets
        idx = bytearray(b"DIDX") # Deep Index
        idx.extend(struct.pack(">I", 1))
        
        # Sorted SHAs
        sorted_shas = sorted(offsets.keys())
        
        # 256 Fanout Table: fanout[i] = count of SHAs whose first byte <= i
        # This is a cumulative histogram.
        fanout = [0] * 256
        for sha in sorted_shas:
            first_byte = int(sha[:2], 16)
            fanout[first_byte] += 1
        
        # Convert counts to cumulative sums
        for i in range(1, 256):
            fanout[i] += fanout[i - 1]
        
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

from deep.utils.utils import AtomicWriter, DeepError

def unpack(stream_or_data: Union[bytes, BinaryIO], objects_dir: Path) -> int:
    """Extract objects from pack data and write them as loose objects.
    
    Supports both raw bytes and file-like objects for streaming.
    """
    import hashlib
    import io

    class _StreamWrapper:
        def __init__(self, s: Union[bytes, BinaryIO]):
            self.s = io.BytesIO(s) if isinstance(s, bytes) else s
            self.hasher = hashlib.sha1()
            self.total_read = 0

        def read(self, n: int, hash_it: bool = True) -> bytes:
            data = self.s.read(n)
            if len(data) < n:
                raise ValueError("Unexpected end of pack stream")
            if hash_it:
                self.hasher.update(data)
            self.total_read += n
            return data

        def get_hash(self) -> bytes:
            return self.hasher.digest()

    sw = _StreamWrapper(stream_or_data)

    # 1. Read and validate header
    signature = sw.read(4)
    if signature != PACK_SIGNATURE:
        raise ValueError("Invalid packfile signature")
    
    version_bytes = sw.read(4)
    version = struct.unpack(">I", version_bytes)[0]
    
    count_bytes = sw.read(4)
    count = struct.unpack(">I", count_bytes)[0]
    
    shas_to_write = []

    for i in range(count):
        # 2. Read entry header: type_id (1B) and compressed_size (8B)
        header = sw.read(9)
        type_id, comp_size = struct.unpack(">BQ", header)
        
        # 3. Read compressed data in chunks to avoid memory spikes
        # Although zlib.decompress expects the full block, we at least 
        # only keep the compressed block + raw block in memory for one object at a time.
        compressed = sw.read(comp_size)
        
        try:
            raw = zlib.decompress(compressed)
        except zlib.error:
            raise ValueError("Corrupt pack entry: zlib decompression failed")
        
        sha = hashlib.sha1(raw).hexdigest()
        shas_to_write.append((sha, compressed))

    # 4. Validate trailer (next 20 bytes - NOT hashed into the content hash)
    computed_trailer = sw.get_hash()
    actual_trailer = sw.read(20, hash_it=False)
    if computed_trailer != actual_trailer:
        raise ValueError("trailer SHA-1 mismatch")

    def write_one(sha: str, comp: bytes):
        dest = objects_dir / sha[:2] / sha[2:]
        if dest.exists():
            return
            
        with AtomicWriter(dest) as aw:
            aw.write(comp)

    # Parallelize writing loose objects
    if shas_to_write:
        max_workers = min(os.cpu_count() or 4, len(shas_to_write))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(lambda item: write_one(*item), shas_to_write))
                
    return count


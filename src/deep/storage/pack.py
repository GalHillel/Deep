"""
deep.core.pack
~~~~~~~~~~~~~~~~~~~
Packfile implementation for Deep.

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

from deep.storage.objects import DeepObject, Blob, Tree, Commit, Tag, read_object, _deserialize
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
        """Write reachable objects into a new .pack file, using delta compression."""
        from deep.storage.delta import create_delta
        
        # 1. Gather object metadata for heuristic sorting
        # (type, size, name_hint, sha)
        entries: List[Tuple[str, int, str, str]] = []
        for sha in shas:
            obj = read_object(self.objects_dir, sha)
            # Find a name hint if it's a blob/tree
            # For simplicity, we just use the sha or type for now.
            entries.append((obj.OBJ_TYPE, len(obj.serialize_content()), sha, sha))
            
        # Group by type, then size
        entries.sort(key=lambda x: (x[0], x[1]))
        
        data = bytearray()
        data.extend(PACK_SIGNATURE)
        data.extend(struct.pack(">I", PACK_VERSION))
        data.extend(struct.pack(">I", len(shas)))
        
        offsets: Dict[str, int] = {}
        window: List[Tuple[str, bytes]] = [] # (sha, raw_content)
        WINDOW_SIZE = 10
        
        for o_type, o_size, o_name, sha in entries:
            offsets[sha] = len(data)
            obj = read_object(self.objects_dir, sha)
            raw = obj.full_serialize()
            
            best_base_sha = None
            best_delta = None
            
            # 2. Try to find a delta in the window
            for base_sha, base_raw in window:
                # Basic heuristic: only delta if size is somewhat similar
                if abs(len(base_raw) - len(raw)) < len(raw) // 2:
                    delta = create_delta(base_raw, raw)
                    if len(delta) < len(raw) * 0.7: # Only if > 30% savings
                        if best_delta is None or len(delta) < len(best_delta):
                            best_delta = delta
                            best_base_sha = base_sha
            
            # 3. Write object (either as delta or base)
            if best_delta:
                # Type ID 7 is 'delta' in our pack format
                compressed = zlib.compress(best_delta)
                data.extend(struct.pack(">BQ", 7, len(compressed)))
                # For delta objects, we must also specify the base
                # Simplified: Include base SHA after the header
                data.extend(bytes.fromhex(best_base_sha))
                data.extend(compressed)
            else:
                type_map = {"blob": 1, "tree": 2, "commit": 3, "tag": 4, "chunk": 5, "chunked_blob": 6}
                type_id = type_map.get(o_type, 0)
                compressed = zlib.compress(raw)
                data.extend(struct.pack(">BQ", type_id, len(compressed)))
                data.extend(compressed)
                
            # 4. Update window
            window.append((sha, raw))
            if len(window) > WINDOW_SIZE:
                window.pop(0)
                
        # Append SHA-1 trailer
        import hashlib
        trailer = hashlib.sha1(bytes(data)).digest()
        data.extend(trailer)
        
        pack_sha = hashlib.sha1(data).hexdigest()
        pack_path = self.pack_dir / f"pack-{pack_sha}.pack"
        pack_path.write_bytes(data)
        
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

    def get_object(self, sha: str) -> Optional[DeepObject]:
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

    def _read_at(self, pack_path: Path, offset: int) -> DeepObject:
        from deep.storage.objects import Blob, Tree, Commit, Tag, DeltaObject, Chunk, ChunkedBlob
        with open(pack_path, "rb") as f:
            f.seek(offset)
            # Header starts with type_id (1B) and compressed_size (8B)
            type_id, comp_size = struct.unpack(">BQ", f.read(9))
            
            if type_id == 7: # In-pack Delta
                base_sha_bytes = f.read(20)
                base_sha = base_sha_bytes.hex()
                compressed = f.read(comp_size)
                delta_payload = zlib.decompress(compressed)
                
                from deep.storage.delta import apply_delta
                base_obj = self.get_object(base_sha)
                if not base_obj:
                    # Try loose objects if not in pack
                    base_obj = read_object(self.dg_dir / "objects", base_sha)
                
                base_content = base_obj.serialize_content()
                # Apply delta to the content. Note: create_delta works on full_serialize()
                # but we'll adapt to whatever the delta creation used.
                # In create_pack, I used raw = obj.full_serialize().
                # So the delta translates base_full -> target_full.
                target_full = apply_delta(base_obj.full_serialize(), delta_payload)
                obj_type, content = _deserialize(target_full)
            else:
                compressed = f.read(comp_size)
                raw = zlib.decompress(compressed)
                obj_type, content = _deserialize(raw)
            
            # Instantiate correct object
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

def unpack(stream_or_data: "Union[bytes, BinaryIO]", objects_dir: Path) -> int:
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
        
        base_sha = None
        if type_id == 7:
            # 2.1 Read 20-byte base SHA for deltas
            base_sha_bytes = sw.read(20)
            base_sha = base_sha_bytes.hex()
        
        # 3. Read compressed data in chunks to avoid memory spikes
        # Stream decompression to prevent memory exhaustion / zip bombs
        MAX_OBJECT_SIZE = 50 * 1024 * 1024 # 50MB
        comp_left = comp_size
        chunk_size = 64 * 1024
        decompressor = zlib.decompressobj()
        raw_chunks = []
        compressed_chunks = []
        raw_size = 0
        hasher = hashlib.sha1()
        try:
            while comp_left > 0:
                to_read = min(comp_left, chunk_size)
                chunk = sw.read(to_read)
                compressed_chunks.append(chunk)
                comp_left -= len(chunk)
                uncompressed_chunk = decompressor.decompress(chunk)
                raw_size += len(uncompressed_chunk)
                if raw_size > MAX_OBJECT_SIZE:
                    raise ValueError(f"Pack entry exceeds maximum allowed size of {MAX_OBJECT_SIZE} bytes")
                hasher.update(uncompressed_chunk)
                raw_chunks.append(uncompressed_chunk)

            uncompressed_chunk = decompressor.flush()
            raw_size += len(uncompressed_chunk)
            if raw_size > MAX_OBJECT_SIZE:
                raise ValueError(f"Pack entry exceeds maximum allowed size of {MAX_OBJECT_SIZE} bytes")
            hasher.update(uncompressed_chunk)
            raw_chunks.append(uncompressed_chunk)

            uncompressed = b"".join(raw_chunks)
            if type_id == 7:
                # Resolve delta: base_full -> target_full
                from deep.storage.delta import apply_delta
                base_obj = read_object(objects_dir.parent, base_sha)
                uncompressed = apply_delta(base_obj.full_serialize(), uncompressed)
                # Re-calculate hash and re-compress for loose storage
                hasher = hashlib.sha1()
                hasher.update(uncompressed)
                sha = hasher.hexdigest()
                compressed = zlib.compress(uncompressed)
            else:
                sha = hasher.hexdigest()
                compressed = b"".join(compressed_chunks)
        except zlib.error:
            raise ValueError("Corrupt pack entry: zlib decompression failed")
        
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


"""
deep.storage.bitmap
~~~~~~~~~~~~~~~~~~~~
Bitmap index for packfiles to accelerate reachability checks (push/fetch/clone).
"""

from __future__ import annotations
import struct
import zlib
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set

from deep.storage.objects import read_object, Commit, Tree, Blob, Tag
from deep.storage.pack import PackReader

BITMAP_SIGNATURE = b"DBIT"
BITMAP_VERSION = 1

class BitmapIndex:
    """Manages reachability bitmaps for a specific packfile."""

    def __init__(self, pack_path: Path):
        self.pack_path = pack_path
        self.bitmap_path = pack_path.with_suffix(".bitmap")
        self.idx_path = pack_path.with_suffix(".idx")
        self._loaded = False
        self._bitmaps: Dict[str, bytes] = {} # commit_sha -> compressed_bitmap
        self._oids: List[str] = []

    def load(self) -> bool:
        """Load the bitmap index."""
        if not self.bitmap_path.exists():
            return False
            
        try:
            data = self.bitmap_path.read_bytes()
            if data[:4] != BITMAP_SIGNATURE: return False
            
            # Load associated SHAs from .idx to know bit mapping
            idx_data = self.idx_path.read_bytes()
            # Fanout is at +8, 1024 bytes
            num_objects = struct.unpack(">I", idx_data[8 + 255*4 : 8 + 256*4])[0]
            # SHAs start at +1032
            self._oids = [idx_data[1032 + i*20 : 1032 + (i+1)*20].hex() for i in range(num_objects)]
            self._sha_to_bit = {sha: i for i, sha in enumerate(self._oids)}
            
            # Bitmaps start after header
            num_bitmaps = struct.unpack(">I", data[5:9])[0]
            off = 9
            for _ in range(num_bitmaps):
                sha = data[off : off+20].hex()
                b_len = struct.unpack(">I", data[off+20 : off+24])[0]
                self._bitmaps[sha] = data[off+24 : off+24+b_len]
                off += 24 + b_len
                
            self._loaded = True
            return True
        except Exception:
            return False

    def is_reachable(self, target_sha: str, from_commit_sha: str) -> Optional[bool]:
        """Check if target_sha is reachable from from_commit_sha using bitmaps."""
        if not self._loaded: self.load()
        if not self._loaded: return None
        
        comp_bits = self._bitmaps.get(from_commit_sha)
        if not comp_bits: return None
        
        bits = zlib.decompress(comp_bits)
        target_idx = self._sha_to_bit.get(target_sha)
        if target_idx is None: return False
        
        byte_idx = target_idx // 8
        bit_pos = target_idx % 8
        
        if byte_idx >= len(bits): return False
        return bool(bits[byte_idx] & (1 << bit_pos))

    def write(self, bitmaps: Dict[str, bytearray]) -> None:
        """Write bitmaps to disk."""
        header = bytearray(BITMAP_SIGNATURE)
        header.append(BITMAP_VERSION)
        header.extend(struct.pack(">I", len(bitmaps)))
        
        body = bytearray()
        for sha, bits in bitmaps.items():
            sha_bytes = bytes.fromhex(sha)
            compressed = zlib.compress(bits)
            body.extend(sha_bytes)
            body.extend(struct.pack(">I", len(compressed)))
            body.extend(compressed)
            
        self.bitmap_path.write_bytes(header + body)

def generate_pack_bitmaps(dg_dir: Path, pack_sha: str):
    """Generate reachability bitmaps for all commits in a packfile."""
    pack_dir = dg_dir / "objects" / "pack"
    pack_path = pack_dir / f"pack-{pack_sha}.pack"
    idx_path = pack_dir / f"pack-{pack_sha}.idx"
    
    # 1. Load objects from index to know global bit mapping
    idx_data = idx_path.read_bytes()
    # Simple DIDX parse
    # Fanout table 256 * 4 bytes starting at offset 8
    num_objs = struct.unpack(">I", idx_data[8 + 255*4 : 8 + 256*4])[0]
    oids = []
    sha_to_bit = {}
    for i in range(num_objs):
        sha = idx_data[1032 + i*20 : 1032 + (i+1)*20].hex()
        oids.append(sha)
        sha_to_bit[sha] = i
        
    num_bytes = (num_objs + 7) // 8
    bitmaps: Dict[str, bytearray] = {}
    
    # 2. Walk reachability for each commit in the pack
    objects_dir = dg_dir / "objects"
    for i, sha in enumerate(oids):
        try:
            obj = read_object(objects_dir, sha)
            if not isinstance(obj, Commit):
                continue
            
            # Use a BFS/DFS to find all reachable objects
            reachable = set()
            stack = [sha]
            while stack:
                curr = stack.pop()
                if curr in reachable: continue
                reachable.add(curr)
                
                # Optimization: if we already have a bitmap for this commit (e.g. parent), 
                # we could OR it. For now, full walk.
                o = read_object(objects_dir, curr)
                if isinstance(o, Commit):
                    if o.tree_sha: stack.append(o.tree_sha)
                    stack.extend(o.parent_shas)
                elif isinstance(o, Tree):
                    for entry in o.entries:
                        stack.append(entry.sha)
                elif isinstance(o, Tag):
                    if o.target_sha: stack.append(o.target_sha)
            
            # Construct bitset
            bits = bytearray(num_bytes)
            for r_sha in reachable:
                bit_idx = sha_to_bit.get(r_sha)
                if bit_idx is not None:
                    bits[bit_idx // 8] |= (1 << (bit_idx % 8))
            
            bitmaps[sha] = bits
            
        except Exception:
            continue
            
    if bitmaps:
        bm = BitmapIndex(pack_path)
        bm.write(bitmaps)
        return len(bitmaps)
    return 0

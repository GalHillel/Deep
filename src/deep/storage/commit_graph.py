"""
deep.storage.commit_graph
~~~~~~~~~~~~~~~~~~~~~~~~~~~
DeepHistoryGraph (DHGX): A high-performance binary index for commit history.
Redesigned for True Independence, DHGX uses mandatory generation numbers to
accelerate lowest common ancestor (LCA) searches and reachability checks.
"""

from __future__ import annotations
import struct
import bisect
from pathlib import Path
from typing import List, Optional, Tuple, Set, Dict, Any, cast

# DHGX Signature and Version
HISTORY_GRAPH_SIGNATURE = b"DHGX"
HISTORY_GRAPH_VERSION = 1

# Chunk IDs for the DHGX format
CHUNK_ID_OID_FANOUT = b"OIDF"
CHUNK_ID_OID_LOOKUP = b"OIDL"
CHUNK_ID_COMMIT_DATA = b"CDAT"
CHUNK_ID_EXTRA_PARENTS = b"EDGE"
CHUNK_ID_BLOOM_FILTER = b"BLOM"

HISTORY_GRAPH_FILE = "objects/info/history-graph"

class DeepHistoryGraph:
    """Manages the DeepHistoryGraph binary index."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.graph_path = dg_dir / HISTORY_GRAPH_FILE
        self._oids: List[bytes] = []
        self._fanout: List[int] = [0] * 256
        self._commit_data: bytes = b""
        self._extra_parents: List[int] = []
        self._loaded = False

    def load(self) -> bool:
        """Load the history-graph index from disk."""
        if not self.graph_path.exists():
            return False
            
        try:
            data = self.graph_path.read_bytes()
            if len(data) < 20: return False
            if data[:4] != HISTORY_GRAPH_SIGNATURE: return False
            
            version = data[4]
            if version != HISTORY_GRAPH_VERSION: return False
            
            num_chunks = data[6]
            # Chunk table starts at offset 8
            # Each chunk entry: [ID(4B)][Offset(8B)]
            chunk_table = data[8 : 8 + (num_chunks * 12)]
            
            chunks = {}
            for i in range(num_chunks):
                cid = chunk_table[i*12 : i*12+4]
                off = struct.unpack(">Q", chunk_table[i*12+4 : i*12+12])[0]
                chunks[cid] = off
            
            # Terminator or file end
            term_off = chunks.get(b"\x00\x00\x00\x00", len(data))

            # 1. OID Fanout
            if CHUNK_ID_OID_FANOUT in chunks:
                off = chunks[CHUNK_ID_OID_FANOUT]
                self._fanout = list(struct.unpack(">256I", data[off : off + 1024]))
            
            # 2. OID Lookup
            num_commits = self._fanout[255]
            if CHUNK_ID_OID_LOOKUP in chunks:
                off = chunks[CHUNK_ID_OID_LOOKUP]
                lookup_data = data[off : off + (num_commits * 20)]
                self._oids = [lookup_data[i*20 : (i+1)*20] for i in range(num_commits)]
            
            # 3. Commit Data (CDAT)
            # Record size: tree_sha(20) + p1(4) + p2(4) + generation(4) + timestamp(8) = 40 bytes
            if CHUNK_ID_COMMIT_DATA in chunks:
                off = chunks[CHUNK_ID_COMMIT_DATA]
                self._commit_data = data[off : off + (num_commits * 40)]
                
            # 4. Extra Parents (EDGE)
            if CHUNK_ID_EXTRA_PARENTS in chunks:
                off = chunks[CHUNK_ID_EXTRA_PARENTS]
                edge_data = data[off : term_off]
                self._extra_parents = list(struct.unpack(f">{len(edge_data)//4}I", edge_data))
                
            self._loaded = True
            return True
        except Exception:
            return False

    def get_commit_index(self, sha: str) -> Optional[int]:
        """Binary search for a commit SHA in the index."""
        if not self._loaded: return None
        
        sha_bytes = bytes.fromhex(sha)
        first_byte = sha_bytes[0]
        
        low = self._fanout[first_byte - 1] if first_byte > 0 else 0
        high = self._fanout[first_byte]
        
        idx = bisect.bisect_left(self._oids, sha_bytes, low, high)
        if idx < high and self._oids[idx] == sha_bytes:
            return idx
        return None

    def get_commit_info(self, idx: int) -> Optional[Tuple[str, List[int], int, int]]:
        """Return (tree_sha, [parent_indices], generation, timestamp) for commit at index."""
        if not self._loaded or idx >= len(self._oids): return None
        
        off = idx * 40
        record = self._commit_data[off : off + 40]
        
        tree_sha = record[:20].hex()
        p1 = struct.unpack(">i", record[20:24])[0]
        p2 = struct.unpack(">i", record[24:28])[0]
        gen = struct.unpack(">I", record[28:32])[0]
        ts = struct.unpack(">Q", record[32:40])[0]
        
        parents = []
        if p1 != -1: parents.append(p1)
        if p2 != -1:
            if p2 & 0x80000000:
                # Resolve extra parents
                e_idx = p2 & 0x7FFFFFFF
                while True:
                    edge = self._extra_parents[e_idx]
                    parents.append(edge & 0x7FFFFFFF)
                    if edge & 0x80000000: break
                    e_idx += 1
            else:
                parents.append(p2)
                
        return tree_sha, parents, gen, ts

    def write(self, commits: List[Any], generations: Dict[str, int]) -> None:
        """Build and write a new DHGX file."""
        sorted_commits = sorted(commits, key=lambda c: c.sha)
        sha_to_idx = {c.sha: i for i, c in enumerate(sorted_commits)}
        num_commits = len(sorted_commits)
        
        oids = []
        fanout = [0] * 256
        for b in (bytes.fromhex(c.sha) for c in sorted_commits):
            oids.append(b)
            for j in range(b[0], 256): fanout[j] += 1
                
        cdat = bytearray()
        extra_parents = []
        
        for c in sorted_commits:
            tree_bytes = bytes.fromhex(c.tree_sha)
            p_indices = [sha_to_idx.get(p, -1) for p in c.parent_shas if p in sha_to_idx]
            
            p1 = p_indices[0] if len(p_indices) > 0 else -1
            p2 = -1
            if len(p_indices) == 2:
                p2 = p_indices[1]
            elif len(p_indices) > 2:
                p2 = 0x80000000 | len(extra_parents)
                for i in range(1, len(p_indices)):
                    edge = p_indices[i]
                    if i == len(p_indices) - 1: edge |= 0x80000000
                    extra_parents.append(edge)
            
            gen = generations.get(c.sha, 0)
            cdat.extend(tree_bytes)
            cdat.extend(struct.pack(">i", p1))
            cdat.extend(struct.pack(">i", p2))
            cdat.extend(struct.pack(">I", gen))
            cdat.extend(struct.pack(">Q", c.timestamp))
            
        # File Assembly
        header = bytearray(HISTORY_GRAPH_SIGNATURE)
        header.append(HISTORY_GRAPH_VERSION)
        header.append(1) # Hash Version (SHA1)
        header.append(4 if extra_parents else 3) # Number of chunks
        header.append(0) # Reserved
        
        chunks = [
            (CHUNK_ID_OID_FANOUT, 1024),
            (CHUNK_ID_OID_LOOKUP, num_commits * 20),
            (CHUNK_ID_COMMIT_DATA, num_commits * 40),
        ]
        if extra_parents:
            chunks.append((CHUNK_ID_EXTRA_PARENTS, len(extra_parents) * 4))
        chunks.append((b"\x00\x00\x00\x00", 0)) # Terminator
        
        offset = 8 + (len(chunks) * 12)
        table = bytearray()
        chunk_body = bytearray()
        
        for cid, size in chunks:
            table.extend(cid)
            table.extend(struct.pack(">Q", offset))
            if cid == CHUNK_ID_OID_FANOUT: chunk_body.extend(struct.pack(">256I", *fanout))
            elif cid == CHUNK_ID_OID_LOOKUP: chunk_body.extend(b"".join(oids))
            elif cid == CHUNK_ID_COMMIT_DATA: chunk_body.extend(cdat)
            elif cid == CHUNK_ID_EXTRA_PARENTS: chunk_body.extend(struct.pack(f">{len(extra_parents)}I", *extra_parents))
            offset += size
            
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph_path.write_bytes(header + table + chunk_body)

def build_history_graph(dg_dir: Path):
    """Scan and index all commits with generation numbers."""
    from deep.storage.objects import Commit, read_object, walk_loose_shas
    objects_dir = dg_dir / "objects"
    commits: Dict[str, Commit] = {}
    
    # 1. Collect all commits
    for sha in walk_loose_shas(objects_dir):
        try:
            obj = read_object(objects_dir, sha)
            if isinstance(obj, Commit):
                commits[sha] = obj
        except Exception: continue
        
    if not commits: return 0
    
    # 2. Compute Generation Numbers (Post-order traversal)
    generations: Dict[str, int] = {}
    
    def get_gen(sha: str) -> int:
        if sha in generations: return generations[sha]
        c = commits.get(sha)
        if not c: return 0 # Base case or missing history
        
        if not c.parent_shas:
            generations[sha] = 1
            return 1
            
        g = 1 + max((get_gen(p) for p in c.parent_shas), default=0)
        generations[sha] = g
        return g

    for sha in commits: get_gen(sha)
    
    # 3. Write DHGX
    cg = DeepHistoryGraph(dg_dir)
    cg.write(list(commits.values()), generations)
    return len(commits)

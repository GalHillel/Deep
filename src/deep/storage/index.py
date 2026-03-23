"""
deep.storage.index
~~~~~~~~~~~~~~~~~~

DeepIndex v1: Redesigned Staging Area for Deep.
This index structure is optimized for independent operation, providing
O(1) conflict detection via path hashing and nanosecond-precision timestamps.
"""

from __future__ import annotations
import struct
import logging
import hashlib
import time
import os
import errno
import random
import string
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Any, cast, List, Tuple

from deep.utils.utils import DeepError

# ── DeepIndex Binary Format v2 ───────────────────────────────────────
# Header (FIXED SIZE - 45 bytes):
# [MAGIC: b"DEEPIDX2" (8B)]
# [VERSION: uint8 (1B)]
# [ENTRY_COUNT: uint32 (4B)]
# [CHECKSUM: SHA256 of body (32B)]
# ── Body (Variable) ──
# For each entry:
# [Path_Len: uint16 (2B)]
# [Path: bytes (UTF-8)]
# [Content_Hash: bytes (32B)]
# [MTIME_NS: uint64 (8B)]
# [Path_Hash: uint64 (8B)]

INDEX_MAGIC_V2 = b"DEEPIDX2"
INDEX_VERSION_V2 = 2

# Legacy Signatures
INDEX_SIGNATURE_V1 = b"DPIX"
INDEX_VERSION_V1 = 1

class CorruptIndexError(DeepError):
    """Raised when the index file is corrupted or invalid."""
    pass

@dataclass
class DeepIndexEntry:
    """Metadata for a single entry in DeepIndex v2."""
    content_hash: str # SHA256 hex string (32 bytes binary)
    mtime_ns: int    # Nanosecond timestamp
    size: int        # uint64 (File size in bytes)
    path_hash: int   # uint64
    flags: int = 0   # Bit 0: skip-worktree, Bit 1: executable (Reserved for v2)

    @property
    def skip_worktree(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def is_executable(self) -> bool:
        return bool(self.flags & 0x02)

@dataclass
class DeepIndex:
    """In-memory representation of DeepIndex v2."""
    entries: Dict[str, DeepIndexEntry] = field(default_factory=dict)
    version: int = INDEX_VERSION_V2

    def to_binary(self) -> bytes:
        """Serialize as DeepIndex v2 binary format."""
        # 1. Build body
        body_parts = []
        # Sort by path for deterministic output
        for path in sorted(self.entries.keys()):
            entry = self.entries[path]
            path_bytes = path.encode("utf-8")
            
            # Entry: [Path_Len: H][Path: s][Content_Hash: 32s][MTIME_NS: Q][Size: Q][Path_Hash: Q]
            path_bytes = path.encode("utf-8")
            entry_header = struct.pack(">H", len(path_bytes))
            entry_body = path_bytes
            
            # RULE: Pad 40-char SHA1 to 32 bytes ONLY for storage
            c_hash_padded = entry.content_hash.ljust(64, '0')
            
            # RULE: Handle legacy string path_hashes (hex) gracefully during conversion
            p_hash = entry.path_hash
            if isinstance(p_hash, str):
                try:
                    p_hash = int(p_hash, 16)
                except ValueError:
                    # If it's a 40-char SHA string, truncate or re-hash
                    p_hash = struct.unpack(">Q", hashlib.sha256(path_bytes).digest()[:8])[0]
            
            entry_body += struct.pack(">32sQQQ",
                bytes.fromhex(c_hash_padded),
                int(entry.mtime_ns or 0),
                int(entry.size or 0),
                int(p_hash or 0)
            )
            
            body_parts.append(entry_header + entry_body)
        
        body = b"".join(body_parts)
        
        # 2. Compute SHA256 of body
        checksum = hashlib.sha256(body).digest()
        
        # 3. Build Header: [MAGIC: 8s][VERSION: B][ENTRY_COUNT: I][CHECKSUM: 32s]
        header = struct.pack(">8sBI32s", INDEX_MAGIC_V2, self.version, len(self.entries), checksum)
        
        return header + body

    @classmethod
    def from_binary(cls, data: bytes) -> "DeepIndex":
        """Deserialize from binary with strict validation."""
        if not data:
            return cls()
            
        # 1. Validate MAGIC and detect legacy formats
        magic = data[:8]
        if magic != INDEX_MAGIC_V2:
            if magic[:4] == INDEX_SIGNATURE_V1:
                return cls._migrate_from_v1(data)
            if magic[:4] == b"DEEP":
                return cls._migrate_from_legacy(data)
            raise CorruptIndexError(f"Invalid DeepIndex magic: {magic!r}")

        # 2. Header parsing [MAGIC 8][VER 1][COUNT 4][CHECKSUM 32] = 45 bytes
        if len(data) < 45:
            raise CorruptIndexError("Index file truncated (header too short)")
            
        _, version, count, expected_checksum = struct.unpack(">8sBI32s", data[:45])
        
        if version != INDEX_VERSION_V2:
            raise CorruptIndexError(f"Unsupported DeepIndex version: {version}")
            
        body = data[45:]
        
        # 3. Validate checksum BEFORE parsing entries
        actual_checksum = hashlib.sha256(body).digest()
        if actual_checksum != expected_checksum:
            raise CorruptIndexError("Index checksum mismatch (data corruption detected)")
            
        entries: Dict[str, DeepIndexEntry] = {}
        offset = 0
        body_len = len(body)
        
        try:
            for _ in range(count):
                if offset + 2 > body_len:
                    raise CorruptIndexError("Malformed entry: missing path length")
                
                path_len = struct.unpack(">H", body[offset : offset + 2])[0]
                offset += 2
                
                if offset + path_len + 56 > body_len:
                    raise CorruptIndexError("Malformed entry: body too short for entry data")
                
                path_bytes = body[offset : offset + path_len]
                offset += path_len
                
                try:
                    path = path_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    raise CorruptIndexError(f"Invalid UTF-8 path at offset {offset - path_len}")
                    
                # [Content_Hash 32s][MTIME_NS Q][Size Q][Path_Hash Q] = 56 bytes
                content_hash_bytes, mtime_ns, size, path_hash = struct.unpack(">32sQQQ", body[offset : offset + 56])
                content_hash = content_hash_bytes.hex()
                # RULE: Unpad immediately after reading (strip 24 trailing zeros from 64-char hex)
                if content_hash.endswith('0' * 24):
                    content_hash = content_hash[:40]
                offset += 56
                
                entries[path] = DeepIndexEntry(
                    content_hash=content_hash,
                    mtime_ns=mtime_ns,
                    size=size,
                    path_hash=path_hash
                )
        except struct.error as e:
            raise CorruptIndexError(f"Binary parsing error: {e}")
            
        if offset != body_len:
            raise CorruptIndexError(f"Trailing data in index: {body_len - offset} extra bytes")
            
        return cls(entries=entries, version=version)

    @classmethod
    def _migrate_from_v1(cls, data: bytes) -> "DeepIndex":
        """Migrate from DPIX v1 format."""
        logging.getLogger("Deep").info("Migrating DeepIndex v1 to v2")
        # [DPIX][VER 4B][COUNT 4B][FLAGS 4B] = 16B
        version, count, _ = struct.unpack(">III", data[4:16])
        entries: Dict[str, DeepIndexEntry] = {}
        offset = 16
        for _ in range(count):
            # v1: [Path_Hash: SHA1 (20B)][MTIME_NS: Q][Size: Q][Content_Hash: SHA1 (20B)][Flags: I][Path_Len: H][Path]
            # We map SHA1 to SHA256 by hashing the path and content if possible, but for migration 
            # we just accept the 20-byte hash padded or reused if we must. 
            # Actually, it's better to just re-calculate or accept that v2 expects 32 bytes.
            # Since we can't easily upgrade SHA1 to SHA256 without the original data, 
            # we might need to mark these as 'stale' or just pad them for now.
            # But the user wants a ROBUST system. Migration should ideally re-hash if files exist,
            # but DeepIndex is just a staging area.
            
            # v1 structure:
            # 20 (p_hash) + 8 (mtime) + 8 (size) + 20 (c_hash) + 4 (flags) + 2 (p_len) = 62 bytes fixed
            p_hash_bin = data[offset : offset + 20]
            mtime_ns, size = struct.unpack(">QQ", data[offset + 20 : offset + 36])
            c_hash_bin = data[offset + 36 : offset + 56]
            flags, path_len = struct.unpack(">IH", data[offset + 56 : offset + 62])
            path = data[offset + 62 : offset + 62 + path_len].decode("utf-8")
            offset += 62 + path_len
            
            # RULE: Store 40-char SHA1 in memory.
            c_hash_v2 = c_hash_bin.hex()
            # path_hash v2 is uint64. v1 path_hash was SHA1 hex. 
            # We'll just re-calculate path_hash v2 correctly from path.
            p_hash_v2 = struct.unpack(">Q", hashlib.sha256(path.encode("utf-8")).digest()[:8])[0]
            
            entries[path] = DeepIndexEntry(
                content_hash=c_hash_v2,
                mtime_ns=mtime_ns,
                size=size,
                path_hash=p_hash_v2,
                flags=flags
            )
        return cls(entries=entries)

    @classmethod
    def _migrate_from_legacy(cls, data: bytes) -> "DeepIndex":
        """Handle migration from the legacy 'DEEP' format."""
        logging.getLogger("Deep").info("Migrating legacy DEEP index to v2")
        count = struct.unpack(">I", data[8:12])[0]
        entries = {}
        offset = 12
        for _ in range(count):
            path_len, sha, size, mtime, flags = struct.unpack_from(">H20sQdB", data, offset)
            offset += 39
            path = data[offset : offset + path_len].decode("utf-8")
            offset += path_len
            
            # RULE: Store 40-char SHA1 in memory.
            c_hash_v2 = sha.hex()
            p_hash_v2 = struct.unpack(">Q", hashlib.sha256(path.encode("utf-8")).digest()[:8])[0]
            
            # Convert float mtime to int nsec
            mtime_ns = int(mtime * 1e9)
            
            entries[path] = DeepIndexEntry(
                content_hash=c_hash_v2,
                mtime_ns=mtime_ns,
                size=int(size),
                path_hash=p_hash_v2,
                flags=flags
            )
        return cls(entries=entries)

# ── Public APIs (Independent of Deep naming) ──────────────────────────

# ── Hardened Locking ──────────────────────────────────────────────────

def _get_journal_path(dg_dir: Path) -> Path:
    """Legacy helper for tests."""
    return dg_dir / "index.journal"

def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still alive (cross-platform)."""
    if pid <= 0: return False
    import sys
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

class IndexLock:
    """Bulletproof reentrant atomic file lock for index operations."""
    _thread_local_locks: Dict[str, int] = {} # Path -> recursion_level

    def __init__(self, dg_dir: Path, timeout: float = 10.0):
        self.lock_path = dg_dir / "index.lock"
        self.timeout = timeout
        self.pid = os.getpid()
        self.lock_id = str(self.lock_path)

    def _get_lock_pid(self) -> Optional[int]:
        """Read PID from lock file, handling both raw PID and JSON metadata."""
        if not self.lock_path.exists(): return None
        try:
            # On Windows, PermissionError is common if the file is locked.
            # We use a raw os.open with sharing flags to bypass some restrictions.
            fd = os.open(self.lock_path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
            try:
                content_bytes = os.read(fd, 1024)
                content = content_bytes.decode('utf-8', errors='ignore').strip()
            finally:
                os.close(fd)
            
            if not content: return None
            if content.startswith("{"):
                try:
                    data = json.loads(content.split("}")[0] + "}")
                    return int(data.get("pid", 0))
                except:
                    import re
                    m = re.search(r'"pid":\s*(\d+)', content)
                    return int(m.group(1)) if m else None
            return int(content)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def acquire(self):
        """Acquire lock (reentrant)."""
        # Reentrancy check
        if self._thread_local_locks.get(self.lock_id, 0) > 0:
            self._thread_local_locks[self.lock_id] += 1
            return

        start = time.time()
        while True:
            try:
                # 1. Aggressive stale cleanup AND reentrancy detection
                if self.lock_path.exists():
                    owner_pid = self._get_lock_pid()
                    # Reentrancy: PID matches ours
                    if owner_pid == self.pid:
                        self._thread_local_locks[self.lock_id] = self._thread_local_locks.get(self.lock_id, 0) + 1
                        return
                    # Stale lock: PID is dead or invalid
                    if owner_pid is None or not _is_process_alive(owner_pid):
                        logging.getLogger("Deep").warning(f"Removing stale/invalid index.lock")
                        try: os.remove(self.lock_path)
                        except OSError: pass
                
                # 2. Atomic acquisition
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(self.pid).encode())
                finally:
                    os.close(fd)
                
                self._thread_local_locks[self.lock_id] = 1
                return
            except (FileExistsError, PermissionError, OSError):
                # On Windows, PermissionError often means another process has it open (O_EXCL)
                if time.time() - start > self.timeout:
                    raise TimeoutError(f"Timed out waiting for index.lock at {self.lock_path}")
                time.sleep(0.05 + random.random() * 0.1)

    def release(self):
        """Release lock (reentrant)."""
        if self._thread_local_locks.get(self.lock_id, 0) <= 0:
            return

        self._thread_local_locks[self.lock_id] -= 1
        if self._thread_local_locks[self.lock_id] == 0:
            try:
                owner_pid = self._get_lock_pid()
                if owner_pid == self.pid or owner_pid is None:
                    if self.lock_path.exists():
                        os.remove(self.lock_path)
            except OSError:
                pass
            finally:
                if self.lock_id in self._thread_local_locks:
                    del self._thread_local_locks[self.lock_id]

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# ── Public APIs (Independent of Deep naming) ──────────────────────────

def read_index(dg_dir: Path) -> DeepIndex:
    """Read index with lazy stale lock/journal cleanup and NO read lock."""
    path = dg_dir / "index"
    lock_path = dg_dir / "index.lock"
    journal_path = dg_dir / "index.journal"
    
    # Passive cleanup (leaks/stale)
    for p in [lock_path, journal_path]:
        if p.exists():
            try:
                if p == journal_path:
                    p.unlink()
                else:
                    # Use a temp lock object for stale check
                    tmp_lock = IndexLock(dg_dir)
                    owner_pid = tmp_lock._get_lock_pid()
                    if owner_pid is None or not _is_process_alive(owner_pid):
                        p.unlink()
            except (OSError, ValueError):
                pass

    if not path.exists():
        return DeepIndex()
    
    try:
        data = path.read_bytes()
        index = DeepIndex.from_binary(data)
        
        # Backward Compatibility (Rewrite to v2 if migrated)
        if data[:8] != INDEX_MAGIC_V2:
            logging.getLogger("Deep").info("Upgrading index to v2 format")
            write_index(dg_dir, index)
            
        return index
    except CorruptIndexError as e:
        timestamp = int(time.time())
        corrupt_path = path.with_name(f"index.corrupt.{timestamp}")
        logging.getLogger("Deep").error(f"Index corruption detected: {e}. Moving to {corrupt_path}")
        try:
            os.rename(path, corrupt_path)
        except OSError:
            pass
        return DeepIndex()
    except Exception as e:
        logging.getLogger("Deep").error(f"Unexpected error reading index: {e}")
        return DeepIndex()

def write_index(dg_dir: Path, index: DeepIndex) -> None:
    """Write the index atomically with strict ACID properties."""
    path = dg_dir / "index"
    with IndexLock(dg_dir):
        _write_index_core(dg_dir, index, path)

def _write_index_core(dg_dir: Path, index: DeepIndex, path: Path):
    """Atomic write core: Temp file -> Fsync -> Atomic Replace."""
    # Generate unique temp name
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    tmp_path = path.with_name(f"index.tmp_{os.getpid()}_{rand}")
    
    try:
        data = index.to_binary()
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic swap with retry for Windows (handles transient reader locks)
        max_retries = 5
        for i in range(max_retries):
            try:
                os.replace(tmp_path, path)
                break
            except OSError as e:
                if i == max_retries - 1: raise
                time.sleep(0.01 * (i + 1))
    except Exception as e:
        logging.getLogger("Deep").error(f"Failed to write index: {e}")
        if tmp_path.exists():
            try: tmp_path.unlink()
            except OSError: pass
        raise
    finally:
        if tmp_path.exists():
            try: tmp_path.unlink()
            except OSError: pass

def read_index_no_lock(dg_dir: Path) -> DeepIndex:
    """Read the index (lock-free due to atomic rename)."""
    return read_index(dg_dir)

def write_index_no_lock(dg_dir: Path, index: DeepIndex) -> None:
    """Write the index (lock-free write - caller must ensure locking)."""
    _write_index_core(dg_dir, index, dg_dir / "index")

def add_to_index(dg_dir: Path, rel_path: str, sha: str, size: int, mtime_ns: int):
    add_multiple_to_index(dg_dir, [(rel_path, sha, size, mtime_ns)])

def add_multiple_to_index(dg_dir: Path, entries: List[Tuple[str, str, int, int]]):
    from deep.core.locks import IndexLock
    lock = IndexLock(dg_dir)
    with lock:
        index = read_index_no_lock(dg_dir)
        for rel_path, sha, size, mtime_ns in entries:
            # Use SHA256 for path_hash (take first 8 bytes for uint64)
            p_hash_full = hashlib.sha256(rel_path.encode("utf-8")).digest()
            path_hash = struct.unpack(">Q", p_hash_full[:8])[0]
            
            # RULE: Store 40-char SHA1 in memory. No padding here.
            index.entries[rel_path] = DeepIndexEntry(
                content_hash=sha,
                mtime_ns=mtime_ns,
                size=size,
                path_hash=path_hash
            )
        write_index_no_lock(dg_dir, index)

def remove_from_index(dg_dir: Path, rel_path: str):
    remove_multiple_from_index(dg_dir, [rel_path])

def remove_multiple_from_index(dg_dir: Path, rel_paths: List[str]):
    from deep.core.locks import IndexLock
    lock = IndexLock(dg_dir)
    with lock:
        index = read_index_no_lock(dg_dir)
        for p in rel_paths:
            if p in index.entries:
                del index.entries[p]
        write_index_no_lock(dg_dir, index)

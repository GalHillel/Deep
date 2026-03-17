"""
deep.storage.vault
~~~~~~~~~~~~~~~~~~
DeepVault (DVPF) is the primary archival storage format for Deep objects.
It replaces legacy packfiles with a versioned, integrity-checked binary container.
"""

from __future__ import annotations
import os
import struct
import zlib
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, BinaryIO, Union
from dataclasses import dataclass

VAULT_MAGIC = b"DVPF"
VAULT_VERSION = 1

@dataclass
class VaultEntry:
    sha: str
    offset: int
    size: int
    obj_type: str

class DeepVaultWriter:
    """Creates a DeepVault (DVPF) container from a list of objects."""
    
    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.vault_dir = dg_dir / "objects" / "vault"
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    def create_vault(self, objects: List[tuple[str, str, bytes]]) -> Tuple[str, Path]:
        """
        Write objects into a DVPF container.
        Args:
            objects: List of (sha, type, raw_content)
        Returns:
            (vault_sha, vault_path)
        """
        body = bytearray()
        entries: List[VaultEntry] = []
        
        # 1. Build body and collect offsets
        for sha, o_type, content in objects:
            offset = len(body)
            compressed = zlib.compress(content)
            # Each block: [type_len(1B)][type_str][data_len(4B)][compressed_data]
            type_bytes = o_type.encode("ascii")
            block = struct.pack(">B", len(type_bytes)) + type_bytes
            block += struct.pack(">I", len(compressed)) + compressed
            body.extend(block)
            entries.append(VaultEntry(sha, offset, len(block), o_type))

        # 2. Build Header
        # [magic(4B)][version(1B)][flags(1B)][count(4B)]
        header = VAULT_MAGIC
        header += struct.pack(">B B I", VAULT_VERSION, 0, len(entries))
        
        # 3. Build Object Table (for O(1) lookup inside the vault)
        # [sha(20B)][offset(8B)][size(4B)]
        table = bytearray()
        for entry in entries:
            table.extend(bytes.fromhex(entry.sha))
            table.extend(struct.pack(">Q I", entry.offset, entry.size))
            
        # 4. Assemble and Hash
        # Content = Header + Table + Body
        content = header + table + body
        integrity_hash = hashlib.sha256(content).hexdigest()
        
        # Footer: [checksum(32B)]
        footer = hashlib.sha256(content).digest()
        final_data = content + footer
        
        vault_path = self.vault_dir / f"{integrity_hash}.dvpf"
        vault_path.write_bytes(final_data)
        
        return integrity_hash, vault_path

class DeepVaultReader:
    """Reads objects from DeepVault (DVPF) containers."""
    
    def __init__(self, vault_path: Path):
        self.path = vault_path
        self._data = vault_path.read_bytes()
        self._validate()
        self._parse_header()

    def _validate(self):
        if len(self._data) < 42: # magic(4) + ver(1) + flags(1) + count(4) + footer(32)
            raise ValueError(f"Invalid DeepVault file: too small ({self.path})")
        
        magic = self._data[:4]
        if magic != VAULT_MAGIC:
            raise ValueError(f"Invalid DeepVault signature: {magic}")
            
        # Verify integrity
        content = self._data[:-32]
        actual_hash = self._data[-32:]
        expected_hash = hashlib.sha256(content).digest()
        if actual_hash != expected_hash:
            raise ValueError(f"DeepVault integrity check failed for {self.path}")

    def _parse_header(self):
        self.version = self._data[4]
        self.flags = self._data[5]
        self.count = struct.unpack(">I", self._data[6:10])[0]
        self._table_offset = 10
        self._body_offset = 10 + (self.count * 32) # sha(20) + off(8) + size(4)

    def get_object(self, sha: str) -> Optional[Tuple[str, bytes]]:
        """Find and return (type, raw_content) for a given SHA."""
        sha_bytes = bytes.fromhex(sha)
        
        # Binary search in the table
        low = 0
        high = self.count - 1
        
        while low <= high:
            mid = (low + high) // 2
            entry_pos = self._table_offset + (mid * 32)
            mid_sha = self._data[entry_pos : entry_pos + 20]
            
            if mid_sha == sha_bytes:
                off = struct.unpack(">Q", self._data[entry_pos + 20 : entry_pos + 28])[0]
                size = struct.unpack(">I", self._data[entry_pos + 28 : entry_pos + 32])[0]
                return self._read_block(off, size)
            elif mid_sha < sha_bytes:
                low = mid + 1
            else:
                high = mid - 1
                
        return None

    def _read_block(self, offset: int, size: int) -> Tuple[str, bytes]:
        pos = self._body_offset + offset
        # [type_len(1B)][type_str][data_len(4B)][compressed_data]
        type_len = self._data[pos]
        obj_type = self._data[pos + 1 : pos + 1 + type_len].decode("ascii")
        data_len = struct.unpack(">I", self._data[pos + 1 + type_len : pos + 5 + type_len])[0]
        compressed = self._data[pos + 5 + type_len : pos + 5 + type_len + data_len]
        return obj_type, zlib.decompress(compressed)

    def list_shas(self) -> List[str]:
        shas = []
        for i in range(self.count):
            pos = self._table_offset + (i * 32)
            shas.append(self._data[pos : pos + 20].hex())
        return shas

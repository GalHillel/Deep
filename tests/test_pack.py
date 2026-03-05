"""
tests.test_pack
~~~~~~~~~~~~~~~
Tests for binary packfile creation and extraction.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from deep.storage.objects import Blob, Tree, TreeEntry, read_object
from deep.storage.pack import create_pack, unpack


@pytest.fixture()
def objects_dir(tmp_path: Path) -> Path:
    d = tmp_path / "objects"
    d.mkdir()
    return d


def test_pack_unpack_round_trip(objects_dir: Path) -> None:
    # 1. Create a few objects
    b1 = Blob(data=b"hello pack")
    sha1 = b1.write(objects_dir)
    
    b2 = Blob(data=b"world pack")
    sha2 = b2.write(objects_dir)
    
    tree = Tree(entries=[
        TreeEntry(mode="100644", name="f1.txt", sha=sha1),
        TreeEntry(mode="100644", name="f2.txt", sha=sha2),
    ])
    sha3 = tree.write(objects_dir)
    
    shas = [sha1, sha2, sha3]
    
    # 2. Create packfile
    pack_data = create_pack(objects_dir, shas)
    assert len(pack_data) > 32 # header + trailer
    
    # 3. Wipe objects directory
    import shutil
    shutil.rmtree(objects_dir)
    objects_dir.mkdir()
    
    # 4. Unpack
    count = unpack(pack_data, objects_dir)
    assert count == 3
    
    # 5. Verify objects are restored
    for sha in shas:
        obj = read_object(objects_dir, sha)
        assert obj.sha == sha


def test_unpack_corrupt_trailer(objects_dir: Path) -> None:
    b1 = Blob(data=b"data")
    sha1 = b1.write(objects_dir)
    pack_data = create_pack(objects_dir, [sha1])
    
    # Corrupt last byte of trailer
    corrupt_pack = pack_data[:-1] + b"\xff"
    
    with pytest.raises(ValueError, match="trailer SHA-1 mismatch"):
        unpack(corrupt_pack, objects_dir)


def test_unpack_corrupt_crc(objects_dir: Path) -> None:
    b1 = Blob(data=b"some data for crc test")
    sha1 = b1.write(objects_dir)
    pack_data = create_pack(objects_dir, [sha1])
    
    # Header is 12 bytes. 
    # Entry meta is 9 bytes (type, orig_size, compr_size).
    # Data is N bytes.
    # CRC is 4 bytes.
    # Trailer is 20 bytes.
    
    # Let's flip a bit in the compressed data area (offset 12 + 9 = 21)
    pack_list = list(pack_data)
    pack_list[21] ^= 0x01
    corrupt_pack = bytes(pack_list)
    
    # Note: Flipping a bit also breaks the trailer, so we need to fix it or catch CRC first.
    # Actually, the trailer is checked FIRST in our implementation.
    # To test CRC, we need a valid trailer but invalid CRC.
    
    import hashlib
    data_without_trailer = corrupt_pack[:-20]
    new_trailer = hashlib.sha1(data_without_trailer).digest()
    corrupt_pack_fixed_trailer = data_without_trailer + new_trailer
    
    with pytest.raises(ValueError, match="CRC mismatch"):
        unpack(corrupt_pack_fixed_trailer, objects_dir)


def test_unpack_invalid_signature(objects_dir: Path) -> None:
    bad_pack = b"BAD!" + b"\x00" * 30
    # Add a fake 20-byte trailer to pass length check if needed
    bad_pack += b"\x00" * 20
    
    # Fix trailer to pass the first check
    import hashlib
    bad_pack = bad_pack[:-20] + hashlib.sha1(bad_pack[:-20]).digest()
    
    with pytest.raises(ValueError, match="Invalid packfile signature"):
        unpack(bad_pack, objects_dir)

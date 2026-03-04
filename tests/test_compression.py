"""
tests.test_compression
~~~~~~~~~~~~~~~~~~~~~~
Tests for transparent object compression and backward compatibility.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from deep_git.core.objects import Blob, Commit, Tag, Tree, TreeEntry, read_object, hash_bytes
from deep_git.core.utils import AtomicWriter


@pytest.fixture()
def objects_dir(tmp_path: Path) -> Path:
    d = tmp_path / "objects"
    d.mkdir()
    return d


def test_round_trip_blob(objects_dir: Path) -> None:
    data = b"hello compression"
    blob = Blob(data=data)
    sha = blob.write(objects_dir)
    
    # Verify disk content is compressed
    path = objects_dir / sha[:2] / sha[2:]
    disk_bytes = path.read_bytes()
    # If it's compressed, decompressing should work and not be equal to original
    uncompressed = zlib.decompress(disk_bytes)
    assert uncompressed != disk_bytes
    assert b"blob 17\x00hello compression" == uncompressed
    
    # Read back
    read_blob = read_object(objects_dir, sha)
    assert isinstance(read_blob, Blob)
    assert read_blob.data == data


def test_backward_compatibility(objects_dir: Path) -> None:
    # Manually write an uncompressed object
    content = b"content for uncompressed"
    header = f"blob {len(content)}".encode("ascii")
    raw = header + b"\x00" + content
    sha = hash_bytes(raw)
    
    path = objects_dir / sha[:2] / sha[2:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    
    # Read it back using the new robust read_object
    read_blob = read_object(objects_dir, sha)
    assert isinstance(read_blob, Blob)
    assert read_blob.data == content


def test_sha_consistency(objects_dir: Path) -> None:
    data = b"same content"
    
    # 1. Write as compressed (normal way)
    blob = Blob(data=data)
    sha_compressed = blob.write(objects_dir)
    
    # 2. Write as uncompressed (manual way)
    raw = blob.full_serialize()
    sha_uncompressed = hash_bytes(raw)
    
    assert sha_compressed == sha_uncompressed
    
    # Both should be readable and return same object
    obj1 = read_object(objects_dir, sha_compressed)
    obj2 = read_object(objects_dir, sha_uncompressed)
    assert obj1.serialize_content() == obj2.serialize_content()


def test_corruption_handling(objects_dir: Path) -> None:
    # Random garbage that is neither valid zlib nor starts with valid header
    sha = "f" * 40
    path = objects_dir / sha[:2] / sha[2:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a valid object")
    
    with pytest.raises(ValueError, match="corrupted or in an unknown format"):
        read_object(objects_dir, sha)


def test_tree_compression(objects_dir: Path) -> None:
    entry = TreeEntry(mode="100644", name="f.txt", sha="a" * 40)
    tree = Tree(entries=[entry])
    sha = tree.write(objects_dir)
    
    read_tree = read_object(objects_dir, sha)
    assert isinstance(read_tree, Tree)
    assert len(read_tree.entries) == 1
    assert read_tree.entries[0].name == "f.txt"

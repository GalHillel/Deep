"""
tests.test_storage_validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Phase 7: Storage layer validation — deterministic hashing, compression,
integrity, and content-addressability.
"""

from __future__ import annotations

import hashlib
import zlib
from pathlib import Path

import pytest

from deep.storage.objects import (
    Blob, Commit, Tree, TreeEntry, Tag,
    read_object, hash_bytes, _serialize, _object_path,
)
from deep.storage.pack import create_pack, unpack
from deep.core.repository import DEEP_DIR
from deep.cli.main import main
import os


@pytest.fixture()
def repo(tmp_path: Path):
    os.chdir(tmp_path)
    main(["init"])
    return tmp_path


class TestDeterministicHashing:
    """Same content must always produce the same SHA."""

    def test_blob_determinism(self, repo):
        b1 = Blob(data=b"hello world")
        b2 = Blob(data=b"hello world")
        assert b1.sha == b2.sha

    def test_blob_different_content(self, repo):
        b1 = Blob(data=b"hello")
        b2 = Blob(data=b"world")
        assert b1.sha != b2.sha

    def test_tree_determinism(self, repo):
        entries = [TreeEntry(mode="100644", name="a.txt", sha="a" * 40)]
        t1 = Tree(entries=list(entries))
        t2 = Tree(entries=list(entries))
        assert t1.sha == t2.sha

    def test_commit_determinism(self, repo):
        c1 = Commit(tree_sha="a" * 40, message="test", timestamp=1000, timezone="+0000")
        c2 = Commit(tree_sha="a" * 40, message="test", timestamp=1000, timezone="+0000")
        assert c1.sha == c2.sha

    def test_sha_matches_git_format(self, repo):
        """SHA = sha1(type + SP + size + NUL + content)"""
        b = Blob(data=b"hello")
        content = b.serialize_content()
        canonical = f"blob {len(content)}\0".encode() + content
        expected = hashlib.sha1(canonical).hexdigest()
        assert b.sha == expected


class TestCompression:
    """Objects should be stored compressed."""

    def test_written_object_is_compressed(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        b = Blob(data=b"test compression data " * 100)
        sha = b.write(objects_dir)
        path = _object_path(objects_dir, sha)
        raw_on_disk = path.read_bytes()
        # Should be zlib-compressed
        decompressed = zlib.decompress(raw_on_disk)
        assert b"blob " in decompressed

    def test_compressed_smaller_than_raw(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        data = b"repetitive data " * 500
        b = Blob(data=data)
        sha = b.write(objects_dir)
        path = _object_path(objects_dir, sha)
        assert path.stat().st_size < len(data)


class TestIntegrity:
    """Written objects must be readable and match their SHA."""

    def test_write_read_roundtrip_blob(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        original = Blob(data=b"integrity test")
        sha = original.write(objects_dir)
        recovered = read_object(objects_dir, sha)
        assert isinstance(recovered, Blob)
        assert recovered.data == original.data

    def test_write_read_roundtrip_tree(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        blob = Blob(data=b"file content")
        blob_sha = blob.write(objects_dir)
        tree = Tree(entries=[TreeEntry(mode="100644", name="file.txt", sha=blob_sha)])
        tree_sha = tree.write(objects_dir)
        recovered = read_object(objects_dir, tree_sha)
        assert isinstance(recovered, Tree)
        assert len(recovered.entries) == 1
        assert recovered.entries[0].name == "file.txt"

    def test_write_read_roundtrip_commit(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        c = Commit(tree_sha="a" * 40, message="test commit", timestamp=1000, timezone="+0000")
        sha = c.write(objects_dir)
        recovered = read_object(objects_dir, sha)
        assert isinstance(recovered, Commit)
        assert recovered.tree_sha == "a" * 40
        assert recovered.message == "test commit"


class TestContentAddressability:
    """Two identical objects must share the same storage location."""

    def test_duplicate_blob_no_double_write(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        b1 = Blob(data=b"duplicate")
        sha1 = b1.write(objects_dir)
        path = _object_path(objects_dir, sha1)
        mtime_before = path.stat().st_mtime

        b2 = Blob(data=b"duplicate")
        sha2 = b2.write(objects_dir)
        assert sha1 == sha2
        # File should not be rewritten
        assert path.stat().st_mtime == mtime_before

    def test_different_content_different_sha(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        sha1 = Blob(data=b"alpha").write(objects_dir)
        sha2 = Blob(data=b"beta").write(objects_dir)
        assert sha1 != sha2


class TestPackfileIntegrity:
    """Packfiles must preserve all objects perfectly."""

    def test_pack_unpack_roundtrip(self, repo):
        objects_dir = repo / DEEP_DIR / "objects"
        shas = []
        for i in range(5):
            b = Blob(data=f"pack test {i}".encode())
            shas.append(b.write(objects_dir))

        pack_data = create_pack(objects_dir, shas)
        # Unpack into a fresh dir
        fresh_dir = repo / "fresh_objects"
        fresh_dir.mkdir()
        count = unpack(pack_data, fresh_dir)
        assert count == 5

        for sha in shas:
            obj = read_object(fresh_dir, sha)
            assert isinstance(obj, Blob)

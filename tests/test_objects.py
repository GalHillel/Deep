"""
tests.test_objects
~~~~~~~~~~~~~~~~~~~
Unit tests for :mod:`deep_git.core.objects`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_git.core.objects import (
    Blob,
    Commit,
    Tree,
    TreeEntry,
    read_object,
    _serialize,
    _deserialize,
)
from deep_git.core.repository import init_repo


# ── Serialisation helpers ────────────────────────────────────────────

class TestSerialiseDeserialise:
    def test_round_trip(self) -> None:
        raw = _serialize("blob", b"hello")
        obj_type, content = _deserialize(raw)
        assert obj_type == "blob"
        assert content == b"hello"

    def test_size_mismatch_raises(self) -> None:
        bad = b"blob 99\x00short"
        with pytest.raises(ValueError, match="size mismatch"):
            _deserialize(bad)


# ── Blob ─────────────────────────────────────────────────────────────

class TestBlob:
    def test_sha_deterministic(self) -> None:
        b = Blob(data=b"hello world")
        assert b.sha == b.sha

    def test_different_data_different_sha(self) -> None:
        assert Blob(data=b"a").sha != Blob(data=b"b").sha

    def test_serialize_format(self) -> None:
        b = Blob(data=b"hi")
        raw = b.full_serialize()
        assert raw.startswith(b"blob 2\x00")
        assert raw.endswith(b"hi")

    def test_write_and_read(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        objects_dir = dg / "objects"
        b = Blob(data=b"test content")
        sha = b.write(objects_dir)
        assert len(sha) == 40

        loaded = read_object(objects_dir, sha)
        assert isinstance(loaded, Blob)
        assert loaded.data == b"test content"

    def test_idempotent_write(self, tmp_path: Path) -> None:
        """Writing the same blob twice should not error."""
        dg = init_repo(tmp_path)
        objects_dir = dg / "objects"
        b = Blob(data=b"dup")
        sha1 = b.write(objects_dir)
        sha2 = b.write(objects_dir)
        assert sha1 == sha2


# ── Tree ─────────────────────────────────────────────────────────────

class TestTree:
    def _make_blob_sha(self, data: bytes, objects_dir: Path) -> str:
        return Blob(data=data).write(objects_dir)

    def test_serialize_round_trip(self) -> None:
        t = Tree(entries=[
            TreeEntry(mode="100644", name="b.txt", sha="ab" * 20),
            TreeEntry(mode="100644", name="a.txt", sha="cd" * 20),
        ])
        content = t.serialize_content()
        t2 = Tree.from_content(content)
        # Entries should be sorted by name in serialised form.
        assert t2.entries[0].name == "a.txt"
        assert t2.entries[1].name == "b.txt"

    def test_write_and_read(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        objects_dir = dg / "objects"
        sha_a = self._make_blob_sha(b"aaa", objects_dir)
        sha_b = self._make_blob_sha(b"bbb", objects_dir)
        t = Tree(entries=[
            TreeEntry(mode="100644", name="a.txt", sha=sha_a),
            TreeEntry(mode="100644", name="b.txt", sha=sha_b),
        ])
        tree_sha = t.write(objects_dir)
        loaded = read_object(objects_dir, tree_sha)
        assert isinstance(loaded, Tree)
        assert len(loaded.entries) == 2


# ── Commit ───────────────────────────────────────────────────────────

class TestCommit:
    def test_serialize_round_trip(self) -> None:
        c = Commit(
            tree_sha="ab" * 20,
            parent_shas=["cd" * 20],
            author="Alice <alice@x>",
            committer="Bob <bob@x>",
            message="Initial commit",
            timestamp=1700000000,
            timezone="+0200",
        )
        content = c.serialize_content()
        c2 = Commit.from_content(content)
        assert c2.tree_sha == c.tree_sha
        assert c2.parent_shas == c.parent_shas
        assert c2.author == c.author
        assert c2.message == c.message
        assert c2.timestamp == c.timestamp
        assert c2.timezone == c.timezone

    def test_root_commit_no_parent(self) -> None:
        c = Commit(tree_sha="aa" * 20, message="root")
        content = c.serialize_content()
        c2 = Commit.from_content(content)
        assert c2.parent_shas == []

    def test_write_and_read(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        objects_dir = dg / "objects"
        # Create a real tree first.
        b = Blob(data=b"x")
        blob_sha = b.write(objects_dir)
        t = Tree(entries=[TreeEntry(mode="100644", name="x.txt", sha=blob_sha)])
        tree_sha = t.write(objects_dir)

        c = Commit(tree_sha=tree_sha, message="test commit", timestamp=1700000000)
        commit_sha = c.write(objects_dir)

        loaded = read_object(objects_dir, commit_sha)
        assert isinstance(loaded, Commit)
        assert loaded.tree_sha == tree_sha
        assert loaded.message == "test commit"


# ── DAG integrity ────────────────────────────────────────────────────

class TestDAGIntegrity:
    """Verify that commits form a valid DAG."""

    def test_commit_chain(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        objects_dir = dg / "objects"

        # Root commit.
        b1 = Blob(data=b"v1")
        blob1_sha = b1.write(objects_dir)
        t1 = Tree(entries=[TreeEntry("100644", "f.txt", blob1_sha)])
        tree1_sha = t1.write(objects_dir)
        c1 = Commit(tree_sha=tree1_sha, message="first", timestamp=100)
        c1_sha = c1.write(objects_dir)

        # Second commit points to first.
        b2 = Blob(data=b"v2")
        blob2_sha = b2.write(objects_dir)
        t2 = Tree(entries=[TreeEntry("100644", "f.txt", blob2_sha)])
        tree2_sha = t2.write(objects_dir)
        c2 = Commit(
            tree_sha=tree2_sha,
            parent_shas=[c1_sha],
            message="second",
            timestamp=200,
        )
        c2_sha = c2.write(objects_dir)

        # Walk the DAG backwards.
        loaded_c2 = read_object(objects_dir, c2_sha)
        assert isinstance(loaded_c2, Commit)
        assert loaded_c2.parent_shas == [c1_sha]

        loaded_c1 = read_object(objects_dir, loaded_c2.parent_shas[0])
        assert isinstance(loaded_c1, Commit)
        assert loaded_c1.parent_shas == []

        # Verify the trees are reachable.
        loaded_t2 = read_object(objects_dir, loaded_c2.tree_sha)
        assert isinstance(loaded_t2, Tree)
        loaded_b2 = read_object(objects_dir, loaded_t2.entries[0].sha)
        assert isinstance(loaded_b2, Blob)
        assert loaded_b2.data == b"v2"

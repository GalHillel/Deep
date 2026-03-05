"""
tests.test_index_concurrency
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Concurrency stress tests for :mod:`deep.core.index`.

Spawns 20 threads that simultaneously update the index and verifies no data
corruption occurs.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from deep.storage.index import (
    Index,
    IndexEntry,
    read_index,
    remove_index_entry,
    update_index_entry,
    write_index,
)
from deep.core.repository import init_repo


class TestIndexBasic:
    """Non-concurrent index operations."""

    def test_empty_index(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        idx = read_index(dg)
        assert idx.entries == {}

    def test_add_and_read_entry(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        update_index_entry(dg, "hello.txt", sha="ab" * 20, size=5, mtime=1.0)
        idx = read_index(dg)
        assert "hello.txt" in idx.entries
        assert idx.entries["hello.txt"].sha == "ab" * 20
        assert idx.entries["hello.txt"].size == 5

    def test_remove_entry(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        update_index_entry(dg, "a.txt", sha="aa" * 20, size=1, mtime=0.0)
        remove_index_entry(dg, "a.txt")
        idx = read_index(dg)
        assert "a.txt" not in idx.entries

    def test_remove_missing_raises(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        with pytest.raises(KeyError):
            remove_index_entry(dg, "nope.txt")

    def test_json_round_trip(self) -> None:
        idx = Index(entries={
            "foo.py": IndexEntry(sha="ab" * 20, size=100, mtime=12345.0),
        })
        text = idx.to_json()
        loaded = Index.from_json(text)
        assert loaded.entries["foo.py"].sha == "ab" * 20

    def test_overwrite_entry(self, tmp_path: Path) -> None:
        dg = init_repo(tmp_path)
        update_index_entry(dg, "f.txt", sha="aa" * 20, size=1, mtime=0.0)
        update_index_entry(dg, "f.txt", sha="bb" * 20, size=2, mtime=1.0)
        idx = read_index(dg)
        assert idx.entries["f.txt"].sha == "bb" * 20
        assert idx.entries["f.txt"].size == 2


class TestIndexConcurrency:
    """Stress-test the index with many concurrent writers."""

    NUM_THREADS = 20

    def test_concurrent_updates_no_corruption(self, tmp_path: Path) -> None:
        """20 threads each add a unique entry; all must be present at the end."""
        dg = init_repo(tmp_path)
        errors: list[str] = []
        barrier = threading.Barrier(self.NUM_THREADS)

        def worker(thread_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                key = f"file_{thread_id}.txt"
                sha = f"{thread_id:040d}"
                update_index_entry(dg, key, sha=sha, size=thread_id, mtime=float(thread_id))
            except Exception as exc:
                errors.append(f"Thread {thread_id}: {exc}")

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(self.NUM_THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert errors == [], f"Thread errors: {errors}"

        # Verify ALL entries are present and correct.
        idx = read_index(dg)
        assert len(idx.entries) == self.NUM_THREADS
        for i in range(self.NUM_THREADS):
            key = f"file_{i}.txt"
            assert key in idx.entries, f"Missing {key}"
            assert idx.entries[key].sha == f"{i:040d}"
            assert idx.entries[key].size == i

    def test_concurrent_mixed_operations(self, tmp_path: Path) -> None:
        """Threads doing a mix of adds and overwrites must not corrupt."""
        dg = init_repo(tmp_path)
        errors: list[str] = []
        barrier = threading.Barrier(self.NUM_THREADS)

        def worker(thread_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                # Each thread writes to two keys: its own and a shared one.
                own_key = f"own_{thread_id}.txt"
                shared_key = "shared.txt"
                sha = f"{thread_id:040d}"
                update_index_entry(dg, own_key, sha=sha, size=thread_id, mtime=0.0)
                update_index_entry(dg, shared_key, sha=sha, size=thread_id, mtime=0.0)
            except Exception as exc:
                errors.append(f"Thread {thread_id}: {exc}")

        threads = [
            threading.Thread(target=worker, args=(i,))
            for i in range(self.NUM_THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert errors == [], f"Thread errors: {errors}"

        idx = read_index(dg)
        # All own_* keys must be present.
        for i in range(self.NUM_THREADS):
            assert f"own_{i}.txt" in idx.entries
        # shared.txt must exist and hold a valid value from one of the threads.
        assert "shared.txt" in idx.entries
        shared_size = idx.entries["shared.txt"].size
        assert 0 <= shared_size < self.NUM_THREADS

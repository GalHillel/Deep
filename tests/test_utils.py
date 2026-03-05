"""
tests.test_utils
~~~~~~~~~~~~~~~~
Unit tests for :mod:`deep.core.utils`.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

import pytest

from deep.utils.utils import AtomicWriter, hash_bytes


# ── hash_bytes ───────────────────────────────────────────────────────

class TestHashBytes:
    """Verify SHA-1 hashing behaviour."""

    def test_empty_bytes(self) -> None:
        assert hash_bytes(b"") == hashlib.sha1(b"").hexdigest()

    def test_known_value(self) -> None:
        data = b"hello world"
        assert hash_bytes(data) == hashlib.sha1(data).hexdigest()

    def test_deterministic(self) -> None:
        data = b"deep git rocks"
        assert hash_bytes(data) == hash_bytes(data)

    def test_different_inputs_differ(self) -> None:
        assert hash_bytes(b"a") != hash_bytes(b"b")

    def test_returns_40_hex_chars(self) -> None:
        digest = hash_bytes(b"test")
        assert len(digest) == 40
        assert all(c in "0123456789abcdef" for c in digest)


# ── AtomicWriter ─────────────────────────────────────────────────────

class TestAtomicWriter:
    """Verify atomic file-write behaviour."""

    def test_basic_write(self, tmp_path: Path) -> None:
        target = tmp_path / "out.bin"
        with AtomicWriter(target) as aw:
            aw.write(b"hello")
        assert target.read_bytes() == b"hello"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c" / "file.txt"
        with AtomicWriter(target, mode="w") as aw:
            aw.write("nested")
        assert target.read_text() == "nested"

    def test_no_temp_files_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "clean.bin"
        with AtomicWriter(target) as aw:
            aw.write(b"data")
        # Only the target should exist (no leftover .tmp_ files).
        names = [p.name for p in tmp_path.iterdir()]
        assert names == ["clean.bin"]

    def test_target_untouched_on_exception(self, tmp_path: Path) -> None:
        """Simulate a crash — the target must NOT be created."""
        target = tmp_path / "should_not_exist.bin"
        with pytest.raises(RuntimeError):
            with AtomicWriter(target) as aw:
                aw.write(b"partial data")
                raise RuntimeError("simulated crash")
        assert not target.exists()

    def test_no_temp_files_on_exception(self, tmp_path: Path) -> None:
        """After a simulated crash, temp files must be cleaned up."""
        target = tmp_path / "crash.bin"
        with pytest.raises(RuntimeError):
            with AtomicWriter(target) as aw:
                aw.write(b"junk")
                raise RuntimeError("boom")
        leftover = list(tmp_path.iterdir())
        assert leftover == []

    def test_overwrite_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "overwrite.bin"
        target.write_bytes(b"old")
        with AtomicWriter(target) as aw:
            aw.write(b"new")
        assert target.read_bytes() == b"new"

    def test_text_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "text.txt"
        with AtomicWriter(target, mode="w") as aw:
            aw.write("שלום עולם")
        assert target.read_text(encoding="utf-8") == "שלום עולם"

    def test_concurrent_writes_no_corruption(self, tmp_path: Path) -> None:
        """Multiple threads writing to different files must not interfere."""
        errors: list[str] = []

        def writer(idx: int) -> None:
            target = tmp_path / f"file_{idx}.bin"
            try:
                with AtomicWriter(target) as aw:
                    aw.write(f"data-{idx}".encode())
                if target.read_bytes() != f"data-{idx}".encode():
                    errors.append(f"File {idx} corrupted")
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

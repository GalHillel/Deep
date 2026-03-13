"""
tests.test_add_concurrency
~~~~~~~~~~~~~~~~~~~~~~~~~~

Concurrency stress tests for the ``deep add`` command.
"""

from __future__ import annotations

import threading
from pathlib import Path
import os

from deep.cli.main import main
from deep.core.repository import DEEP_DIR
from deep.storage.index import read_index


def test_add_concurrent_threads_no_index_corruption(tmp_path: Path) -> None:
    """Multiple threads running `deep add` in parallel must not corrupt the index."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize repository
    from deep.cli.main import main as deep_main

    deep_main(["init", str(repo)])
    os.chdir(repo)

    # Create 20 distinct files
    num_files = 20
    files = []
    for i in range(num_files):
        f = repo / f"file_{i}.txt"
        f.write_text(f"content {i}")
        files.append(f)

    errors: list[str] = []

    def worker(path: Path) -> None:
        try:
            deep_main(["add", str(path)])
        except Exception as exc:  # pragma: no cover - should not happen
            errors.append(f"{path.name}: {exc}")

    threads = [threading.Thread(target=worker, args=(f,)) for f in files]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"

    dg_dir = repo / DEEP_DIR
    index = read_index(dg_dir)
    # All files should be present in the index
    assert len(index.entries) == num_files
    for i in range(num_files):
        rel = f"file_{i}.txt"
        assert rel in index.entries


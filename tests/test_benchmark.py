"""
tests.test_benchmark
~~~~~~~~~~~~~~~~~~~~
Tests for the performance benchmarking command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.cli.main import main


def test_benchmark_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # Ensure benchmark runs even without a repo initialized (it creates its own temp repo)
    monkeypatch.chdir(tmp_path)
    
    # Run benchmark command
    main(["benchmark"])
    
    out = capsys.readouterr().out
    assert "RESULTS" in out
    assert "Blob Hashing" in out
    assert "Commit Speed" in out
    assert "Benchmark complete" in out


def test_benchmark_no_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # Initialize a repo in current dir
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    # Track initial object count
    from deep.core.repository import DEEP_GIT_DIR
    objects_dir = tmp_path / DEEP_GIT_DIR / "objects"
    initial_objects = list(objects_dir.glob("??/*"))
    
    # Run benchmark
    main(["benchmark"])
    
    # Verify no new objects were added to THIS repo
    final_objects = list(objects_dir.glob("??/*"))
    assert len(initial_objects) == len(final_objects)

"""
tests.test_log_advanced
~~~~~~~~~~~~~~~~~~~~~~~
Tests for deep log advanced options (--oneline, -n, --graph)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.cli.main import main


@pytest.fixture()
def repo_with_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    for i in range(3):
        f = tmp_path / f"file{i}.txt"
        f.write_text(f"content {i}")
        main(["add", str(f.name)])
        main(["commit", "-m", f"commit {i} message"])
        
    return tmp_path


def test_log_oneline(repo_with_commits: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    main(["log", "--oneline"])
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 3
    # Newest commit is first
    assert "commit 2 message" in lines[0]
    assert "commit 1 message" in lines[1]
    assert "commit 0 message" in lines[2]


def test_log_max_count(repo_with_commits: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    main(["log", "-n", "2"])
    out = capsys.readouterr().out
    
    # Should only show 2 commits
    assert "commit 2 message" in out
    assert "commit 1 message" in out
    assert "commit 0 message" not in out


def test_log_graph(repo_with_commits: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    main(["log", "--graph"])
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    # first line should start with "● "
    assert "● " in lines[0]
    # second line should start with "| Author:" or "│ Author:"
    assert "Author:" in lines[1]


def test_log_graph_oneline(repo_with_commits: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    main(["log", "--graph", "--oneline", "-n", "1"])
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert "● " in lines[0]
    assert "commit 2 message" in lines[0]

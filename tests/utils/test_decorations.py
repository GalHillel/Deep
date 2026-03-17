"""
tests.test_decorations
~~~~~~~~~~~~~~~~~~~~~~~
Tests for commit decorations in log and status commands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.core.refs import resolve_head
from deep.cli.main import main


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    return tmp_path


def test_log_decorations(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = repo / "f.txt"
    f.write_text("v1")
    main(["add", str(f)])
    main(["commit", "-m", "c1"])
    
    main(["branch", "feature"])
    
    capsys.readouterr()
    main(["log"])
    out = capsys.readouterr().out
    
    # Both branches should be in the decoration for the commit
    assert "HEAD -> main" in out
    assert "feature" in out


def test_status_detached_head(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = repo / "f.txt"
    f.write_text("v1")
    main(["add", str(f)])
    main(["commit", "-m", "c1"])
    
    head_sha = resolve_head(repo / ".deep")
    assert head_sha is not None
    
    main(["checkout", head_sha])
    
    capsys.readouterr()
    main(["status"])
    out = capsys.readouterr().out
    
    assert f"HEAD detached at {head_sha[:7]}" in out


def test_log_detached_head_decoration(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = repo / "f.txt"
    f.write_text("v1")
    main(["add", str(f)])
    main(["commit", "-m", "c1"])
    
    head_sha = resolve_head(repo / ".deep")
    assert head_sha is not None
    
    # Detach HEAD
    main(["checkout", head_sha])
    
    capsys.readouterr()
    main(["log"])
    out = capsys.readouterr().out
    
    # The output should show HEAD and main
    assert "(HEAD, main)" in out or "(main, HEAD)" in out

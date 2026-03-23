"""
tests.test_rebase
~~~~~~~~~~~~~~~~~
Tests for the linear rebase engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.cli.main import main
from deep.core.errors import DeepCLIException


@pytest.fixture()
def repo_with_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    # Base commit
    fbase = tmp_path / "base.txt"
    fbase.write_text("base")
    main(["add", "base.txt"])
    main(["commit", "-m", "base commit"])
    
    # Create feature branch
    main(["branch", "feature"])
    
    # Commit on main
    fmain = tmp_path / "main.txt"
    fmain.write_text("main")
    main(["add", "main.txt"])
    main(["commit", "-m", "main commit"])
    
    # Checkout feature and make commits
    main(["checkout", "feature"])
    feat1 = tmp_path / "feat1.txt"
    feat1.write_text("feat1")
    main(["add", "feat1.txt"])
    main(["commit", "-m", "feature 1 commit"])
    
    feat2 = tmp_path / "feat2.txt"
    feat2.write_text("feat2")
    main(["add", "feat2.txt"])
    main(["commit", "-m", "feature 2 commit"])
    
    return tmp_path


def test_rebase_linear(repo_with_branches: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Action: rebase feature onto main
    main(["rebase", "main"])
    
    out = capsys.readouterr().out
    assert "Successfully rebased" in out
    
    # Verify the graph: HEAD should have "feature 2", parent "feature 1", grandparent "main commit", great-grandparent "base"
    main(["log", "--oneline", "-n", "4"])
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert "feature 2 commit" in lines[0]
    assert "feature 1 commit" in lines[1]
    assert "main commit" in lines[2]
    assert "base commit" in lines[3]
    
    # Make sure files from both branches exist
    assert (repo_with_branches / "base.txt").exists()
    assert (repo_with_branches / "main.txt").exists()
    assert (repo_with_branches / "feat1.txt").exists()
    assert (repo_with_branches / "feat2.txt").exists()


def test_rebase_fast_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    (tmp_path / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "c1"])
    
    main(["branch", "feat"])
    
    (tmp_path / "f2.txt").write_text("v2")
    main(["add", "f2.txt"])
    main(["commit", "-m", "c2"])
    
    # Current branch: main (at c2)
    # Target branch: feat (at c1)
    # Rebase main onto feat -> up to date
    main(["rebase", "feat"])
    assert "Current branch is up to date." in capsys.readouterr().out
    
    # Now checkout feat and rebase onto main -> fast forward
    main(["checkout", "feat"])
    main(["rebase", "main"])
    assert "Fast-forwarded to main." in capsys.readouterr().out
    
    # Verify feat is at c2
    main(["log", "--oneline", "-n", "1"])
    assert "c2" in capsys.readouterr().out

def test_rebase_conflict_aborts(repo_with_branches: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Create conflict
    f = repo_with_branches / "base.txt"
    f.write_text("feature modifying base")
    main(["add", "base.txt"])
    main(["commit", "-m", "feature modifying base"])
    
    main(["checkout", "main"])
    f.write_text("main modifying base")
    main(["add", "base.txt"])
    main(["commit", "-m", "main modifying base"])
    
    main(["checkout", "feature"])
    
    with pytest.raises(DeepCLIException) as exc:
        main(["rebase", "main"])
        
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "CONFLICT applying commit" in err
    assert "Rebase aborted" in err

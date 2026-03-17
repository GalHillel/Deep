import pytest
import subprocess
import os
from pathlib import Path
from deep.cli.main import main
from deep.core.repository import init_repo
from deep.core.refs import resolve_head, get_branch

def test_checkout_create_branch_from_head(tmp_path, monkeypatch):
    """Test 'deep checkout -b new-branch' explicitly branches from current HEAD."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)

    # commit v1
    (repo_root / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    v1_sha = resolve_head(dg)

    # create branch feat
    main(["checkout", "-b", "feat"])
    
    # Verify branch created
    assert get_branch(dg, "feat") == v1_sha
    
    # Verify HEAD updated to ref: refs/heads/feat
    head_content = (dg / "HEAD").read_text().strip()
    assert head_content == "ref: refs/heads/feat"

def test_checkout_no_args_shows_error(tmp_path, monkeypatch, capsys):
    """Test 'deep checkout' with no arguments raises error."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)

    with pytest.raises(SystemExit):
        main(["checkout"])
    
    captured = capsys.readouterr()
    # Argparse usually prints to stderr for missing arguments
    assert "the following arguments are required: target" in captured.err

def test_checkout_error_handling(tmp_path, monkeypatch, capsys):
    """Test specific DeepError messages."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)

    # 1. Non-existent branch
    with pytest.raises(SystemExit):
        main(["checkout", "nonexistent"])
    assert "DeepError: 'nonexistent' is not a branch" in capsys.readouterr().err

    # 2. Branch already exists with -b
    (repo_root / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    
    with pytest.raises(SystemExit):
        main(["checkout", "-b", "main"])
    assert "DeepError: branch already exists: main" in capsys.readouterr().err

def test_checkout_dirty_state_protection(tmp_path, monkeypatch, capsys):
    """Test protection against overwriting dirty state."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    monkeypatch.chdir(repo_root)

    # v1
    (repo_root / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    
    # v2 in different branch
    main(["checkout", "-b", "feat"])
    (repo_root / "f.txt").write_text("v2")
    main(["add", "f.txt"])
    main(["commit", "-m", "v2"])
    
    # Back to main
    main(["checkout", "main"])
    assert (repo_root / "f.txt").read_text() == "v1"

    # Make dirty in main
    (repo_root / "f.txt").write_text("v1-dirty")
    
    # Try checkout feat (which has v2 for f.txt)
    with pytest.raises(SystemExit):
        main(["checkout", "feat"])
    
    assert "DeepError" in capsys.readouterr().err
    assert (repo_root / "f.txt").read_text() == "v1-dirty" # Preserved

    # Force should work
    main(["checkout", "--force", "feat"])
    assert (repo_root / "f.txt").read_text() == "v2"

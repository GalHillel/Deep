import subprocess
import os
import shutil
import pytest
from pathlib import Path

def get_head_content(repo_dir: Path, bare: bool = False) -> str:
    from deep.core.constants import DEEP_DIR
    dg = repo_dir if bare else repo_dir / DEEP_DIR
    head_path = dg / "HEAD"
    if not head_path.exists():
        return ""
    return head_path.read_text(encoding="utf-8").strip()

def get_config_content(repo_dir: Path, bare: bool = False) -> str:
    from deep.core.constants import DEEP_DIR
    dg = repo_dir if bare else repo_dir / DEEP_DIR
    config_path = dg / "config"
    if not config_path.exists():
        return ""
    return config_path.read_text(encoding="utf-8").strip()

def test_init_default(tmp_path):
    """Verify deep init in the current directory."""
    cwd = tmp_path / "repo"
    cwd.mkdir()
    
    subprocess.run(["deep", "init"], cwd=str(cwd), check=True, capture_output=True)
    
    from deep.core.constants import DEEP_DIR
    assert (cwd / DEEP_DIR).exists()
    assert (cwd / DEEP_DIR).is_dir()
    assert (cwd / DEEP_DIR / "objects").is_dir()
    assert (cwd / DEEP_DIR / "refs" / "heads").is_dir()
    assert (cwd / DEEP_DIR / "HEAD").is_file()
    assert "ref: refs/heads/main" in get_head_content(cwd)

def test_init_with_path(tmp_path):
    """Verify deep init <path> creates the directory if needed."""
    cwd = tmp_path
    repo_path = cwd / "my-project"
    
    subprocess.run(["deep", "init", "my-project"], cwd=str(cwd), check=True, capture_output=True)
    
    from deep.core.constants import DEEP_DIR
    assert repo_path.exists()
    assert (repo_path / DEEP_DIR).exists()
    assert "ref: refs/heads/main" in get_head_content(repo_path)

def test_init_bare(tmp_path):
    """Verify deep init --bare creates a bare repository."""
    cwd = tmp_path / "bare-repo.deep"
    cwd.mkdir()
    
    subprocess.run(["deep", "init", "--bare"], cwd=str(cwd), check=True, capture_output=True)
    
    # In bare repo, the dir itself is the deep dir
    assert (cwd / "objects").is_dir()
    assert (cwd / "refs" / "heads").is_dir()
    assert (cwd / "HEAD").is_file()
    assert (cwd / "config").is_file()
    
    config = get_config_content(cwd, bare=True)
    assert "bare = true" in config
    assert "format_version = 2" in config

def test_init_idempotency(tmp_path):
    """Verify initializing an existing repo is idempotent and doesn't wipe it."""
    cwd = tmp_path / "repo"
    cwd.mkdir()
    
    # First init
    subprocess.run(["deep", "init"], cwd=str(cwd), check=True, capture_output=True)
    from deep.core.constants import DEEP_DIR
    (cwd / DEEP_DIR / "some_data").write_text("don't delete me")
    
    # Second init
    subprocess.run(["deep", "init"], cwd=str(cwd), check=True, capture_output=True)
    
    assert (cwd / DEEP_DIR / "some_data").exists()
    assert (cwd / DEEP_DIR / "some_data").read_text() == "don't delete me"

def test_init_conflict_file(tmp_path):
    """Verify deep init fails gracefully if path is a file."""
    cwd = tmp_path
    conflict_file = cwd / "conflict.txt"
    conflict_file.write_text("already here")
    
    res = subprocess.run(["deep", "init", "conflict.txt"], cwd=str(cwd), capture_output=True, text=True)
    
    assert res.returncode != 0
    assert "error" in res.stderr.lower()
    assert "not a directory" in res.stderr.lower()

def test_init_conflict_dotdeep_file(tmp_path):
    """Verify deep init fails if .deep is a file."""
    cwd = tmp_path / "repo"
    cwd.mkdir()
    from deep.core.constants import DEEP_DIR
    (cwd / DEEP_DIR).write_text("I am a file, not a dir")
    
    res = subprocess.run(["deep", "init"], cwd=str(cwd), capture_output=True, text=True)
    
    assert res.returncode != 0
    assert "error" in res.stderr.lower()
    assert "not a directory" in res.stderr.lower()

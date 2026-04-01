import subprocess
import pytest
from pathlib import Path
import shutil

def run_deep(repo_dir, args):
    """Run a deep command and return the result."""
    result = subprocess.run(
        ["deep"] + args,
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    return result

@pytest.fixture
def source_repo(tmp_path):
    # Create a source repository with multiple branches and tags
    repo_dir = tmp_path / "source"
    repo_dir.mkdir()
    run_deep(repo_dir, ["init"])
    
    (repo_dir / "f1.txt").write_text("v1")
    run_deep(repo_dir, ["add", "f1.txt"])
    run_deep(repo_dir, ["commit", "-m", "initial commit"])
    run_deep(repo_dir, ["tag", "v1.0"])
    
    run_deep(repo_dir, ["branch", "feature"])
    run_deep(repo_dir, ["checkout", "feature"])
    (repo_dir / "f2.txt").write_text("feature content")
    run_deep(repo_dir, ["add", "f2.txt"])
    run_deep(repo_dir, ["commit", "-m", "feature commit"])
    
    run_deep(repo_dir, ["checkout", "main"])
    return repo_dir

def test_mirror_basic(source_repo, tmp_path):
    """Test deep mirror url path creates a full mirror."""
    mirror_path = tmp_path / "mirror"
    
    res = run_deep(tmp_path, ["mirror", str(source_repo), str(mirror_path)])
    assert res.returncode == 0
    assert "Mirror complete" in res.stdout
    assert (mirror_path / ".deep").exists()
    
    # Verify branches
    res = run_deep(mirror_path, ["branch"])
    assert "main" in res.stdout
    assert "feature" in res.stdout
    
    # Verify tags
    res = run_deep(mirror_path, ["tag"])
    assert "v1.0" in res.stdout
    
    # Verify config
    res = run_deep(mirror_path, ["config", "remote.origin.url"])
    assert str(source_repo) in res.stdout.strip()
    
    res = run_deep(mirror_path, ["config", "core.mirror"])
    assert "true" in res.stdout.strip()

def test_mirror_existing_not_empty(source_repo, tmp_path):
    """Test deep mirror fails if destination is not empty."""
    mirror_path = tmp_path / "mirror"
    mirror_path.mkdir()
    (mirror_path / "file.txt").write_text("dummy")
    
    res = run_deep(tmp_path, ["mirror", str(source_repo), str(mirror_path)])
    assert res.returncode != 0
    assert "already exists and is not empty" in res.stderr

def test_mirror_invalid_url(tmp_path):
    """Test deep mirror fails with invalid URL."""
    mirror_path = tmp_path / "mirror"
    res = run_deep(tmp_path, ["mirror", "non-existent-url", str(mirror_path)])
    assert res.returncode != 0
    # The error message should indicate that metadata parsing or mirror failed
    assert "mirror failed" in res.stderr or "Cannot parse remote URL" in res.stderr

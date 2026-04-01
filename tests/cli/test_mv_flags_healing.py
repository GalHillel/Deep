import subprocess
import os
import shutil
import pytest
from pathlib import Path

@pytest.fixture
def clean_repo(tmp_path):
    """Set up a clean Deep repository."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_path), check=True)
    return repo_path

def test_mv_basic_file(clean_repo):
    """Verify renaming a single tracked file."""
    f1 = clean_repo / "old.txt"
    f1.write_text("content")
    subprocess.run(["deep", "add", "old.txt"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "init"], cwd=str(clean_repo), check=True)
    
    # Run mv
    subprocess.run(["deep", "mv", "old.txt", "new.txt"], cwd=str(clean_repo), check=True)
    
    # Check disk
    assert not f1.exists()
    assert (clean_repo / "new.txt").exists()
    assert (clean_repo / "new.txt").read_text() == "content"
    
    # Check index
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "old.txt" not in index.entries
    assert "new.txt" in index.entries

def test_mv_file_to_dir(clean_repo):
    """Verify moving a file into an existing directory."""
    f1 = clean_repo / "file.txt"
    f1.write_text("data")
    d1 = clean_repo / "docs"
    d1.mkdir()
    subprocess.run(["deep", "add", "file.txt"], cwd=str(clean_repo), check=True)
    
    # Run mv
    subprocess.run(["deep", "mv", "file.txt", "docs/"], cwd=str(clean_repo), check=True)
    
    # Check disk
    assert not f1.exists()
    assert (d1 / "file.txt").exists()
    
    # Check index
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "file.txt" not in index.entries
    assert "docs/file.txt" in index.entries

def test_mv_directory(clean_repo):
    """Verify renaming a directory containing multiple tracked files."""
    d1 = clean_repo / "src"
    d1.mkdir()
    (d1 / "main.py").write_text("print(1)")
    (d1 / "util.py").write_text("def f(): pass")
    subprocess.run(["deep", "add", "src/"], cwd=str(clean_repo), check=True)
    subprocess.run(["deep", "commit", "-m", "init"], cwd=str(clean_repo), check=True)
    
    # Run mv
    subprocess.run(["deep", "mv", "src", "lib"], cwd=str(clean_repo), check=True)
    
    # Check disk
    assert not d1.exists()
    assert (clean_repo / "lib").is_dir()
    assert (clean_repo / "lib" / "main.py").exists()
    assert (clean_repo / "lib" / "util.py").exists()
    
    # Check index
    from deep.storage.index import read_index
    from deep.core.constants import DEEP_DIR
    index = read_index(clean_repo / DEEP_DIR)
    assert "src/main.py" not in index.entries
    assert "lib/main.py" in index.entries
    assert "lib/util.py" in index.entries

def test_mv_untracked_error(clean_repo):
    """Verify that moving an untracked file fails."""
    f1 = clean_repo / "untracked.txt"
    f1.write_text("secret")
    
    # Run mv (should fail)
    res = subprocess.run(["deep", "mv", "untracked.txt", "new.txt"], cwd=str(clean_repo), capture_output=True, text=True)
    assert res.returncode != 0
    assert "not tracked" in res.stderr
    
    # Disk should remain untouched (in standard Git, it might still move on disk if not careful, 
    # but we implemented it to error out before the physical move).
    assert f1.exists()
    assert not (clean_repo / "new.txt").exists()

def test_mv_dest_exists_error(clean_repo):
    """Verify that moving onto an existing destination fails."""
    f1 = clean_repo / "a.txt"
    f1.write_text("a")
    f2 = clean_repo / "b.txt"
    f2.write_text("b")
    subprocess.run(["deep", "add", "a.txt", "b.txt"], cwd=str(clean_repo), check=True)
    
    # Run mv (should fail because b.txt exists)
    res = subprocess.run(["deep", "mv", "a.txt", "b.txt"], cwd=str(clean_repo), capture_output=True, text=True)
    assert res.returncode != 0
    assert "destination exists" in res.stderr

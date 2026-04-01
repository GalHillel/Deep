import subprocess
import os
import shutil
import time
import pytest
from pathlib import Path
from datetime import datetime, timezone as dt_timezone

def get_config_content(repo_dir: Path, bare: bool = False) -> str:
    from deep.core.constants import DEEP_DIR
    dg = repo_dir if bare else repo_dir / DEEP_DIR
    config_path = dg / "config"
    if not config_path.exists():
        return ""
    return config_path.read_text(encoding="utf-8").strip()

def normalize_path(p: str | Path) -> str:
    """Normalize path for comparison: forward slashes, lowercase drive, and no trailing slash."""
    p_str = str(p).replace("\\", "/").rstrip("/")
    if len(p_str) > 1 and p_str[1] == ":":
        return p_str[0].lower() + p_str[1:].lower()
    return p_str.lower()

def test_clone_basic(tmp_path):
    """Verify basic clone from one local path to another."""
    repo_src = tmp_path / "src"
    repo_src.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_src), check=True)
    (repo_src / "f1.txt").write_text("hello")
    subprocess.run(["deep", "add", "f1.txt"], cwd=str(repo_src), check=True)
    subprocess.run(["deep", "commit", "-m", "initial"], cwd=str(repo_src), check=True)
    
    repo_dst = tmp_path / "dst"
    subprocess.run(["deep", "clone", str(repo_src), str(repo_dst)], check=True)
    
    from deep.core.constants import DEEP_DIR
    assert (repo_dst / DEEP_DIR).exists()
    assert (repo_dst / "f1.txt").read_text() == "hello"
    
    config = get_config_content(repo_dst)
    # Use normalized paths for comparison. We only normalize the needle 
    # and the config content manually to avoid Path.resolve() side effects.
    needle = normalize_path(repo_src)
    haystack = config.replace("\\", "/").lower()
    assert needle in haystack

def test_clone_mirror(tmp_path):
    """Verify --mirror flag creates a bare repository."""
    repo_src = tmp_path / "src"
    repo_src.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_src), check=True)
    # Add a commit so it's not empty (empty repos might skip some config steps)
    (repo_src / "f1.txt").write_text("hello")
    subprocess.run(["deep", "add", "."], cwd=str(repo_src), check=True)
    subprocess.run(["deep", "commit", "-m", "initial"], cwd=str(repo_src), check=True)
    
    repo_dst = tmp_path / "mirror"
    subprocess.run(["deep", "clone", str(repo_src), str(repo_dst), "--mirror"], check=True)
    
    # In mirror repo, root IS the deep dir
    assert (repo_dst / "objects").is_dir()
    assert not (repo_dst / ".deep").exists()
    
    config = get_config_content(repo_dst, bare=True)
    assert "bare = true" in config
    assert "mirror = true" in config

def test_clone_depth(tmp_path):
    """Verify --depth 1 truncates history."""
    repo_src = tmp_path / "src"
    repo_src.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_src), check=True)
    
    # Three commits
    for i in range(3):
        (repo_src / f"f{i}.txt").write_text(f"content {i}")
        subprocess.run(["deep", "add", "."], cwd=str(repo_src), check=True)
        subprocess.run(["deep", "commit", "-m", f"msg {i}"], cwd=str(repo_src), check=True)
        
    repo_dst = tmp_path / "shallow"
    subprocess.run(["deep", "clone", str(repo_src), str(repo_dst), "--depth", "1"], check=True)
    
    # Verify only 1 commit in log
    res = subprocess.run(["deep", "log", "--oneline"], cwd=str(repo_dst), capture_output=True, text=True, check=True)
    lines = res.stdout.strip().splitlines()
    assert len(lines) == 1
    assert "msg 2" in lines[0]

def test_clone_shallow_since(tmp_path):
    """Verify --shallow-since truncates history based on date."""
    repo_src = tmp_path / "src"
    repo_src.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_src), check=True)
    
    # Commit 1
    (repo_src / "f1.txt").write_text("1")
    subprocess.run(["deep", "add", "."], cwd=str(repo_src), check=True)
    subprocess.run(["deep", "commit", "-m", "first"], cwd=str(repo_src), check=True)
    
    # Wait to ensure timestamp difference
    time.sleep(1.5)
    cutoff = datetime.now(dt_timezone.utc).isoformat()
    time.sleep(1.5)
    
    # Commit 2
    (repo_src / "f2.txt").write_text("2")
    subprocess.run(["deep", "add", "."], cwd=str(repo_src), check=True)
    subprocess.run(["deep", "commit", "-m", "second"], cwd=str(repo_src), check=True)
    
    repo_dst = tmp_path / "since"
    subprocess.run(["deep", "clone", str(repo_src), str(repo_dst), "--shallow-since", cutoff], check=True)
    
    res = subprocess.run(["deep", "log", "--oneline"], cwd=str(repo_dst), capture_output=True, text=True, check=True)
    lines = res.stdout.strip().splitlines()
    # It should only have 'second' commit
    assert len(lines) == 1
    assert "second" in lines[0]

def test_clone_filter(tmp_path):
    """Verify --filter blob:none skips blob downloads."""
    repo_src = tmp_path / "src"
    repo_src.mkdir()
    subprocess.run(["deep", "init"], cwd=str(repo_src), check=True)
    (repo_src / "big.txt").write_text("lots of data")
    subprocess.run(["deep", "add", "."], cwd=str(repo_src), check=True)
    subprocess.run(["deep", "commit", "-m", "add blob"], cwd=str(repo_src), check=True)
    
    repo_dst = tmp_path / "partial"
    subprocess.run(["deep", "clone", str(repo_src), str(repo_dst), "--filter", "blob:none"], check=True)
    
    from deep.storage.objects import hash_bytes
    # Deep blob hashing: b"blob <len>\0<data>"
    content = b"lots of data"
    header = f"blob {len(content)}\0".encode("ascii")
    blob_sha = hash_bytes(header + content)
    
    from deep.core.constants import DEEP_DIR
    blob_path = repo_dst / DEEP_DIR / "objects" / blob_sha[:2] / blob_sha[2:]
    assert not blob_path.exists()

"""Tests for crash recovery and resilience (Phase 48)."""
from pathlib import Path
import subprocess, sys, os, zlib
import pytest

from deep.core.repository import DEEP_DIR
from deep.utils.utils import hash_bytes


@pytest.fixture
def resilience_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src") + os.pathsep + str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_object_quarantine(resilience_repo):
    repo, env = resilience_repo
    # Create a valid object
    (repo / "f.txt").write_text("stable content")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "f.txt"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "c1"], cwd=repo, env=env, check=True)
    
    # Identify the blob SHA
    from deep.core.refs import resolve_head
    from deep.storage.objects import read_object, Commit
    dg_dir = repo / DEEP_DIR
    sha = resolve_head(dg_dir)
    commit = read_object(dg_dir / "objects", sha)
    from deep.web.dashboard import _tree_entries_flat
    entries = _tree_entries_flat(dg_dir / "objects", commit.tree_sha)
    blob_sha = list(entries.values())[0]
    
    # Corrupt the blob file on disk
    blob_path = dg_dir / "objects" / blob_sha[:2] / blob_sha[2:]
    # Overwrite with garbage (but still needs to be zlib decompressible to trigger SHA mismatch, 
    # or fail decompression which is also an error)
    content = zlib.compress(b"blob 5\x00wrong")
    blob_path.write_bytes(content)
    
    # Run doctor to trigger quarantine
    result = subprocess.run(
        [sys.executable, "-m", "deep.main", "doctor", "--fix"],
        cwd=repo, env=env, capture_output=True, text=True
    )
    assert "corrupt" in result.stdout.lower()
    
    # Check quarantine dir
    quarantine_base = dg_dir / "quarantine"
    assert quarantine_base.exists()
    
    # Doctor uses timestamped subdirs: dg_dir / "quarantine" / str(int(time.time()))
    # And appends _corrupt suffix for corrupt objects
    found = False
    for ts_dir in quarantine_base.iterdir():
        if (ts_dir / f"{blob_sha}_corrupt").exists():
            found = True
            break
    assert found, f"Corrupt blob {blob_sha} not found in quarantine"

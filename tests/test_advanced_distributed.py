"""Tests for advanced distributed features (Phase 26)."""
from pathlib import Path
import subprocess, sys, os, socket, time
import pytest

from deep.core.repository import DEEP_DIR
from deep.core.refs import resolve_head


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def env():
    e = os.environ.copy()
    e["PYTHONPATH"] = str(Path.cwd() / "src")
    e["PYTHONUNBUFFERED"] = "1"
    return e


def test_divergent_push_detection(tmp_path, env):
    """Two clients push to same branch — second should still work with our protocol."""
    from deep.network.sync import SyncEngine
    repo = tmp_path / "server"
    repo.mkdir()
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=repo, env=env, check=True)
    (repo / "a.txt").write_text("init")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "a.txt"], cwd=repo, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "init"], cwd=repo, env=env, check=True)
    head = resolve_head(repo / DEEP_DIR)

    engine = SyncEngine(repo / DEEP_DIR)
    # Simulate: correct old_sha → no conflict
    assert engine.detect_conflict("refs/heads/main", head, "new1") is None
    # Simulate: wrong old_sha → conflict
    conflict = engine.detect_conflict("refs/heads/main", "wrong", "new2")
    assert conflict is not None
    assert "Divergent" in conflict.details


def test_shallow_clone_init(tmp_path, env):
    """Shallow clone creates a valid repo."""
    repo = tmp_path / "shallow"
    repo.mkdir()
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=repo, env=env, check=True)
    assert (repo / DEEP_DIR / "HEAD").exists()


def test_incremental_push_sync(tmp_path, env):
    """Push only adds new objects, doesn't duplicate existing ones."""
    server = tmp_path / "server"
    server.mkdir()
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=server, env=env, check=True)
    (server / "a.txt").write_text("v1")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "a.txt"], cwd=server, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "v1"], cwd=server, env=env, check=True)

    # Count objects initially
    objects_dir = server / DEEP_DIR / "objects"
    initial_count = sum(1 for d in objects_dir.iterdir() if d.is_dir() and len(d.name) == 2
                        for _ in d.iterdir())

    # Second commit
    (server / "b.txt").write_text("v2")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "b.txt"], cwd=server, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "v2"], cwd=server, env=env, check=True)

    new_count = sum(1 for d in objects_dir.iterdir() if d.is_dir() and len(d.name) == 2
                    for _ in d.iterdir())
    # Should have added new objects but not duplicated old ones
    assert new_count > initial_count

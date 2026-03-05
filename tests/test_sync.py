"""Tests for multi-user sync engine (Phase 23)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep.network.sync import SyncEngine, SyncEvent
from deep.core.repository import DEEP_GIT_DIR


@pytest.fixture
def sync_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.txt").write_text("hi")
    subprocess.run([sys.executable, "-m", "deep.main", "add", "a.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, "-m", "deep.main", "commit", "-m", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_sync_event_serialization():
    e = SyncEvent("ref_update", ref="refs/heads/main", old_sha="aaa", new_sha="bbb")
    j = e.to_json()
    e2 = SyncEvent.from_json(j)
    assert e2.event_type == "ref_update"
    assert e2.ref == "refs/heads/main"


def test_sync_broadcast(sync_repo):
    engine = SyncEngine(sync_repo / DEEP_GIT_DIR)
    received = []
    engine.register_listener(lambda e: received.append(e))
    engine.record_ref_update("refs/heads/main", "aaa", "bbb", "alice")
    assert len(received) == 1
    assert received[0].event_type == "ref_update"


def test_sync_conflict_detection(sync_repo):
    engine = SyncEngine(sync_repo / DEEP_GIT_DIR)
    from deep.core.refs import resolve_head
    head = resolve_head(sync_repo / DEEP_GIT_DIR)
    # No conflict if expected matches
    conflict = engine.detect_conflict("refs/heads/main", head, "new_sha")
    assert conflict is None
    # Conflict if expected doesn't match
    conflict = engine.detect_conflict("refs/heads/main", "wrong_old", "new_sha")
    assert conflict is not None
    assert conflict.event_type == "conflict"


def test_sync_events_since(sync_repo):
    import time
    engine = SyncEngine(sync_repo / DEEP_GIT_DIR)
    t0 = time.time() - 1
    engine.record_ref_update("refs/heads/main", "a", "b")
    events = engine.get_events_since(t0)
    assert len(events) == 1

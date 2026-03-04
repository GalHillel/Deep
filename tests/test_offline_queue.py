"""Tests for offline operation queue (Phase 33)."""
from pathlib import Path
import subprocess, sys, os
import pytest

from deep_git.network.offline_queue import OfflineQueue
from deep_git.core.repository import DEEP_GIT_DIR


@pytest.fixture
def queue_repo(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], cwd=tmp_path, env=env, check=True)
    return tmp_path


def test_enqueue_and_retrieve(queue_repo):
    q = OfflineQueue(queue_repo / DEEP_GIT_DIR)
    q.enqueue("push", "127.0.0.1:8888", "refs/heads/main", "abc123")
    pending = q.get_pending()
    assert len(pending) == 1
    assert pending[0].operation == "push"


def test_mark_completed(queue_repo):
    q = OfflineQueue(queue_repo / DEEP_GIT_DIR)
    q.enqueue("fetch", "127.0.0.1:8888", "refs/heads/main", "abc123")
    q.mark_completed(0)
    assert len(q.get_pending()) == 0


def test_mark_failed(queue_repo):
    q = OfflineQueue(queue_repo / DEEP_GIT_DIR)
    q.enqueue("push", "127.0.0.1:8888", "refs/heads/main", "abc123")
    q.mark_failed(0, "connection refused")
    pending = q.get_pending()
    assert len(pending) == 0


def test_reconcile_with_callback(queue_repo):
    q = OfflineQueue(queue_repo / DEEP_GIT_DIR)
    q.enqueue("push", "127.0.0.1:8888", "refs/heads/main", "abc123")
    executed = []
    def mock_push(url, ref, sha):
        executed.append((url, ref, sha))
    results = q.reconcile(push_fn=mock_push)
    assert results["completed"] == 1
    assert len(executed) == 1


def test_persistence(queue_repo):
    dg_dir = queue_repo / DEEP_GIT_DIR
    q1 = OfflineQueue(dg_dir)
    q1.enqueue("push", "host:8888", "refs/heads/main", "sha1")
    q2 = OfflineQueue(dg_dir)
    assert len(q2.get_pending()) == 1


def test_clear_completed(queue_repo):
    q = OfflineQueue(queue_repo / DEEP_GIT_DIR)
    q.enqueue("push", "host:8888", "main", "sha1")
    q.enqueue("fetch", "host:8888", "main", "sha2")
    q.mark_completed(0)
    q.clear_completed()
    assert len(q._ops) == 1

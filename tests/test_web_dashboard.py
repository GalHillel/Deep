"""
tests.test_web_dashboard
~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the DeepGit Web Dashboard REST API.
"""

from __future__ import annotations

import json
import subprocess
import sys
import os
import time
import socket
from pathlib import Path
from urllib.request import urlopen

import pytest

from deep.core.repository import DEEP_DIR


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def dashboard_server(tmp_path):
    """Start a dashboard server in a subprocess, yield (port, repo_root)."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    env["PYTHONUNBUFFERED"] = "1"

    # Init repo and make some commits
    subprocess.run(
        [sys.executable, "-m", "deep.main", "init"],
        cwd=repo_root, env=env, check=True
    )
    for i in range(3):
        (repo_root / f"file_{i}.txt").write_text(f"content {i}")
        subprocess.run(
            [sys.executable, "-m", "deep.main", "add", f"file_{i}.txt"],
            cwd=repo_root, env=env, check=True
        )
        subprocess.run(
            [sys.executable, "-m", "deep.main", "commit", "-m", f"commit {i}"],
            cwd=repo_root, env=env, check=True
        )

    port = get_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "deep.main", "web", "--port", str(port)],
        cwd=repo_root, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(1.5)

    yield port, repo_root

    proc.terminate()
    proc.wait()


def test_dashboard_index(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/")
    assert resp.status == 200
    body = resp.read().decode()
    assert "DeepGit" in body
    assert "<canvas" in body or "dag" in body.lower()


def test_api_log(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/log")
    data = json.loads(resp.read())
    assert isinstance(data, list)
    assert len(data) >= 3
    assert "sha" in data[0]
    assert "message" in data[0]
    assert "parents" in data[0]


def test_api_refs(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/refs")
    data = json.loads(resp.read())
    assert "head" in data
    assert "branches" in data
    assert "main" in data["branches"]
    assert data["current_branch"] == "main"


def test_api_object(dashboard_server):
    port, _ = dashboard_server
    # Get HEAD sha from refs
    refs = json.loads(urlopen(f"http://127.0.0.1:{port}/api/refs").read())
    head_sha = refs["head"]
    resp = urlopen(f"http://127.0.0.1:{port}/api/object/{head_sha}")
    data = json.loads(resp.read())
    assert data["type"] == "commit"
    assert data["sha"] == head_sha


def test_api_diff(dashboard_server):
    port, _ = dashboard_server
    refs = json.loads(urlopen(f"http://127.0.0.1:{port}/api/refs").read())
    head_sha = refs["head"]
    resp = urlopen(f"http://127.0.0.1:{port}/api/diff/{head_sha}")
    data = json.loads(resp.read())
    assert isinstance(data, list)


def test_api_metrics(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/metrics")
    data = json.loads(resp.read())
    assert isinstance(data, dict)


def test_api_multi_repo(dashboard_server):
    port, repo_root = dashboard_server
    # Create a sibling repo
    sibling = repo_root.parent / "sibling"
    sibling.mkdir()
    subprocess.run([sys.executable, "-m", "deep.main", "init"], cwd=sibling, check=True)
    
    resp = urlopen(f"http://127.0.0.1:{port}/api/multi-repo")
    data = json.loads(resp.read())
    assert isinstance(data, list)
    names = [r["name"] for r in data]
    assert "repo" in names
    assert "sibling" in names


def test_api_heatmap(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/heatmap")
    data = json.loads(resp.read())
    assert isinstance(data, list)
    assert len(data) > 0
    assert "file" in data[0]
    assert "complexity" in data[0]

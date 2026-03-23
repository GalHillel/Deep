"""
tests.test_web_dashboard
~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the Deep Web Dashboard REST API.
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
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["PYTHONUNBUFFERED"] = "1"

    # Init repo and make some commits
    subprocess.run(
        [sys.executable, "-m", "deep.cli.main", "init"],
        cwd=repo_root, env=env, check=True
    )
    for i in range(3):
        (repo_root / f"file_{i}.txt").write_text(f"content {i}")
        subprocess.run(
            [sys.executable, "-m", "deep.cli.main", "add", f"file_{i}.txt"],
            cwd=repo_root, env=env, check=True
        )
        subprocess.run(
            [sys.executable, "-m", "deep.cli.main", "commit", "-m", f"commit {i}"],
            cwd=repo_root, env=env, check=True
        )

    port = get_free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "deep.cli.main", "web", "--port", str(port)],
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
    body = resp.read().decode().lower()
    assert "deepvcs studio" in body
    assert "app.js" in body


def test_api_log_graph(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/graph")
    res = json.loads(resp.read())
    assert res["success"] is True
    data = res["data"]
    assert isinstance(data, dict)
    commits = data["commits"]
    assert isinstance(commits, list)
    assert len(commits) >= 3
    assert "sha" in commits[0]
    assert "message" in commits[0]


def test_api_status(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/status")
    res = json.loads(resp.read())
    assert res["success"] is True
    data = res["data"]
    assert "branch" in data
    assert data["branch"] == "main"
    assert "modified" in data


def test_api_commit_details(dashboard_server):
    port, _ = dashboard_server
    # Get HEAD sha from graph
    graph_res = json.loads(urlopen(f"http://127.0.0.1:{port}/api/graph").read())
    head_sha = graph_res["data"]["refs"]["HEAD"]
    resp = urlopen(f"http://127.0.0.1:{port}/api/commit/details?sha={head_sha}")
    res = json.loads(resp.read())
    assert res["success"] is True
    data = res["data"]
    assert data["sha"] == head_sha
    assert "author" in data
    assert "message" in data


def test_api_diff(dashboard_server):
    port, _ = dashboard_server
    graph_res = json.loads(urlopen(f"http://127.0.0.1:{port}/api/graph").read())
    head_sha = graph_res["data"]["refs"]["HEAD"]
    resp = urlopen(f"http://127.0.0.1:{port}/api/diff?sha={head_sha}")
    res = json.loads(resp.read())
    assert res["success"] is True
    # The new get_diff returns {"diff": "..."}
    assert "diff" in res["data"]


def test_api_status_metrics(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/status")
    res = json.loads(resp.read())
    assert res["success"] is True
    data = res["data"]
    assert isinstance(data, dict)
    assert "branch" in data


def test_api_branches_list(dashboard_server):
    port, repo_root = dashboard_server
    # Create a new branch
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    subprocess.run([sys.executable, "-m", "deep.cli.main", "branch", "feat-test"], cwd=repo_root, env=env, check=True)
    
    resp = urlopen(f"http://127.0.0.1:{port}/api/branches")
    res = json.loads(resp.read())
    assert res["success"] is True
    data = res["data"]
    assert isinstance(data, list)
    assert "main" in data
    assert "feat-test" in data


def test_api_tree(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/tree")
    res = json.loads(resp.read())
    assert res["success"] is True
    data = res["data"]
    assert isinstance(data, dict)
    assert "tree" in data
    # Check that some files exist in the root (depth 0)
    root_files = data["tree"]
    assert "file_0.txt" in root_files
    assert root_files["file_0.txt"]["_type"] == "file"

def test_api_file_content(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/file?path=file_0.txt")
    res = json.loads(resp.read())
    assert res["success"] is True
    data = res["data"]
    assert "content" in data
    assert "content 0" in data["content"]

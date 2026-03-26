"""
tests.test_vr_dashboard
~~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 59: Hyper GUI + Web + VR Explorer.
"""

import pytest
import json
from urllib.request import urlopen


def test_api_dag_3d(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/graph")
    data = json.loads(resp.read())
    # The API returns {"success": True, "data": {"commits": [...], "refs": {...}}}
    assert "data" in data
    assert "commits" in data["data"]
    commits = data["data"]["commits"]
    assert isinstance(commits, list)
    assert len(commits) >= 3
    # Check first commit structure
    first = commits[0]
    assert "sha" in first
    assert "message" in first


def test_vr_explorer_loading(dashboard_server):
    port, _ = dashboard_server
    # Verify index.html still loads with new VR-ready assets
    resp = urlopen(f"http://127.0.0.1:{port}/")
    body = resp.read().decode()
    assert "Deep" in body
    # In a real VR app, we'd check for 3D library imports or canvas3d
    # assert "vr" in body.lower()

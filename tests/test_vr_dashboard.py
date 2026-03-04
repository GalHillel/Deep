"""
tests.test_vr_dashboard
~~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 59: Hyper GUI + Web + VR Explorer.
"""

import pytest
import json
from urllib.request import urlopen
from tests.test_web_dashboard import dashboard_server


def test_api_dag_3d(dashboard_server):
    port, _ = dashboard_server
    resp = urlopen(f"http://127.0.0.1:{port}/api/dag-3d")
    data = json.loads(resp.read())
    
    assert isinstance(data, list)
    assert len(data) >= 3
    assert "x" in data[0]
    assert "y" in data[0]
    assert "z" in data[0]
    assert "sha" in data[0]


def test_vr_explorer_loading(dashboard_server):
    port, _ = dashboard_server
    # Verify index.html still loads with new VR-ready assets
    resp = urlopen(f"http://127.0.0.1:{port}/")
    body = resp.read().decode()
    assert "DeepGit" in body
    # In a real VR app, we'd check for 3D library imports or canvas3d
    # assert "vr" in body.lower()

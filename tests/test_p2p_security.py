"""
tests.test_p2p_security
~~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 56: Multi-Node Security & Anomaly Detection.
"""

import pytest
import time
from pathlib import Path
from deep_git.core.security import SecurityMonitor


def test_commit_anomaly_detection(tmp_path):
    monitor = SecurityMonitor(tmp_path)
    
    # Normal volume
    assert not monitor.detect_commit_anomaly(5, 10)
    
    # Extreme volume
    assert monitor.detect_commit_anomaly(500, 5)
    alerts = monitor.get_alerts()
    assert len(alerts) == 1
    assert alerts[0].severity == "high"


def test_p2p_request_analysis(tmp_path):
    monitor = SecurityMonitor(tmp_path)
    # Basic pass-through for now
    assert not monitor.analyze_p2p_request("peer_1", "get_object")


def test_unauthorized_access_simulation(tmp_path):
    monitor = SecurityMonitor(tmp_path)
    # Placeholder for future RBAC integration
    assert monitor.check_unauthorized_access("admin", "refs/heads/main")

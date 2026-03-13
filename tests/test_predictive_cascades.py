"""
tests.test_predictive_cascades
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 58: Predictive CI/CD Cascades.
"""

import pytest
import json
import time
from pathlib import Path
from deep.core.repository import init_repo,DEEP_DIR
from deep.core.pipeline import PipelineRunner


@pytest.fixture
def cascade_env(tmp_path):
    # Upstream repo
    upstream = tmp_path / "upstream"
    upstream.mkdir(); init_repo(upstream)
    
    # Downstream repo
    downstream = tmp_path / "downstream"
    downstream.mkdir(); init_repo(downstream)
    
    # Configure downstream to depend on upstream
    config = {
        "dependencies": [{"repo": "upstream"}],
        "jobs": [{"name": "integration-test", "command": "echo 'running integration tests'"}]
    }
    (downstream / DEEP_DIR / "pipeline.json").write_text(json.dumps(config))
    
    return upstream, downstream


def test_cross_repo_cascade_trigger(cascade_env):
    upstream, downstream = cascade_env
    
    runner = PipelineRunner(upstream / DEEP_DIR)
    
    # 1. Trigger cascade from upstream
    cascaded = runner.cascade_to_dependents("abc1234")
    
    assert "downstream" in cascaded
    
    # 2. Verify downstream has a new run
    time.sleep(1.0) # wait for thread start
    ds_runner = PipelineRunner(downstream / DEEP_DIR)
    runs = ds_runner.list_runs()
    
    assert len(runs) > 0
    assert "cascade_from_upstream" in runs[0].commit_sha
    assert "abc1234" in runs[0].commit_sha

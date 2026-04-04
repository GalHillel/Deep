"""
tests.test_benchmark_compare
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 11 features:
1. Deep comparison
2. JSON reporting
"""

from __future__ import annotations

import os
import json
from pathlib import Path
import pytest
from deep.cli.main import main

def test_benchmark_report_and_compare(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    os.chdir(repo)
    main(["init"])
    
    # Run benchmark with report and compare (if deep is available)
    main(["benchmark", "--report", "--compare-deep"])
        
    report_file = repo / "benchmark_report.json"
    assert report_file.exists()
    
    with open(report_file, "r") as f:
        data = json.load(f)
        
    assert "index_add_10k_time" in data
    assert "commit_10k_tree_time" in data
    
    # If deep was found and run successfully
    if "deep" in data:
        assert "commit_avg_time" in data["deep"]
    elif "deep_error" in data:
        print(f"Deep comparison skipped: {data['deep_error']}")

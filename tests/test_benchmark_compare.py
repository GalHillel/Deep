"""
tests.test_benchmark_compare
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for Phase 11 features:
1. Git comparison
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
    
    # Run benchmark with report and compare (if git is available)
    main(["benchmark", "--report", "--compare-git"])
        
    report_file = repo / "benchmark_report.json"
    assert report_file.exists()
    
    with open(report_file, "r") as f:
        data = json.load(f)
        
    assert "deep_blob_total_time" in data
    assert "deep_commit_avg_time" in data
    
    # If git was found and run successfully
    if "git" in data:
        assert "commit_avg_time" in data["git"]
    elif "git_error" in data:
        print(f"Git comparison skipped: {data['git_error']}")

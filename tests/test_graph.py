"""
tests.test_graph
~~~~~~~~~~~~~~~~~
Verification for the high-fidelity graph visualization.
"""

import os
import shutil
import subprocess
from pathlib import Path
import pytest
from deep.core.repository import init_repo, DEEP_GIT_DIR

import sys

def run_deep(cwd: Path, *args: str) -> str:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent)
    try:
        res = subprocess.run(
            [sys.executable, "-m", "deep.main", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=30
        )
    except subprocess.TimeoutExpired:
        print(f"ERROR: timed out running deep {' '.join(args)}")
        return ""
    if res.returncode != 0:
        print(f"ERROR ({res.returncode}) running deep {' '.join(args)}")
        print("STDOUT:", res.stdout)
        print("STDERR:", res.stderr)
    return res.stdout

def test_graph_linear(tmp_path: Path):
    repo = tmp_path / "repo_linear"
    repo.mkdir()
    run_deep(repo, "init")
    
    (repo / "f1.txt").write_text("v1")
    run_deep(repo, "add", "f1.txt")
    run_deep(repo, "commit", "-m", "initial")
    
    (repo / "f1.txt").write_text("v2")
    run_deep(repo, "add", "f1.txt")
    run_deep(repo, "commit", "-m", "second")
    
    out = run_deep(repo, "graph")
    print(out)
    assert "●" in out
    assert "initial" in out
    assert "second" in out
    assert "HEAD" in out

def test_graph_merge(tmp_path: Path):
    repo = tmp_path / "repo_merge"
    repo.mkdir()
    run_deep(repo, "init")
    
    (repo / "base.txt").write_text("base")
    run_deep(repo, "add", "base.txt")
    run_deep(repo, "commit", "-m", "root")
    
    # Branch A
    run_deep(repo, "branch", "feature-a")
    run_deep(repo, "checkout", "feature-a")
    (repo / "a.txt").write_text("a")
    run_deep(repo, "add", "a.txt")
    run_deep(repo, "commit", "-m", "commit a")
    
    # Branch Main
    run_deep(repo, "checkout", "main")
    (repo / "main.txt").write_text("m")
    run_deep(repo, "add", "main.txt")
    run_deep(repo, "commit", "-m", "commit main")
    
    # Merge
    run_deep(repo, "merge", "feature-a")
    
    out = run_deep(repo, "graph", "--all")
    print(out)
    assert "commit a" in out
    assert "commit main" in out
    assert "root" in out
    assert "Merge branch 'feature-a'" in out
    assert "main" in out
    assert "feature-a" in out

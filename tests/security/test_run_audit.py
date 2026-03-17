import os
from pathlib import Path
from collections import defaultdict, deque
import sys
import pytest

from deep.cli.main import main
from deep.core.repository import DEEP_DIR

def run_audit(root_dir):
    print(f"--- PHASE 1: REPOSITORY STRUCTURE AUDIT ({root_dir}) ---")
    dg_dir = Path(root_dir) / DEEP_DIR
    if not dg_dir.exists():
        print(f"Skipping structure audit: {DEEP_DIR} not found in {root_dir}")
        return True # Skip
    
    # Check essential dirs
    for d in ["objects", "refs/heads", "refs/tags", "metadata"]:
        if not (dg_dir / d).is_dir():
             pytest.fail(f"ERROR: Missing directory: {d}")
            
    print("Structure Audit: PASSED")
    return True

def test_repository_audit():
    # Target the project root
    repo_root = Path(__file__).parent.parent
    run_audit(repo_root)

if __name__ == "__main__":
    test_repository_audit()

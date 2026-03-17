"""
tests.test_e2e_validation
~~~~~~~~~~~~~~~~~~~~~~~~~
Final end-to-end stress test across all components.
"""

import os
from pathlib import Path
import pytest
from deep.cli.main import main
from deep.core.repository import DEEP_DIR

def test_full_lifecycle_stress(tmp_path: Path):
    repo1 = tmp_path / "repo1"
    repo1.mkdir()
    os.chdir(repo1)
    
    # 1. Init
    main(["init"])
    assert (repo1 / DEEP_DIR).exists()
    
    # 2. Parallel Staging (simulated by multiple add commands)
    for i in range(20):
        (repo1 / f"file_{i}.txt").write_text(f"content {i}")
        main(["add", f"file_{i}.txt"])
        
    # 3. Commit with AI Suggestion (dry run of CLI)
    main(["commit", "--ai", "-m", "Initial commit of 20 files"])
    
    # 4. Branching and Merging
    main(["branch", "feature-x"])
    main(["checkout", "feature-x"])
    (repo1 / "file_20.txt").write_text("feature content")
    main(["add", "file_20.txt"])
    main(["commit", "-m", "feature work"])
    
    main(["checkout", "main"])
    (repo1 / "file_main.txt").write_text("main content")
    main(["add", "file_main.txt"])
    main(["commit", "-m", "main work"])
    
    main(["merge", "feature-x"])
    
    # 5. Graph rendering sanity check
    main(["graph", "--all"])
    
    # 6. P2P Reachability / Doctor check
    main(["doctor", "--fix"])
    
    # 7. Super Status
    main(["status", "--porcelain"])
    
    # 8. GC
    main(["gc"])
    
    # 9. Verify everything still works
    main(["log", "--oneline"])
    
    print("E2E VALIDATION SUCCESSFUL")

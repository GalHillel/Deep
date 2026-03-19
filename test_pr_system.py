import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(os.path.abspath("src"))

from deep.core.pr import PRManager
from deep.core.repository import find_repo
from deep.core.constants import DEEP_DIR

try:
    repo_root = find_repo()
    dg_dir = repo_root / DEEP_DIR
    manager = PRManager(dg_dir)
    
    print("Testing PR Creation...")
    pr = manager.create_pr("Test PR", "tester", "feat-test", "main", "This is a test")
    print(f"Created PR #{pr.id}")
    
    print("\nTesting PR List...")
    prs = manager.list_prs()
    for p in prs:
        print(f"PR #{p.id}: {p.title} ({p.status})")
        
    print("\nTesting PR Merge...")
    # This might fail if branches didn't setup correctly
    try:
        pr = manager.merge_pr(pr.id)
        print(f"PR #{pr.id} merged successfully")
    except Exception as e:
        print(f"Merge failed: {e}")

except Exception as e:
    import traceback
    traceback.print_exc()

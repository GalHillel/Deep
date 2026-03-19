import sys
import os
from pathlib import Path
from deep.core.repository import find_repo
from deep.core.constants import DEEP_DIR
from deep.core.pr import PRManager
from deep.core.refs import get_current_branch, get_all_branches, resolve_revision, find_merge_base

try:
    repo_root = find_repo()
    dg_dir = repo_root / DEEP_DIR
    manager = PRManager(dg_dir)
    
    print(f"Repo: {repo_root}")
    print(f"Current branch: {get_current_branch(dg_dir)}")
    print(f"All branches: {get_all_branches(dg_dir)}")
    
    head = "feat-new"
    base = "main"
    
    head_sha = resolve_revision(dg_dir, head)
    base_sha = resolve_revision(dg_dir, base)
    
    print(f"Head ({head}): {head_sha}")
    print(f"Base ({base}): {base_sha}")
    
    if not head_sha or not base_sha:
        print("Error: Could not resolve branch SHAs")
        sys.exit(1)
        
    lca = find_merge_base(dg_dir, head_sha, base_sha)
    print(f"LCA: {lca}")
    
    if lca == head_sha:
        print("Info: LCA is HEAD (No changes from HEAD to BASE?)")
        # Wait, if LCA == head_sha, it means HEAD is behind or equal to BASE.
        # Usually, for a PR, we want HEAD to have changes NOT in BASE.
        # This means LCA should be BASE or some ancestor, but NOT HEAD itself.
        # If LCA == HEAD, there's nothing to merge into BASE.
    
    pr = manager.create_pr("Verification PR", "tester", head, base, "Checking overhaul body")
    print(f"Created PR #{pr.id}")
    
    pr_loaded = manager.get_pr(pr.id)
    print(f"Loaded PR status: {pr_loaded.status}")
    print(f"Loaded PR body: {pr_loaded.body}")
    
    print("\nTesting Merge...")
    pr_merged = manager.merge_pr(pr.id)
    print(f"PR status after merge: {pr_merged.status}")
    
    # Check if main branch was updated
    new_base_sha = resolve_revision(dg_dir, base)
    print(f"New base SHA ({base}): {new_base_sha}")

except Exception as e:
    import traceback
    traceback.print_exc()

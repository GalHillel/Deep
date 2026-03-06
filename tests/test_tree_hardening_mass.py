"""
tests.test_tree_hardening_mass
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Phase 6: Mass scenario test suite.
Simulates 1000 repository operations (nested dirs, mixed files, merges) 
and validates tree integrity after each step.
"""

import random
import string
from pathlib import Path
import pytest
from deep.cli.main import main
from deep.storage.objects import read_object, Tree, Commit, Blob
from deep.core.repository import DEEP_GIT_DIR
from deep.core.refs import resolve_head

def random_name(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def create_random_structure(repo_root: Path, depth=0, max_depth=3):
    """Recursively create random files and directories."""
    if depth > max_depth:
        return
    
    num_files = random.randint(1, 5)
    for _ in range(num_files):
        (repo_root / random_name()).write_text(random_name(100))
        
    if depth < max_depth:
        num_dirs = random.randint(1, 3)
        for _ in range(num_dirs):
            d = repo_root / random_name()
            d.mkdir(exist_ok=True)
            create_random_structure(d, depth + 1, max_depth)

def validate_all_trees(dg_dir: Path):
    """Walk every reachable tree and verify modes match object types."""
    objects_dir = dg_dir / "objects"
    head = resolve_head(dg_dir)
    if not head:
        return
    
    visited = set()
    queue = [head]
    
    while queue:
        sha = queue.pop(0)
        if sha in visited:
            continue
        visited.add(sha)
        
        obj = read_object(objects_dir, sha)
        if isinstance(obj, Commit):
            queue.append(obj.tree_sha)
            queue.extend(obj.parent_shas)
        elif isinstance(obj, Tree):
            for entry in obj.entries:
                child = read_object(objects_dir, entry.sha)
                if isinstance(child, Tree):
                    assert entry.mode == "40000", f"Tree {sha} entry {entry.name} is tree but mode is {entry.mode}"
                    queue.append(entry.sha)
                elif isinstance(child, Blob):
                    assert entry.mode != "40000", f"Tree {sha} entry {entry.name} is blob but mode is 40000"

def test_mass_scenarios(tmp_path: Path, monkeypatch):
    """Run 100 scenario iterations."""
    monkeypatch.chdir(tmp_path)
    main(["init"])
    dg_dir = tmp_path / DEEP_GIT_DIR
    
    # We'll do 100 iterations of random changes + commit + merge
    for i in range(100):
        # 1. Random changes
        create_random_structure(tmp_path, max_depth=random.randint(1, 4))
        
        # 2. Add and commit
        main(["add", "."])
        main(["commit", "-m", f"Iteration {i}"])
        
        # 3. Branching and merging occasionally
        if i > 0 and i % 10 == 0:
            current_head = resolve_head(dg_dir)
            main(["branch", f"branch_{i}"])
            # Make a change on main
            (tmp_path / f"main_{i}.txt").write_text("main")
            main(["add", "."])
            main(["commit", "-m", "main change"])
            
            # Switch to branch manually or via checkout
            # Note: checkout is safer
            main(["checkout", f"branch_{i}"])
            (tmp_path / f"branch_{i}.txt").write_text("branch")
            main(["add", "."])
            main(["commit", "-m", "branch change"])
            
            # Merge main into branch
            main(["merge", "main"])
            
        # 4. Validate all reachable objects
        validate_all_trees(dg_dir)

    print("\nMass scenario test passed (100 iterations with deep nesting).")

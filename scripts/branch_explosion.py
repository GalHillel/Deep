import subprocess
import os
import random
import time
import re
from pathlib import Path

REPO_DIR = Path(r"c:\Users\galh2\Documents\GitHub\deep-using-git\deep-test")
DEEP_EXE = ["python", "-m", "deep.cli.main"]

BRANCH_COUNT = 205
COMMITS_PER_BRANCH = 5

def run_deep(args, check=True):
    res = subprocess.run(DEEP_EXE + args, cwd=REPO_DIR, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"Error running deep {' '.join(args)}: {res.stderr}")
        # res.check_returncode()
    return res

def get_existing_branches():
    res = run_deep(["branch"], check=False)
    lines = res.stdout.splitlines()
    branches = []
    for line in lines:
        # Clean up line: remove '*', whitespace
        b = line.strip().replace("*", "").strip()
        if b:
            branches.append(b)
    return branches

def main():
    print(f"Starting/Resuming Branch Explosion (Target: {BRANCH_COUNT} branches, ~{BRANCH_COUNT * COMMITS_PER_BRANCH} commits)...")
    
    # 1. Ensure we are on main
    print("Switching to main...")
    run_deep(["checkout", "main"])
    
    existing_branches = get_existing_branches()
    print(f"Found {len(existing_branches)} existing branches.")
    
    # 2. Explosive branching
    branch_types = ["feature", "bugfix", "hotfix", "refactor", "experiment"]
    modules = ["frontend", "backend", "mobile", "infrastructure", "ai"]
    
    all_created_branches = []
    
    # Try to find the highest index already used
    max_idx = -1
    for b in existing_branches:
        match = re.search(r"task-(\d+)", b)
        if match:
            idx = int(match.group(1))
            if idx > max_idx:
                max_idx = idx
    
    start_idx = max_idx + 1
    print(f"Resuming from index {start_idx}...")
    
    for i in range(start_idx, BRANCH_COUNT):
        b_type = random.choice(branch_types)
        mod = random.choice(modules)
        b_name = f"{b_type}/{mod}-task-{i:03d}"
        
        print(f"[{i+1}/{BRANCH_COUNT}] Creating branch: {b_name}...")
        
        # Check if already exists just in case regex failed
        if b_name in existing_branches:
            print(f"Branch {b_name} already exists, skipping.")
            continue
            
        run_deep(["branch", b_name])
        run_deep(["checkout", b_name])
        
        # Make a few commits
        for c in range(COMMITS_PER_BRANCH):
            mod_dir = REPO_DIR / mod
            # Get a subset of files to avoid slow globbing on 50k files every time
            # We'll just grab some files from the module dir
            files = []
            try:
                # Use a shallower glob or limit results if possible
                files = list(mod_dir.glob("*.txt"))[:10] # Just some txt files in root of module
                if not files:
                    files = list(mod_dir.glob("**/*.txt"))[:10]
            except:
                pass
                
            if not files:
                target_file = mod_dir / f"activity_{i}_{c}.log"
                target_file.touch()
            else:
                target_file = random.choice(files)
            
            with open(target_file, "a", encoding="utf-8") as f:
                f.write(f"\n# Contribution {c} by worker {i} at {time.ctime()}\n")
            
            run_deep(["add", str(target_file.relative_to(REPO_DIR))])
            run_deep(["commit", "-m", f"feat: contribute to {mod} in {b_name} checkpoint {c}"])
        
        all_created_branches.append(b_name)
        
        # Every 25 branches, do a push of the current branch to show progress
        if (i + 1) % 25 == 0:
            print(f"Syncing progress for {b_name}...")
            run_deep(["push", "origin", b_name])
            
        run_deep(["checkout", "main"])

    print(f"Branch Explosion pass complete.")
    
    # Final sync of some samples if not already pushed
    print("Final sample sync...")
    for b in all_created_branches[::20]:
        print(f"Syncing sample branch: {b}")
        run_deep(["push", "origin", b])

if __name__ == "__main__":
    main()

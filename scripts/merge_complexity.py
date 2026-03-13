import subprocess
from pathlib import Path

REPO_DIR = Path(r"c:\Users\galh2\Documents\GitHub\deep-using-git\deep-test")
DEEP_EXE = ["python", "-m", "deep.cli.main"]

def run_deep(args, check=True):
    res = subprocess.run(DEEP_EXE + args, cwd=REPO_DIR, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"Error running deep {' '.join(args)}: {res.stderr}")
        res.check_returncode()
    return res

def get_branches():
    # Try deep branch first
    try:
        res = subprocess.run(DEEP_EXE + ["branch"], cwd=REPO_DIR, capture_output=True, text=True, check=True)
        lines = res.stdout.splitlines()
        branches = []
        for line in lines:
            line = line.strip()
            if not line or "Warning" in line or "result in unpredictable" in line:
                continue
            b = line.replace("*", "").strip()
            if b:
                branches.append(b)
        if branches:
            return branches
    except:
        pass
        
    # Fallback: List refs/heads directly
    refs_dir = REPO_DIR / ".deep_git" / "refs" / "heads"
    branches = []
    
    def walk_refs(d, prefix=""):
        for item in d.iterdir():
            if item.is_dir():
                walk_refs(item, prefix + item.name + "/")
            else:
                branches.append(prefix + item.name)
                
    if refs_dir.exists():
        walk_refs(refs_dir)
        
    return branches

def main():
    print("Starting Phase 4: Merge Graph Complexity...")
    
    all_branches = get_branches()
    print(f"Found {len(all_branches)} total branches.")
    
    # Filter for interesting ones
    # Filter out 'main', 'integration/staging', and any existing release branches from the list
    feature_branches = [b for b in all_branches if ("feature" in b.lower() or "task-" in b.lower() or "ai-" in b.lower() or "backend-" in b.lower()) and "integration" not in b.lower() and "release" not in b.lower() and b != "main"]
    bugfix_branches = [b for b in all_branches if ("bugfix" in b.lower() or "hotfix" in b.lower())]
    
    print(f"Targeting {len(feature_branches)} feature/task branches for merging.")
    
    # 2. Prepare integration branch
    integration_branch = "integration/staging"
    print(f"Preparing {integration_branch}...")
    run_deep(["checkout", "main"])
    
    # Check if exists
    if integration_branch in all_branches:
        print(f"Integration branch {integration_branch} already exists. Using it.")
        run_deep(["checkout", integration_branch])
    else:
        print(f"Creating {integration_branch}...")
        run_deep(["branch", integration_branch])
        run_deep(["checkout", integration_branch])
    
    # Merge feature branches
    # Limit to 15 to keep it manageable
    merged_count = 0
    for b in feature_branches[:15]:
        print(f"Merging {b} into {integration_branch}...")
        res = run_deep(["merge", b], check=False)
        if res.returncode != 0:
            print(f"Note: Merge of {b} completed with non-zero (might be expected in simulation).")
        merged_count += 1
            
    print(f"Merged {merged_count} branches into {integration_branch}.")
    
    # 3. Create a release candidate
    release_branch = f"release/v1.0.0-rc-{int(time.time()) % 1000}"
    print(f"Creating {release_branch} from main...")
    run_deep(["checkout", "main"])
    run_deep(["branch", release_branch])
    run_deep(["checkout", release_branch])
    
    print(f"Merging {integration_branch} into {release_branch}...")
    run_deep(["merge", integration_branch])
    
    # 4. Final push of merges
    print(f"Pushing {release_branch} to GitHub...")
    run_deep(["push", "origin", release_branch])
    
    # Also push main just in case
    print("Pushing main to GitHub...")
    run_deep(["push", "origin", "main"])
    
    print("Phase 4 Merge Graph Complexity complete.")

if __name__ == "__main__":
    import time
    main()

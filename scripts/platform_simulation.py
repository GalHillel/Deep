import json
import random
from pathlib import Path

REPO_DIR = Path(r"c:\Users\galh2\Documents\GitHub\deep-using-git\deep-test")
METADATA_DIR = REPO_DIR / ".deep_git" / "metadata"

def main():
    print("Starting Phase 5: Platform Metadata Simulation...")
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    
    issues_dir = METADATA_DIR / "issues"
    prs_dir = METADATA_DIR / "pull_requests"
    issues_dir.mkdir(exist_ok=True)
    prs_dir.mkdir(exist_ok=True)
    
    # 1. Create 200+ Issues
    print("Generating 220 Issues...")
    for i in range(220):
        issue = {
            "id": f"ISSUE-{i:03d}",
            "title": f"Enterprise Requirement {i}: Scalability Audit",
            "description": f"Detailed audit for module {random.choice(['AI', 'Frontend', 'Backend', 'Infra'])}",
            "status": random.choice(["open", "closed", "in-progress"]),
            "labels": random.choice([["bug"], ["feature"], ["critical"], ["security"]])
        }
        with open(issues_dir / f"issue_{i:03d}.json", "w") as f:
            json.dump(issue, f, indent=2)
            
    # 2. Create 100+ Pull Requests
    print("Generating 115 Pull Requests...")
    for i in range(115):
        pr = {
            "id": f"PR-{i:03d}",
            "title": f"Refactor module component {i}",
            "source_branch": f"feature/branch-{i}",
            "target_branch": "main",
            "status": random.choice(["open", "merged", "declined"]),
            "linked_issues": [f"ISSUE-{random.randint(0, 219):03d}"]
        }
        with open(prs_dir / f"pr_{i:03d}.json", "w") as f:
            json.dump(pr, f, indent=2)
            
    print("Phase 5 Metadata generation complete.")

if __name__ == "__main__":
    main()

import os
import sys
import shutil
import argparse
from pathlib import Path

# Setup path to import deep
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "src")))

from deep.commands.init_cmd import run as init_run
from deep.commands.add_cmd import run as add_run
from deep.commands.commit_cmd import run as commit_run
from deep.commands.branch_cmd import run as branch_run
from deep.commands.checkout_cmd import run as checkout_run
from deep.commands.issue_cmd import run as issue_run
from deep.commands.pr_cmd import run as pr_run
from deep.commands.status_cmd import run as status_run
from deep.core.issue import IssueManager
from deep.core.pr import PRManager

def test_unified_workflow():
    test_dir = Path("tmp_test_workflow")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    initial_cwd = os.getcwd()
    os.chdir(test_dir)
    
    try:
        # 1. Init
        init_run(argparse.Namespace(path=None, bare=False))
        
        # 2. Create Issue
        print("\n--- Testing Issue Creation ---")
        # Bypass interactive by using manager
        im = IssueManager(Path(".deep"))
        issue = im.create_issue("Crash on start", "Fix it", "bug", "tester")
        im.add_timeline_event(issue.id, "created")
        print(f"Created Issue #{issue.id}")

        # 3. Initial commit on main
        with open("README.md", "w") as f: f.write("# Deep")
        add_run(argparse.Namespace(files=["README.md"]))
        commit_run(argparse.Namespace(message="Initial commit", all=False, ai=False, sign=False))

        # 4. Feature branch and commit
        branch_run(argparse.Namespace(name="feat", delete=False, start_point="HEAD"))
        checkout_run(argparse.Namespace(target="feat", branch=False, force=False))
        with open("feat.txt", "w") as f: f.write("new feature")
        add_run(argparse.Namespace(files=["feat.txt"]))
        commit_run(argparse.Namespace(message="feat: working on issue #1", all=False, ai=False, sign=False))

        # 5. Create PR linked to issue
        print("\n--- Testing PR Linking ---")
        pm = PRManager(Path(".deep"))
        # Get commits for PR
        from deep.core.refs import resolve_revision, log_history
        head_sha = resolve_revision(Path(".deep"), "feat")
        base_sha = resolve_revision(Path(".deep"), "main")
        all_head = log_history(Path(".deep"), head_sha)
        all_base = set(log_history(Path(".deep"), base_sha))
        pr_commits = [c for c in all_head if c not in all_base]

        pr = pm.create_pr("Feat PR", "tester", "feat", "main", "Linking to #1", linked_issue=issue.id, commits=pr_commits)
        print(f"Created PR #{pr.id} linked to Issue #{issue.id}")

        # Verify Issue status
        issue = im.get_issue(issue.id)
        if issue.status != "in-progress":
            raise Exception(f"Issue status should be 'in-progress', got '{issue.status}'")
        print("✔ Issue status automatically moved to 'in-progress'")

        # 6. Commit with "fix #1"
        print("\n--- Testing Commit Intelligence ---")
        with open("fix.txt", "w") as f: f.write("fixed")
        add_run(argparse.Namespace(files=["fix.txt"]))
        # pr_cmd.run doesn't have commit intelligence, it's in commit_cmd.run
        commit_run(argparse.Namespace(message="fix #1: resolved the crash", all=False, ai=False, sign=False))
        
        # Verify Issue status
        issue = im.get_issue(issue.id)
        if issue.status != "closed":
            raise Exception(f"Issue status should be 'closed' after fix commit, got '{issue.status}'")
        print("✔ Issue automatically closed via commit message keywords")

        # 7. Reopen issue and merge PR
        im.reopen_issue(issue.id)
        print("\n--- Testing Auto-close on Merge ---")
        # Approve PR
        pm.add_review(pr.id, "reviewer", "approved")
        
        # pr merge <id>
        pr_run(argparse.Namespace(pr_command="merge", id=str(pr.id), verbose=False))
        
        # Verify Issue status
        issue = im.get_issue(issue.id)
        if issue.status != "closed":
            raise Exception(f"Issue status should be 'closed' after PR merge, got '{issue.status}'")
        print("✔ Issue automatically closed after linked PR was merged")

        # 8. Check deep status --work
        print("\n--- Testing deep status --work ---")
        status_run(argparse.Namespace(work=True, porcelain=False))

        print("\n\u2714 ALL TESTS PASSED: Unified Workflow Engine is fully operational.")

    finally:
        os.chdir(initial_cwd)
        if test_dir.exists():
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_unified_workflow()

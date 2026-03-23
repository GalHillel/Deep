import os
import sys
import shutil
import argparse
from pathlib import Path

# Setup path to import deep
sys.path.append(os.getcwd() + "/src")

from deep.commands.init_cmd import run as init_run
from deep.commands.add_cmd import run as add_run
from deep.commands.commit_cmd import run as commit_run
from deep.commands.branch_cmd import run as branch_run
from deep.commands.checkout_cmd import run as checkout_run
from deep.commands.pr_cmd import run as pr_run

def test_pr_merge_real():
    test_dir = Path("tmp_test_pr_merge")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    os.chdir(test_dir)
    
    try:
        # 1. Init
        init_run(argparse.Namespace(path=None, bare=False))
        
        # 2. Main commit
        with open("main.txt", "w") as f: f.write("main")
        add_run(argparse.Namespace(files=["main.txt"]))
        commit_run(argparse.Namespace(message="Initial commit", all=False, ai=False, sign=False))
        
        # 3. Feature branch
        branch_run(argparse.Namespace(name="feat", delete=False, start_point="HEAD"))
        checkout_run(argparse.Namespace(target="feat", branch=False, force=False))
        
        with open("feat.txt", "w") as f: f.write("feat")
        add_run(argparse.Namespace(files=["feat.txt"]))
        commit_run(argparse.Namespace(message="Feature commit", all=False, ai=False, sign=False))
        
        # 4. Back to main
        checkout_run(argparse.Namespace(target="main", branch=False, force=False))
        
        # 5. Create PR
        # We need to simulate the pr command
        # pr create -m "Test PR" -d "Desc" --head feat --base main
        # But wait, pr_cmd.run expects 'args' correctly set up.
        # create_args = argparse.Namespace(pr_command="create", title="Test PR", description="Desc", head="feat", base="main", verbose=False)
        # However, pr_cmd.run with 'create' might call input().
        # Let's bypass the interactive part by mock or just using the manager.
        
        from deep.core.pr import PRManager
        from deep.core.constants import DEEP_DIR
        manager = PRManager(Path(".deep"))
        pr = manager.create_pr("Test PR", "tester", "feat", "main", "Desc")
        manager.add_review(pr.id, "reviewer", "approved")
        print(f"Approved PR #{pr.id}")
        
        # 6. Merge PR
        merge_args = argparse.Namespace(pr_command="merge", id=str(pr.id), verbose=False)
        pr_run(merge_args)
        
        # 7. Verify
        if not os.path.exists("feat.txt"):
            raise Exception("Verification failed: feat.txt missing from working directory after merge")
            
        pr_status = manager.get_pr(pr.id).status
        if pr_status != "merged":
            raise Exception(f"Verification failed: PR status is {pr_status}, expected 'merged'")
            
        print("\n\u2714 SUCCESS: PR merge performed real integration safely.")
        
    finally:
        os.chdir("..")
        shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_pr_merge_real()

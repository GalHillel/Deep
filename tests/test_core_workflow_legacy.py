import subprocess
import tempfile
import sys
from pathlib import Path
from deep.cli.main import main as deep_main
from deep.core.repository import DEEP_DIR

def run_deep(cmd_list, cwd):
    print(f"RUN: deep {' '.join(cmd_list)}")
    res = subprocess.run(["deep"] + cmd_list, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"ERROR executing: deep {' '.join(cmd_list)}")
        print(f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        sys.exit(1)
    return res.stdout

def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = pathlib.Path(tmpdir) / "test_repo"
        repo_dir.mkdir()
        cwd = str(repo_dir)

        print("--- Testing Core Workflow ---")
        run_deep(["init"], cwd)
        
        # Create and commit first file
        (repo_dir / "file1.txt").write_text("Hello World!")
        run_deep(["add", "file1.txt"], cwd)
        run_deep(["commit", "-m", "Initial commit"], cwd)
        
        # Check status
        st = run_deep(["status"], cwd)
        if "working tree clean" not in st:
            print(f"Unexpected status: {st}")
            sys.exit(1)
            
        # Branch
        run_deep(["branch", "feature-1"], cwd)
        run_deep(["checkout", "feature-1"], cwd)
        
        # Modify and commit
        (repo_dir / "file1.txt").write_text("Hello World! Feature 1")
        (repo_dir / "file2.txt").write_text("Second file")
        run_deep(["add", "."], cwd)
        run_deep(["commit", "-m", "Feature 1 added"], cwd)
        
        # Checkout main and merge
        run_deep(["checkout", "main"], cwd)
        run_deep(["merge", "feature-1"], cwd)
        
        # Verify log
        log_out = run_deep(["log", "--oneline"], cwd)
        if "Feature 1 added" not in log_out or "Initial commit" not in log_out:
            print("Missing commits in log")
            sys.exit(1)
            
        print("--- Testing Rebase & Reset ---")
        # Create a branch for rebase testing
        run_deep(["branch", "feature-2"], cwd)
        
        # Make a commit on main
        (repo_dir / "file3.txt").write_text("File 3 on main")
        run_deep(["add", "file3.txt"], cwd)
        run_deep(["commit", "-m", "Commit on main"], cwd)
        
        # Make a commit on feature-2
        run_deep(["checkout", "feature-2"], cwd)
        (repo_dir / "file4.txt").write_text("File 4 on feature-2")
        run_deep(["add", "file4.txt"], cwd)
        run_deep(["commit", "-m", "Commit on feature-2"], cwd)
        
        # Rebase feature-2 onto main
        run_deep(["rebase", "main"], cwd)
        
        # Verify
        st = run_deep(["status", "--porcelain"], cwd)
        log_out = run_deep(["log", "--oneline"], cwd)
        assert "Commit on main" in log_out
        assert "Commit on feature-2" in log_out

        # Test reset
        run_deep(["checkout", "main"], cwd)
        run_deep(["reset", "--hard", "HEAD^"], cwd) # Reset to before "Commit on main"
        
        log_reset = run_deep(["log", "--oneline"], cwd)
        assert "Commit on main" not in log_reset
        assert "Feature 1 added" in log_reset

        print("--- Core Workflow Validation PASSED ---")

if __name__ == "__main__":
    main()

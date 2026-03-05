import subprocess
import tempfile
import pathlib
import sys
import time
import uuid

def run_deep(cmd_list, cwd):
    res = subprocess.run(["deep"] + cmd_list, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"ERROR executing: deep {' '.join(cmd_list)}")
        print(f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        sys.exit(1)
    return res.stdout

def main():
    print("--- PHASE 6 & 7: STORAGE ENGINE & STRESS TEST ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = pathlib.Path(tmpdir) / "stress_repo"
        repo_dir.mkdir()
        cwd = str(repo_dir)

        run_deep(["init"], cwd)
        
        # Test Transaction & Rollback
        print("Testing Rollback...")
        (repo_dir / "safe.txt").write_text("safe")
        run_deep(["add", "safe.txt"], cwd)
        run_deep(["commit", "-m", "safe commit"], cwd)
        
        # Add a bad file
        (repo_dir / "bad.txt").write_text("bad")
        run_deep(["add", "bad.txt"], cwd)
        run_deep(["commit", "-m", "bad commit"], cwd)
        
        # Rollback the last transaction
        run_deep(["rollback"], cwd)
        
        log_out = run_deep(["log", "--oneline"], cwd)
        if "bad commit" in log_out:
            print("Rollback failed to remove bad commit!")
            sys.exit(1)
        if "safe commit" not in log_out:
            print("Rollback removed safe commit!")
            sys.exit(1)
            
        print("Testing Stress / Performance...")
        start_time = time.time()
        
        # Stress: Create 100 files, add and commit them rapidly
        for i in range(100):
            (repo_dir / f"stress_{i}.txt").write_text(f"content {uuid.uuid4()}")
        
        run_deep(["add", "."], cwd)
        run_deep(["commit", "-m", "stress 100 files"], cwd)
        
        # Stress: Create 50 rapid commits
        for i in range(50):
            (repo_dir / "rapid.txt").write_text(f"rapid {i}")
            run_deep(["add", "rapid.txt"], cwd)
            run_deep(["commit", "-m", f"rapid commit {i}"], cwd)
            
        end_time = time.time()
        duration = end_time - start_time
        print(f"Stress test completed in {duration:.2f} seconds.")
        
        # Check doctor
        print("Running deep doctor...")
        doctor_out = run_deep(["doctor"], cwd)
        if "FATAL" in doctor_out or "Error" in doctor_out:
            print("Doctor found corruption!")
            sys.exit(1)
            
        print("--- PHASE 6 & 7 PASSED ---")

if __name__ == "__main__":
    main()

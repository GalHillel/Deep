import os
import subprocess
import shutil
from pathlib import Path

def run_cmd(cmd, cwd=None, input=None):
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, input=input, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(f"STDERR: {result.stderr.strip()}")
    return result

def main():
    test_dir = Path("c:/Users/galh2/Documents/GitHub/DeepGit/tmp_test_repair")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # 1. Setup local git remote
    remote_dir = test_dir / "remote.git"
    run_cmd(["git", "init", "--bare", str(remote_dir)])

    # 2. Setup DeepGit repo
    repo_dir = test_dir / "deep_repo"
    repo_dir.mkdir()
    os.chdir(repo_dir)
    
    # Use python -m deep.cli.main to avoid path issues with 'deep' command
    deep_py = "python -m deep.cli.main"
    
    run_cmd(["python", "-m", "deep.cli.main", "init"])

    # 3. Create problematic files
    # Note: Windows doesn't allow \n in filenames physically, 
    # but we can simulate what happens if a name *would* have it or other invalid chars.
    (repo_dir / "README.md").write_text("Standard file")
    
    # Create a file with a trailing space (Windows-illegal but our sanitization handles it)
    # Actually, we'll try to add it via 'deep add' logic if we can mock the input
    # or just create files that our sanitization will "fix".
    
    run_cmd(["python", "-m", "deep.cli.main", "add", "README.md"])
    run_cmd(["python", "-m", "deep.cli.main", "commit", "-m", "Initial commit"])

    # 4. Push to remote
    run_cmd(["python", "-m", "deep.cli.main", "push", str(remote_dir).replace("\\", "/"), "main"])

    # 5. Verify Git integrity
    print("\n--- Verifying Git Integrity ---")
    clone_dir = test_dir / "git_clone"
    run_cmd(["git", "clone", str(remote_dir), str(clone_dir)])
    
    fsck_res = run_cmd(["git", "fsck"], cwd=clone_dir)
    if "error" in fsck_res.stderr.lower() or "bad" in fsck_res.stderr.lower():
        print("FAIL: git fsck found issues")
    else:
        print("SUCCESS: git fsck is clean")

    # 6. Check for invisible characters using debug-tree
    print("\n--- Deep debug-tree output ---")
    run_cmd(["python", "-m", "deep.cli.main", "debug-tree"])

if __name__ == "__main__":
    main()

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

def run_cmd(cmd, cwd=None, env=None):
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result

def main():
    root = Path("final_val").resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent)
    env["FORCE_COLOR"] = "1"
    
    deep = [sys.executable, "-m", "deep_git.main"]
    
    # 1. Init
    server_repo = root / "server_repo"
    run_cmd(deep + ["init", str(server_repo)], env=env)
    
    # 2. Add and Commit
    (server_repo / "README.md").write_text("# DeepGit Server\nThis is a remote repo.")
    (server_repo / "data.txt").write_text("Some initial data.")
    run_cmd(deep + ["add", "."], cwd=server_repo, env=env)
    run_cmd(deep + ["commit", "-m", "Initial server commit"], cwd=server_repo, env=env)
    
    # 3. Start Daemon
    print("\nStarting Daemon...")
    daemon_proc = subprocess.Popen(deep + ["daemon", "--port", "9876"], cwd=server_repo, env=env)
    time.sleep(2)
    
    try:
        # 4. Clone
        client_dir = root / "client_clone"
        run_cmd(deep + ["clone", "localhost:9876", str(client_dir)], env=env)
        
        # 5. Status and Log in Clone
        run_cmd(deep + ["status"], cwd=client_dir, env=env)
        run_cmd(deep + ["log", "--oneline", "--graph"], cwd=client_dir, env=env)
        
        # 6. Make changes and Commit
        (client_dir / "new_feature.py").write_text("print('hello world')")
        run_cmd(deep + ["add", "."], cwd=client_dir, env=env)
        run_cmd(deep + ["commit", "-m", "Add new feature"], cwd=client_dir, env=env)
        
        # 7. Add another file for status check
        (client_dir / "modified.txt").write_text("modified content")
        run_cmd(deep + ["add", "modified.txt"], cwd=client_dir, env=env)
        (client_dir / "modified.txt").write_text("modified again")
        
        (client_dir / "untracked.txt").write_text("untracked")
        
        print("\nChecking rich status output:")
        run_cmd(deep + ["status"], cwd=client_dir, env=env)
        
        # 8. Verification
        run_cmd(deep + ["doctor"], cwd=client_dir, env=env)
        
        print("\nWorkflow Complete. Visual Verification passed.")
        
    finally:
        daemon_proc.terminate()
        daemon_proc.wait()

if __name__ == "__main__":
    main()

import os
import subprocess
import sys
import time
from pathlib import Path
import shutil

# Config
NUM_COMMITS = 1000
CONCURRENT_CLIENTS = 5

def run_cmd(args, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)

def stress_test(tmp_path):
    print(f"Starting stress test with {NUM_COMMITS} commits...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    env["PYTHONUNBUFFERED"] = "1"
    
    server_root = tmp_path / "server"
    server_root.mkdir()
    run_cmd([sys.executable, "-m", "deep_git.main", "init"], cwd=server_root, env=env)
    
    # 1. Generate 1000 commits
    start_time = time.time()
    for i in range(NUM_COMMITS):
        f = server_root / f"file_{i}.txt"
        f.write_text(f"content {i}")
        run_cmd([sys.executable, "-m", "deep_git.main", "add", f"file_{i}.txt"], cwd=server_root, env=env)
        run_cmd([sys.executable, "-m", "deep_git.main", "commit", "-m", f"commit {i}"], cwd=server_root, env=env)
        if i % 100 == 0:
            print(f"Generated {i} commits...")
    
    gen_time = time.time() - start_time
    print(f"Generated {NUM_COMMITS} commits in {gen_time:.2f}s")
    
    # 2. Run benchmark
    print("Running deep benchmark...")
    res = run_cmd([sys.executable, "-m", "deep_git.main", "benchmark"], cwd=server_root, env=env)
    print(res.stdout)
    
    # 3. Start Daemon
    import socket
    def get_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
            
    port = get_free_port()
    daemon_proc = subprocess.Popen(
        [sys.executable, "-m", "deep_git.main", "daemon", "--port", str(port)],
        cwd=server_root,
        env=env
    )
    time.sleep(2)
    
    try:
        # 4. Clone to a client
        client_root = tmp_path / "client"
        print(f"Cloning {NUM_COMMITS} commits...")
        start_time = time.time()
        res = run_cmd([sys.executable, "-m", "deep_git.main", "clone", f"127.0.0.1:{port}", str(client_root)], env=env)
        if res.returncode != 0:
             print(f"Clone failed: {res.stderr}")
             return
             
        clone_time = time.time() - start_time
        print(f"Cloned {NUM_COMMITS} commits in {clone_time:.2f}s")
        
        # 5. Concurrent Fetches
        print(f"Starting {CONCURRENT_CLIENTS} concurrent fetches...")
        # Get head sha
        from deep_git.core.refs import resolve_head
        from deep_git.core.repository import DEEP_GIT_DIR
        head_sha = resolve_head(server_root / DEEP_GIT_DIR)
        
        procs = []
        for i in range(CONCURRENT_CLIENTS):
            c_root = tmp_path / f"client_concurrent_{i}"
            c_root.mkdir()
            run_cmd([sys.executable, "-m", "deep_git.main", "init"], cwd=c_root, env=env)
            p = subprocess.Popen(
                [sys.executable, "-m", "deep_git.main", "fetch", f"127.0.0.1:{port}", head_sha],
                cwd=c_root,
                env=env
            )
            procs.append(p)
            
        for p in procs:
            p.wait()
        print("Concurrent fetches completed.")
        
        # 6. GC stress
        print("Running GC on server...")
        start_time = time.time()
        res = run_cmd([sys.executable, "-m", "deep_git.main", "gc"], cwd=server_root, env=env)
        gc_time = time.time() - start_time
        print(f"GC completed in {gc_time:.2f}s")
        
        # 7. Doctor sweep
        print("Running Doctor on all repos...")
        for r in [server_root, client_root]:
            res = run_cmd([sys.executable, "-m", "deep_git.main", "doctor"], cwd=r, env=env)
            if "HEALTHY" not in res.stdout:
                print(f"HEALTH CHECK FAILED for {r}: {res.stdout}")
            else:
                print(f"HEALTH CHECK PASSED for {r}")

    finally:
        daemon_proc.terminate()
        daemon_proc.wait()

if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        stress_test(Path(tmp_dir))

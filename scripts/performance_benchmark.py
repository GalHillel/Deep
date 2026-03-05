"""
scripts.performance_benchmark
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Phase 9: Measure performance of core operations.
"""

import time
import shutil
import os
from pathlib import Path
from deep_git.main import main

def benchmark_op(name, func):
    start = time.perf_counter()
    func()
    end = time.perf_counter()
    print(f"{name}: {end - start:.4f}s")
    return end - start

def setup_test_env(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()
    os.chdir(path)
    main(["init"])

def create_medium_repo(path: Path, num_files=500):
    for i in range(num_files):
        (path / f"file_{i}.txt").write_text(f"content {i}" * 10)
    main(["add", "."])
    main(["commit", "-m", "medium commit"])

import tempfile

def run_benchmarks():
    import uuid
    root_tmp = f"perf_bench_{uuid.uuid4().hex[:6]}"
    root = Path(root_tmp).resolve()
    root.mkdir(parents=True, exist_ok=True)
    
    server_path = root / "server"
    setup_test_env(server_path)
    print(f"Creating medium repo with 1000 files in {root_tmp}...")
    create_medium_repo(server_path, 1000)
    
    # Start daemon
    import subprocess
    import sys
    
    print("Starting daemon for clone benchmark...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent)
    daemon_proc = subprocess.Popen([sys.executable, "-m", "deep_git.main", "daemon", "--port", "9998"], 
                                  cwd=server_path, env=env)
    time.sleep(2) # Wait for daemon
    
    try:
        os.chdir(root)
        
        def do_clone():
            subprocess.run([sys.executable, "-m", "deep_git.main", "clone", "localhost:9998", "client_clone"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        clone_time = benchmark_op("Clone 1000 files", do_clone)
        
        def do_status():
            subprocess.run([sys.executable, "-m", "deep_git.main", "status"], cwd=root / "client_clone", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        benchmark_op("Status on 1000 files", do_status)
        
        def do_log():
            subprocess.run([sys.executable, "-m", "deep_git.main", "log", "-n", "10"], cwd=root / "client_clone", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        benchmark_op("Log (10 entries)", do_log)
    finally:
        daemon_proc.terminate()
        try:
            daemon_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon_proc.kill()
        
    print("\nBenchmark Complete.")
    if clone_time < 3.0:
        print("PASS: Clone < 3s requirement met.")
    else:
        print("FAIL: Clone > 3s requirement.")

if __name__ == "__main__":
    run_benchmarks()

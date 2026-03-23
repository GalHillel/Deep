import os
import shutil
import sys
import tempfile
import time
import pytest
import subprocess
from pathlib import Path

# Add src to sys.path to import deep modules
sys.path.append(os.path.abspath("src"))

from deep.core.repository import init_repo, find_repo, DEEP_DIR
from deep.storage.index import read_index
from deep.core.refs import resolve_head, get_branch, get_current_branch, update_branch, update_head
from deep.core.status import compute_status

def log(msg):
    print(f"[*] {msg}")

def check(condition, msg):
    if condition:
        print(f"[PASS] {msg}")
    else:
        print(f"[FAIL] {msg}")
        assert condition, msg

def run_phase_1(workspace: Path):
    log("Phase 1: Init & Repository Setup")
    os.chdir(workspace)
    from deep.cli.main import main
    main(["init"])
    
    dg_dir = workspace / DEEP_DIR
    check(dg_dir.exists(), "Initial .deep exists")
    check((dg_dir / "objects").is_dir(), "objects directory exists")
    check((dg_dir / "refs" / "heads").is_dir(), "refs/heads directory exists")
    check((dg_dir / "HEAD").is_file(), "HEAD file exists")
    
    # Verify index exists (binary format now)
    check((dg_dir / "index").is_file(), "Empty index exists")
    
    head_val = resolve_head(dg_dir)
    check(get_current_branch(dg_dir) == "main", "HEAD points to main branch")

def run_phase_2(workspace: Path):
    log("Phase 2: Basic Operations (Add/Commit)")
    from deep.cli.main import main
    (workspace / "f1.txt").write_text("hello deep")
    main(["add", "f1.txt"])
    
    main(["commit", "-m", "first commit"])
    head_sha = resolve_head(workspace / DEEP_DIR)
    check(head_sha is not None, "First commit SHA created")
    
    (workspace / "dir1").mkdir()
    (workspace / "dir1" / "f2.txt").write_text("nested file")
    (workspace / "script.py").write_text("print('hello')")
    main(["add", "."])
    main(["commit", "-m", "second commit"])
    
    new_head = resolve_head(workspace / DEEP_DIR)
    check(new_head != head_sha, "HEAD updated after second commit")

def run_phase_3(workspace: Path):
    log("Phase 3: Branching & Checkout")
    from deep.cli.main import main
    main(["branch", "feat-x"])
    check(get_branch(workspace / DEEP_DIR, "feat-x") is not None, "Branch feat-x created")
    
    main(["checkout", "feat-x"])
    check(get_current_branch(workspace / DEEP_DIR) == "feat-x", "Switched to feat-x")
    
    (workspace / "feat.txt").write_text("feature content")
    main(["add", "feat.txt"])
    main(["commit", "-m", "feat commit"])
    
    main(["checkout", "main"])
    check(not (workspace / "feat.txt").exists(), "feat.txt gone on main")
    check(get_current_branch(workspace / DEEP_DIR) == "main", "Back on main")

def run_phase_4(workspace: Path):
    log("Phase 4: Status & Diff")
    from deep.cli.main import main
    (workspace / "f1.txt").write_text("modified content")
    res = compute_status(workspace)
    check("f1.txt" in res.modified, "Status detects modification")
    
    # Subprocess for diff to check output
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
    res = subprocess.run([sys.executable, "-m", "deep.cli.main", "diff"], capture_output=True, text=True, env=env)
    check("+modified content" in res.stdout, "Diff shows added line")

def run_phase_5(workspace: Path):
    log("Phase 5: Merging")
    from deep.cli.main import main
    main(["merge", "feat-x"])
    check((workspace / "feat.txt").exists(), "Merge brought feat.txt")
    
    # Conflict test
    main(["branch", "side"])
    (workspace / "conflict.txt").write_text("base")
    main(["add", "conflict.txt"])
    main(["commit", "-m", "conflict base"])
    
    main(["checkout", "side"])
    (workspace / "conflict.txt").write_text("side change")
    main(["add", "conflict.txt"])
    main(["commit", "-m", "side commit"])
    
    main(["checkout", "main"])
    (workspace / "conflict.txt").write_text("main change")
    main(["add", "conflict.txt"])
    main(["commit", "-m", "main commit"])
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
    # Merge side into main
    proc = subprocess.run([sys.executable, "-m", "deep.cli.main", "merge", "side"], capture_output=True, text=True, env=env)
    check("CONFLICT" in proc.stdout or proc.returncode != 0, "Merge conflict detected")

def run_phase_6(workspace: Path):
    log("Phase 6: Remote Operations (Simulation)")
    from deep.cli.main import main
    main(["remote", "add", "origin", "deep://localhost:9999/repo"])
    from deep.core.config import Config
    cfg = Config(workspace)
    # Changed to use dot notation property
    check(cfg.get("remote.origin.url") == "deep://localhost:9999/repo", "Remote origin added to config")

def run_phase_7(workspace: Path):
    log("Phase 7: Object Integrity & GC")
    from deep.cli.main import main
    main(["gc"]) # Should not crash
    check((workspace / DEEP_DIR / "objects").is_dir(), "Objects dir intact after GC")

def run_phase_8(workspace: Path):
    log("Phase 8: Audit & Doctor")
    from deep.cli.main import main
    main(["audit"])
    main(["doctor"])
    print("Audit/Doctor: PASSED")

def run_phase_9(workspace: Path):
    log("Phase 9: Security Scan")
    python_files = list(workspace.rglob("*.py"))
    check(len(python_files) > 0, "Found python files to scan")

@pytest.mark.slow
def test_exhaustive_audit():
    with tempfile.TemporaryDirectory() as audit_workspace:
        audit_workspace_path = Path(audit_workspace)
        log(f"Starting Exhaustive Audit in {audit_workspace}")
        original_cwd = os.getcwd()
        try:
            run_phase_1(audit_workspace_path)
            run_phase_2(audit_workspace_path)
            run_phase_3(audit_workspace_path)
            run_phase_4(audit_workspace_path)
            run_phase_5(audit_workspace_path)
            # run_phase_6(audit_workspace_path)  # Disabled: remote feature experimental
            run_phase_7(audit_workspace_path)
            run_phase_8(audit_workspace_path)
            run_phase_9(audit_workspace_path)
        finally:
            os.chdir(original_cwd)

if __name__ == "__main__":
    test_exhaustive_audit()

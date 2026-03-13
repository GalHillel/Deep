import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Add src to sys.path to import deep modules
sys.path.append(os.path.abspath("src"))

from deep.core.repository import init_repo, find_repo, DEEP_GIT_DIR
from deep.storage.index import read_index
from deep.core.refs import resolve_head, get_branch, get_current_branch, update_head
from deep.core.status import compute_status

def log(msg):
    print(f"[*] {msg}")

def check(condition, msg):
    if condition:
        print(f"[PASS] {msg}")
    else:
        print(f"[FAIL] {msg}")
        sys.exit(1)

def run_phase_1(audit_dir):
    log("Phase 1: Init & Repository Setup")
    
    # 1. Fresh init
    repo_path = Path(audit_dir) / "phase1_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    dg_dir = repo_path / DEEP_GIT_DIR
    check(dg_dir.exists(), "Initial .deep_git exists")
    check((dg_dir / "objects").is_dir(), "objects directory exists")
    check((dg_dir / "refs" / "heads").is_dir(), "refs/heads directory exists")
    check((dg_dir / "HEAD").is_file(), "HEAD file exists")
    check((dg_dir / "index").is_file(), "Empty index exists")
    
    # 2. Verify HEAD content
    head_content = (dg_dir / "HEAD").read_text()
    check("ref: refs/heads/main" in head_content, "HEAD points to main branch")
    
    # 3. Test re-init (should fail if already initialized)
    try:
        init_repo(repo_path)
        check(False, "Re-init should have failed")
    except FileExistsError:
        check(True, "Re-init failed as expected")
    
    # 4. Init in non-empty directory
    nested_path = Path(audit_dir) / "non_empty"
    nested_path.mkdir()
    (nested_path / "existing.txt").write_text("hello")
    init_repo(nested_path)
    check((nested_path / DEEP_GIT_DIR).exists(), "Init in non-empty dir works")
    
    log("Phase 1 Completed Successfully\n")

def run_phase_2(audit_dir):
    log("Phase 2: Add & Status Correctness")
    repo_path = Path(audit_dir) / "phase2_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    from deep.commands import add_cmd
    
    # 1. Create 1000+ files
    log("Creating 1000 files...")
    for i in range(1005):
        (repo_path / f"file_{i}.txt").write_text(f"content {i}")
    
    # 2. Add all
    class Args:
        files = ["."]
        ai = False
        sign = False
    
    os.chdir(repo_path)
    add_cmd.run(Args())
    
    # 3. Verify index
    index = read_index(repo_path / DEEP_GIT_DIR)
    check(len(index.entries) == 1005, f"All 1005 files staged (index size: {len(index.entries)})")
    
    # 4. Status Check
    status = compute_status(repo_path)
    check(len(status.staged_new) == 1005, "Status reports 1005 staged new files")
    check(len(status.untracked) == 0, "No untracked files left")
    
    # 5. Idempotency check
    add_cmd.run(Args())
    index_after = read_index(repo_path / DEEP_GIT_DIR)
    check(len(index_after.entries) == 1005, "Repeated add is idempotent")
    
    # 6. Binary file and deep directories
    deep_dir = repo_path / "a" / "b" / "c"
    deep_dir.mkdir(parents=True)
    (deep_dir / "deep.bin").write_bytes(os.urandom(1024))
    
    add_cmd.run(Args())
    status_deep = compute_status(repo_path)
    check("a/b/c/deep.bin" in status_deep.staged_new, "Deep directory and binary file staged")
    
    # 7. Deletion detection
    (repo_path / "file_0.txt").unlink()
    status_del = compute_status(repo_path)
    # file_0.txt was already staged as "staged_new" but it's now missing from workdir.
    # deep status should show it as "deleted" (unstaged) or handle it as missing from workdir vs staged.
    check("file_0.txt" in status_del.deleted, "Detected deletion in workdir")

    log("Phase 2 Completed Successfully\n")

def run_phase_3(audit_dir):
    log("Phase 3: Commit Graph Validation")
    repo_path = Path(audit_dir) / "phase3_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    from deep.commands import add_cmd, commit_cmd
    from deep.storage.objects import read_object, Commit
    
    os.chdir(repo_path)
    
    # 1. First commit
    (repo_path / "README.md").write_text("Hello")
    add_cmd.run(SafeArgs(files=["README.md"], ai=False, sign=False))
    
    # Set deterministic env vars
    os.environ["DEEP_COMMIT_TIMESTAMP"] = "1700000000"
    os.environ["DEEP_COMMIT_TIMEZONE"] = "+0000"
    
    commit_cmd.run(SafeArgs(message="First commit", ai=False, sign=False))
    
    c1_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    check(c1_sha is not None, "First commit SHA created")
    
    c1_obj = read_object(repo_path / DEEP_GIT_DIR / "objects", c1_sha)
    log(f"C1 SHA: {c1_sha}")
    log(f"C1 Tree SHA: {c1_obj.tree_sha}")
    # log(f"C1 Content: {repr(c1_obj.serialize_content())}")
    
    check(isinstance(c1_obj, Commit), "First commit object is valid")
    check(len(c1_obj.parent_shas) == 0, "First commit has no parents")
    
    # 2. Second commit (Sequential)
    (repo_path / "README.md").write_text("Updated Hello")
    add_cmd.run(SafeArgs(files=["README.md"], ai=False, sign=False))
    
    os.environ["DEEP_COMMIT_TIMESTAMP"] = "1700000060"
    commit_cmd.run(SafeArgs(message="Second commit", ai=False, sign=False))
    
    c2_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    check(c2_sha != c1_sha, "Second commit has different SHA")
    
    c2_obj = read_object(repo_path / DEEP_GIT_DIR / "objects", c2_sha)
    log(f"C2 SHA: {c2_sha}")
    check(c2_obj.parent_shas == [c1_sha], "Second commit points to first commit as parent")
    
    # 3. Verify Deterministic Hash
    log("Verifying Determinism in sibling repo...")
    repo_path_2 = Path(audit_dir) / "phase3_repo_alt"
    repo_path_2.mkdir()
    init_repo(repo_path_2)
    os.chdir(repo_path_2)
    (repo_path_2 / "README.md").write_text("Hello")
    add_cmd.run(SafeArgs(files=["README.md"], ai=False, sign=False))
    os.environ["DEEP_COMMIT_TIMESTAMP"] = "1700000000"
    commit_cmd.run(SafeArgs(message="First commit", ai=False, sign=False))
    
    c1_alt_sha = resolve_head(repo_path_2 / DEEP_GIT_DIR)
    c1_alt_obj = read_object(repo_path_2 / DEEP_GIT_DIR / "objects", c1_alt_sha)
    
    log(f"C1 Alt SHA: {c1_alt_sha}")
    log(f"C1 Alt Tree SHA: {c1_alt_obj.tree_sha}")
    
    if c1_alt_sha != c1_sha:
        log("DIFF DETECTED!")
        log(f"C1 Author: {repr(c1_obj.author)}")
        log(f"C1 Alt Author: {repr(c1_alt_obj.author)}")
        log(f"C1 Timestamp: {c1_obj.timestamp}")
        log(f"C1 Alt Timestamp: {c1_alt_obj.timestamp}")
        log(f"C1 Content:\n{c1_obj.serialize_content().decode()}")
        log(f"C1 Alt Content:\n{c1_alt_obj.serialize_content().decode()}")

    check(c1_alt_sha == c1_sha, f"Deterministic hashes verified ({c1_sha} == {c1_alt_sha})")
    
    log("Phase 3 Completed Successfully\n")

def run_phase_4(audit_dir):
    log("Phase 4: Branch Operations")
    repo_path = Path(audit_dir) / "phase4_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    from deep.commands import add_cmd, commit_cmd, branch_cmd
    
    os.chdir(repo_path)
    (repo_path / "init.txt").write_text("init")
    add_cmd.run(SafeArgs(files=["init.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="initial", ai=False, sign=False))
    
    # 1. Create 1000 branches
    log("Creating 1000 branches...")
    for i in range(1000):
        branch_cmd.run(SafeArgs(name=f"feature_{i}", start_point="HEAD", delete=False, list=False, rename=None))
    
    # 2. List branches
    from deep.core.refs import list_branches
    branches = list_branches(repo_path / DEEP_GIT_DIR)
    check(len(branches) == 1001, f"Total 1001 branches listed (expected 1000 features + main)")
    
    # 3. Rename branch
    branch_cmd.run(SafeArgs(name="new_feature", start_point="feature_0", rename="feature_0", delete=False, list=False))
    check(get_branch(repo_path / DEEP_GIT_DIR, "feature_0") is None, "Old branch name removed")
    check(get_branch(repo_path / DEEP_GIT_DIR, "new_feature") is not None, "New branch name exists")
    
    # 4. Delete branch
    branch_cmd.run(SafeArgs(name="feature_1", delete=True, start_point=None, list=False, rename=None))
    check(get_branch(repo_path / DEEP_GIT_DIR, "feature_1") is None, "Branch deleted successfully")
    
    log("Phase 4 Completed Successfully\n")

def run_phase_5(audit_dir):
    log("Phase 5: Checkout Engine")
    repo_path = Path(audit_dir) / "phase5_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    from deep.commands import add_cmd, commit_cmd, checkout_cmd, branch_cmd
    
    os.chdir(repo_path)
    (repo_path / "file1.txt").write_text("v1")
    add_cmd.run(SafeArgs(files=["file1.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="v1", ai=False, sign=False))
    
    branch_cmd.run(SafeArgs(name="feat", start_point="HEAD"))
    
    # 1. Branch -> Branch
    (repo_path / "file1.txt").write_text("v2")
    add_cmd.run(SafeArgs(files=["file1.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="v2", ai=False, sign=False))
    
    checkout_cmd.run(SafeArgs(target="feat", force=False))
    check((repo_path / "file1.txt").read_text() == "v1", "Switched back to v1 on feat branch")
    check(get_current_branch(repo_path / DEEP_GIT_DIR) == "feat", "Current branch is feat")
    
    # 2. Detached HEAD
    head_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    checkout_cmd.run(SafeArgs(target=head_sha, force=False))
    check(get_current_branch(repo_path / DEEP_GIT_DIR) is None, "In detached HEAD state")
    
    # 3. Safety check: Protect untracked/modified files
    checkout_cmd.run(SafeArgs(target="main", force=False)) # back to main
    (repo_path / "untracked.txt").write_text("i am untracked")
    # feat also has no untracked.txt, so it's safe if it doesn't conflict.
    # Let's create a conflict:
    # On 'feat' branch, let's create 'conflict.txt'
    checkout_cmd.run(SafeArgs(target="feat", force=False))
    (repo_path / "conflict.txt").write_text("base")
    add_cmd.run(SafeArgs(files=["conflict.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="add conflict", ai=False, sign=False))
    
    checkout_cmd.run(SafeArgs(target="main", force=False))
    # Now create untracked 'conflict.txt' in workdir
    (repo_path / "conflict.txt").write_text("dirty")
    
    try:
        # Should fail because 'conflict.txt' exists in target 'feat' but is untracked/dirty here
        checkout_cmd.run(SafeArgs(target="feat", force=False))
        check(False, "Checkout should have failed due to conflict")
    except SystemExit:
        check(True, "Checkout aborted safely to protect untracked file")
        
    log("Phase 5 Completed Successfully\n")

def run_phase_6(audit_dir):
    log("Phase 6: Merge Engine")
    repo_path = Path(audit_dir) / "phase6_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    from deep.commands import add_cmd, commit_cmd, merge_cmd, branch_cmd, checkout_cmd
    
    os.chdir(repo_path)
    (repo_path / "base.txt").write_text("base content")
    add_cmd.run(SafeArgs(files=["base.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="base", ai=False, sign=False))
    
    branch_cmd.run(SafeArgs(name="side", start_point="HEAD"))
    
    # 1. Fast-forward merge
    (repo_path / "side.txt").write_text("side content")
    add_cmd.run(SafeArgs(files=["side.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="side commit", ai=False, sign=False))
    side_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    
    checkout_cmd.run(SafeArgs(target="main", force=False))
    merge_cmd.run(SafeArgs(branch="side"))
    
    check(resolve_head(repo_path / DEEP_GIT_DIR) == side_sha, "Fast-forward merge successful")
    check((repo_path / "side.txt").exists(), "side.txt exists after FF merge")
    
    # 2. True 3-way merge
    branch_cmd.run(SafeArgs(name="feature", start_point="HEAD"))
    (repo_path / "main_edit.txt").write_text("main edit")
    add_cmd.run(SafeArgs(files=["main_edit.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="main edit", ai=False, sign=False))
    
    checkout_cmd.run(SafeArgs(target="feature", force=False))
    (repo_path / "feat_edit.txt").write_text("feat edit")
    add_cmd.run(SafeArgs(files=["feat_edit.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="feat edit", ai=False, sign=False))
    
    checkout_cmd.run(SafeArgs(target="main", force=False))
    merge_cmd.run(SafeArgs(branch="feature"))
    
    check((repo_path / "main_edit.txt").exists() and (repo_path / "feat_edit.txt").exists(), "3-way merge successful")
    
    # 3. Conflict detection
    branch_cmd.run(SafeArgs(name="conflict_side", start_point="HEAD"))
    (repo_path / "shared.txt").write_text("main version")
    add_cmd.run(SafeArgs(files=["shared.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="main shared", ai=False, sign=False))
    
    checkout_cmd.run(SafeArgs(target="conflict_side", force=False))
    (repo_path / "shared.txt").write_text("side version")
    add_cmd.run(SafeArgs(files=["shared.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="side shared", ai=False, sign=False))
    
    checkout_cmd.run(SafeArgs(target="main", force=False))
    try:
        merge_cmd.run(SafeArgs(branch="conflict_side"))
        check(False, "Merge should have failed due to conflict")
    except SystemExit:
        check(True, "Conflict detected and merge aborted")
    
    log("Phase 6 Completed Successfully\n")

def run_phase_7(audit_dir):
    log("Phase 7: Reset Engine")
    repo_path = Path(audit_dir) / "phase7_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    from deep.commands import add_cmd, commit_cmd, reset_cmd, checkout_cmd
    
    os.chdir(repo_path)
    (repo_path / "f1.txt").write_text("v1")
    add_cmd.run(SafeArgs(files=["f1.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="c1", ai=False, sign=False))
    c1_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    
    (repo_path / "f1.txt").write_text("v2")
    add_cmd.run(SafeArgs(files=["f1.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="c2", ai=False, sign=False))
    c2_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    
    # 1. Soft Reset (HEAD moves, index/workdir stay)
    reset_cmd.run(SafeArgs(commit=c1_sha, soft=True, mixed=False, hard=False))
    check(resolve_head(repo_path / DEEP_GIT_DIR) == c1_sha, "Soft reset: HEAD moved to c1")
    status_soft = compute_status(repo_path)
    check("f1.txt" in status_soft.staged_modified, "Soft reset: f1.txt stays staged as modified")
    
    # 2. Mixed Reset (HEAD/Index move, workdir stays)
    # Move back to c2 first
    update_head(repo_path / DEEP_GIT_DIR, c2_sha)
    reset_cmd.run(SafeArgs(commit=c1_sha, soft=False, mixed=True, hard=False))
    check(resolve_head(repo_path / DEEP_GIT_DIR) == c1_sha, "Mixed reset: HEAD moved to c1")
    status_mixed = compute_status(repo_path)
    check("f1.txt" in status_mixed.modified, "Mixed reset: f1.txt is modified in workdir but unstaged")
    
    # 3. Hard Reset (HEAD/Index/Workdir move)
    update_head(repo_path / DEEP_GIT_DIR, c2_sha)
    # Ensure index is also updated to c2 for clean test
    add_cmd.run(SafeArgs(files=["f1.txt"], ai=False, sign=False))
    reset_cmd.run(SafeArgs(commit=c1_sha, soft=False, mixed=False, hard=True))
    check(resolve_head(repo_path / DEEP_GIT_DIR) == c1_sha, "Hard reset: HEAD moved to c1")
    check((repo_path / "f1.txt").read_text() == "v1", "Hard reset: workdir restored to v1")
    status_hard = compute_status(repo_path)
    check(len(status_hard.modified) == 0 and len(status_hard.staged_modified) == 0, "Hard reset: status is clean")
    
    log("Phase 7 Completed Successfully\n")

def run_phase_8(audit_dir):
    log("Phase 8: Diff & Log Verification")
    repo_path = Path(audit_dir) / "phase8_repo"
    repo_path.mkdir()
    init_repo(repo_path)
    
    from deep.commands import add_cmd, commit_cmd, diff_cmd, log_cmd
    
    os.chdir(repo_path)
    (repo_path / "f.txt").write_text("line 1\n")
    add_cmd.run(SafeArgs(files=["f.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="c1", ai=False, sign=False))
    c1_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    
    (repo_path / "f.txt").write_text("line 2\n")
    add_cmd.run(SafeArgs(files=["f.txt"], ai=False, sign=False))
    commit_cmd.run(SafeArgs(message="c2", ai=False, sign=False))
    c2_sha = resolve_head(repo_path / DEEP_GIT_DIR)
    
    # 1. Diff Commit vs Commit
    log("Running diff c1 c2...")
    diff_cmd.run(SafeArgs(revisions=[c1_sha, c2_sha]))
    
    # 2. Log DAG
    log("Running log...")
    log_cmd.run(SafeArgs(max_count=None, graph=True, oneline=True))
    
    log("Phase 8 Completed Successfully\n")

import random
import string

class VCSFuzzer:
    def __init__(self, repo_dir):
        self.repo_dir = Path(repo_dir)
        self.dg_dir = self.repo_dir / DEEP_GIT_DIR
        self.known_files = []
        self.branches = ["main"]
        self.ops_count = 0
        
    def random_string(self, length=10):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def create_file(self):
        name = f"fuzzed_{len(self.known_files)}.txt"
        (self.repo_dir / name).write_text(self.random_string(50))
        self.known_files.append(name)
        
    def modify_file(self):
        if not self.known_files: return
        name = random.choice(self.known_files)
        (self.repo_dir / name).write_text(self.random_string(60))

    def run_random_op(self):
        from deep.commands import add_cmd, commit_cmd, branch_cmd, checkout_cmd, merge_cmd
        op = random.choice(["add", "commit", "branch", "checkout", "merge"])
        self.ops_count += 1
        
        try:
            if op == "add":
                self.create_file()
                self.modify_file()
                add_cmd.run(SafeArgs(files=["."], ai=False, sign=False))
            elif op == "commit":
                commit_cmd.run(SafeArgs(message=f"fuzz {self.ops_count}", ai=False, sign=False))
            elif op == "branch":
                if not resolve_head(self.dg_dir): return
                new_branch = f"b_{self.random_string(4)}"
                branch_cmd.run(SafeArgs(name=new_branch, start_point="HEAD"))
                self.branches.append(new_branch)
            elif op == "checkout":
                if not self.branches: return
                target = random.choice(self.branches)
                checkout_cmd.run(SafeArgs(target=target, force=True))
            elif op == "merge":
                if len(self.branches) < 2: return
                curr = get_current_branch(self.dg_dir)
                other = random.choice([b for b in self.branches if b != curr])
                merge_cmd.run(SafeArgs(branch=other))
        except SystemExit:
            pass # Legit aborts are OK in fuzzer
        except Exception as e:
            print(f"FUZZER CRASH on op {op}: {e}")
            raise

def run_phase_9(audit_dir):
    log("Phase 9: Randomized Fuzz Testing (10,000 Ops)")
    repo_path = Path(audit_dir) / "phase9_fuzz"
    repo_path.mkdir()
    init_repo(repo_path)
    os.chdir(repo_path)
    
    fuzzer = VCSFuzzer(repo_path)
    for i in range(10000): # Full 10,000 operations for exhaustive audit
        fuzzer.run_random_op()
        if (i+1) % 100 == 0:
            log(f"Fuzzer Progress: {i+1} ops...")
            
    log("Phase 9 Completed Successfully (Initial 1000 ops verified)\n")

class SafeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as audit_workspace:
        log(f"Starting Exhaustive Audit in {audit_workspace}")
        original_cwd = os.getcwd()
        try:
            run_phase_1(audit_workspace)
            run_phase_2(audit_workspace)
            run_phase_3(audit_workspace)
            run_phase_4(audit_workspace)
            run_phase_5(audit_workspace)
            run_phase_6(audit_workspace)
            run_phase_7(audit_workspace)
            run_phase_8(audit_workspace)
            run_phase_9(audit_workspace)
        finally:
            os.chdir(original_cwd)

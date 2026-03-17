import os
import random
import shutil
import string
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.append(os.path.abspath("src"))

from deep.core.repository import init_repo, find_repo,DEEP_DIR
from deep.commands import (
    add_cmd, commit_cmd, checkout_cmd, merge_cmd, 
    reset_cmd, branch_cmd, status_cmd, rm_cmd, mv_cmd,
    diff_cmd, log_cmd
)
from deep.core.refs import resolve_head, list_branches, get_current_branch

class SafeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class FuzzStats:
    def __init__(self):
        self.ops = 0
        self.errors = 0
        self.fixes = 0

class VCSFuzzer:
    def __init__(self, repo_dir):
        self.repo_dir = Path(repo_dir)
        self.dg_dir = self.repo_dir / DEEP_DIR
        self.stats = FuzzStats()
        self.known_files = []
        self.branches = []

    def random_string(self, length=10):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def create_file(self):
        name = f"file_{len(self.known_files)}_{self.random_string(5)}.txt"
        path = self.repo_dir / name
        path.write_text(self.random_string(100))
        self.known_files.append(name)
        return name

    def modify_file(self):
        if not self.known_files: return
        name = random.choice(self.known_files)
        path = self.repo_dir / name
        if path.exists():
            path.write_text(self.random_string(100) + "\nModified")

    def run_op(self):
        ops = [
            self.op_add, self.op_commit, self.op_branch, 
            self.op_checkout, self.op_merge, self.op_reset,
            self.op_mv, self.op_rm, self.op_modify, self.op_status,
            self.op_diff, self.op_log
        ]
        op = random.choice(ops)
        try:
            op()
            self.stats.ops += 1
            if self.stats.ops % 500 == 0:
                self.verify_integrity()
        except (Exception, SystemExit) as e:
            if isinstance(e, SystemExit) and e.code == 0:
                self.stats.ops += 1
            else:
                self.stats.errors += 1
                # print(f"ERROR in {op.__name__}: {e}")

    def op_add(self):
        self.create_file()
        add_cmd.run(SafeArgs(files=["."], ai=False, sign=False))

    def op_commit(self):
        commit_cmd.run(SafeArgs(message=f"fuzz commit {self.stats.ops}", ai=False, sign=False))
        if not self.branches:
            curr = get_current_branch(self.dg_dir)
            if curr: self.branches.append(curr)

    def op_branch(self):
        if not resolve_head(self.dg_dir): return
        name = f"branch_{len(self.branches)}_{self.random_string(3)}"
        branch_cmd.run(SafeArgs(name=name, start_point="HEAD"))
        self.branches.append(name)

    def op_checkout(self):
        if not self.branches: return
        target = random.choice(self.branches)
        try:
            checkout_cmd.run(SafeArgs(target=target, force=False))
        except SystemExit:
            pass

    def op_merge(self):
        if len(self.branches) < 2: return
        current = get_current_branch(self.dg_dir)
        others = [b for b in self.branches if b != current]
        if not others: return
        target = random.choice(others)
        try:
            merge_cmd.run(SafeArgs(branch=target))
        except SystemExit:
            pass

    def op_reset(self):
        head = resolve_head(self.dg_dir)
        if not head: return
        mode = random.choice(["soft", "mixed", "hard"])
        try:
            reset_cmd.run(SafeArgs(
                commit=head,
                soft=(mode == "soft"),
                mixed=(mode == "mixed"),
                hard=(mode == "hard")
            ))
        except SystemExit:
            pass

    def op_mv(self):
        if not self.known_files: return
        src = random.choice(self.known_files)
        if not (self.repo_dir / src).exists(): return
        dest = f"moved_{src}_{self.random_string(3)}"
        try:
            mv_cmd.run(SafeArgs(source=src, destination=dest))
            if (self.repo_dir / dest).exists() and not (self.repo_dir / src).exists():
                self.known_files.remove(src)
                self.known_files.append(dest)
        except SystemExit:
            pass

    def op_rm(self):
        if not self.known_files: return
        name = random.choice(self.known_files)
        if not (self.repo_dir / name).exists(): return
        try:
            rm_cmd.run(SafeArgs(files=[name]))
            if not (self.repo_dir / name).exists():
                self.known_files.remove(name)
        except SystemExit:
            pass

    def op_modify(self):
        self.modify_file()

    def op_status(self):
        status_cmd.run(SafeArgs(porcelain=True))

    def op_diff(self):
        if len(self.branches) < 2: return
        rev1 = random.choice(self.branches)
        rev2 = random.choice(self.branches)
        diff_cmd.run(SafeArgs(revisions=[rev1, rev2]))

    def op_log(self):
        log_cmd.run(SafeArgs(max_count=10, graph=True, oneline=True))

    def verify_integrity(self):
        from deep.storage.objects import read_object, Commit
        head = resolve_head(self.dg_dir)
        if head:
            try:
                obj = read_object(self.dg_dir / "objects", head)
                assert isinstance(obj, Commit)
            except Exception as e:
                print(f"INTEGRITY ERROR at {head[:7]}: {e}")
                self.stats.errors += 1

def main():
    iterations = 100000 
    if len(sys.argv) > 1:
        iterations = int(sys.argv[1])
        
    original_cwd = os.getcwd()
    tmpdir = tempfile.mkdtemp(prefix="deep_fuzz_")
    try:
        print(f"Starting Exhaustive Fuzzer for {iterations} ops...")
        os.chdir(tmpdir)
        init_repo(tmpdir)
        fuzzer = VCSFuzzer(tmpdir)
        
        for i in range(iterations):
            fuzzer.run_op()
            if (i+1) % 500 == 0:
                print(f"Progress: {i+1}/{iterations} ops. Errors: {fuzzer.stats.errors}")
                
        print("\nExhaustive Fuzz Audit Completed.")
        print(f"Total Ops: {fuzzer.stats.ops}")
        print(f"Errors Encountered: {fuzzer.stats.errors}")
    finally:
        os.chdir(original_cwd)
        import stat
        def on_rm_error(func, p, exc_info):
            os.chmod(p, stat.S_IWRITE)
            func(p)
        shutil.rmtree(tmpdir, onerror=on_rm_error)

if __name__ == "__main__":
    main()

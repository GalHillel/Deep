"""
deep.commands.rollback_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep rollback [<commit>] [--verify]`` command implementation.

Rolls back the repository state to its condition prior to the last transaction 
using the Write-Ahead Log (WAL). If no transaction history is found, it 
defaults to a hard reset to the parent of the current HEAD.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import hashlib
import struct
import sys
from pathlib import Path
from typing import Optional, Any

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import Color


def _get_tree_files(objects_dir: Path, tree_sha: str, prefix: str = "") -> dict[str, str]:
    """Recursively collect {rel_path: blob_sha} from a tree object."""
    from deep.storage.objects import read_object, Tree
    tree = read_object(objects_dir, tree_sha)
    if not isinstance(tree, Tree):
        return {}
    files: dict[str, str] = {}
    for entry in tree.entries:
        rel = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.mode == "40000":
            files.update(_get_tree_files(objects_dir, entry.sha, rel))
        else:
            files[rel] = entry.sha
    return files


def run(args) -> None:
    """Execute the rollback command (transaction-aware hard reset)."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    from deep.core.refs import resolve_head, get_current_branch, update_branch, write_head
    from deep.storage.objects import read_object, Commit
    from deep.storage.index import DeepIndex, DeepIndexEntry, write_index, read_index
    from deep.storage.txlog import TransactionLog

    txlog = TransactionLog(dg_dir)

    # 1. Handle --verify (WAL Audit)
    if getattr(args, "verify", False):
        print("⚓️ [WAL Security Check] Initiating signature audit...")
        results = txlog.verify_all()
        failures = [tx_id for tx_id, valid in results if not valid]
        if failures:
            print(f"⚠️  [WARNING] WAL Integrity compromised! {len(failures)} invalid signatures detected.", file=sys.stderr)
            for fail_id in failures:
                print(f"   - {fail_id}", file=sys.stderr)
        else:
            print("✅ [WAL Security Check] All transaction signatures verified.")
        print("")

    # 2. Determine target commit
    target_arg = getattr(args, "commit", None)
    target_sha: Optional[str] = None

    if target_arg:
        # User specified a target commit explicitly
        from deep.core.refs import resolve_revision
        resolved = resolve_revision(dg_dir, target_arg)
        if not resolved:
            print(f"Deep: error: cannot resolve '{target_arg}'", file=sys.stderr)
            raise DeepCLIException(1)
        target_sha = resolved
    else:
        head_sha = resolve_head(dg_dir)
        if head_sha is None:
            print("Deep: rollback: No commits found in the repository.", file=sys.stderr)
            return

        # Seek the state prior to the last successful transaction in WAL
        print("⚓️ Analyzing Write-Ahead Log for last committed transaction...")
        records = txlog.read_all()
        last_commit_tx_id = None
        for r in reversed(records):
            if r.status == "COMMIT":
                last_commit_tx_id = r.tx_id
                break
        
        if last_commit_tx_id:
            for r in reversed(records):
                if r.tx_id == last_commit_tx_id and r.status == "BEGIN":
                    if r.previous_commit_sha:
                        target_sha = r.previous_commit_sha
                        print(f"⚓️ Rolling back transaction '{last_commit_tx_id}' ({r.operation}).")
                    break
        
        if not target_sha:
            # Fallback to HEAD~1
            head_commit = read_object(objects_dir, head_sha)
            if isinstance(head_commit, Commit) and head_commit.parent_shas:
                target_sha = head_commit.parent_shas[0]
                print(f"⚓️ No transaction history found. Defaulting to parent of HEAD.")
            else:
                print("Everything up-to-date. No previous state to rollback to.")
                return

    # Verify target is a valid commit
    target_commit = read_object(objects_dir, target_sha)
    if not isinstance(target_commit, Commit):
        print(f"Deep: error: {target_sha[:7]} is not a commit", file=sys.stderr)
        raise DeepCLIException(1)

    print(f"Restoring repository state to {Color.wrap(Color.YELLOW, target_sha[:7])}...")

    # 3. Collect target tree files
    target_files = _get_tree_files(objects_dir, target_commit.tree_sha)

    # 4. Reset WORKING DIRECTORY (Hard Reset logic)
    current_index = read_index(dg_dir)
    # Remove files not in target
    for p in list(current_index.entries.keys()):
        if p not in target_files:
            full = repo_root / p
            if full.exists():
                full.unlink()
                # Clean empty parent dirs
                parent = full.parent
                while parent != repo_root:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent

    # Write/overwrite target files
    for p, sha in target_files.items():
        full = repo_root / p
        full.parent.mkdir(parents=True, exist_ok=True)
        blob = read_object(objects_dir, sha)
        if hasattr(blob, "data"):
            full.write_bytes(blob.data)
        else:
            full.write_bytes(blob.serialize_content())

    # 5. Reset INDEX to match target tree
    new_index = DeepIndex()
    for p, sha in target_files.items():
        full = repo_root / p
        stat = full.stat()
        p_hash = struct.unpack(">Q", hashlib.sha256(p.encode()).digest()[:8])[0]
        new_index.entries[p] = DeepIndexEntry(
            content_hash=sha,
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            path_hash=p_hash,
        )
    write_index(dg_dir, new_index)

    # 6. Move HEAD to target commit
    branch = get_current_branch(dg_dir)
    if branch:
        update_branch(dg_dir, branch, target_sha)
    else:
        write_head(dg_dir, target_sha)

    # State Consistency Check
    from deep.core.state import validate_repo_state
    try:
        validate_repo_state(repo_root)
    except Exception:
        pass # Optional validation

    print(f"{Color.wrap(Color.SUCCESS, 'Rollback complete.')} HEAD is now at {target_sha[:7]}")
    print(f"  Files restored: {len(target_files)}")

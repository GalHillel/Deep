"""
deep.commands.reset_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``reset [--hard|--soft] <commit>`` command implementation.

Moves HEAD (and the current branch) to the specified commit.
With ``--hard``, also resets the index and working directory.
Uses WAL-based crash recovery and proper locking.
"""

from __future__ import annotations

import os
import sys
import hashlib
from pathlib import Path

from deep.storage.index import (
    DeepIndex,
    DeepIndexEntry,
    read_index,
    read_index_no_lock,
    write_index,
    write_index_no_lock,
)
from deep.storage.objects import Blob, Commit, Tree, read_object
from deep.core.refs import get_current_branch, update_branch, update_head, resolve_revision
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo


def _get_tree_files(objects_dir: Path, tree_sha: str, prefix: str = "") -> dict[str, str]:
    """Recursively collect all {rel_path: sha} from a tree."""
    files = {}
    obj = read_object(objects_dir, tree_sha)
    if not isinstance(obj, Tree):
        return {}
    for entry in obj.entries:
        rel_path = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.mode == "40000":
            files.update(_get_tree_files(objects_dir, entry.sha, rel_path))
        else:
            files[rel_path] = entry.sha
    return files


def run(args) -> None:  # type: ignore[no-untyped_def]
    """Execute the ``reset`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    raw_target = args.commit

    # Modes: default is --mixed if neither --soft nor --hard is provided.
    mode = "mixed"
    if getattr(args, "soft", False):
        mode = "soft"
    elif getattr(args, "hard", False):
        mode = "hard"

    target_sha = resolve_revision(dg_dir, raw_target)
    if not target_sha:
        print(f"Deep: error: commit '{raw_target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        commit_obj = read_object(objects_dir, target_sha)
    except (ValueError, FileNotFoundError):
        print(f"Deep: error: commit {target_sha} not found.", file=sys.stderr)
        sys.exit(1)
    if not isinstance(commit_obj, Commit):
        print(f"Deep: error: '{target_sha}' is not a commit.", file=sys.stderr)
        sys.exit(1)

    target_files = _get_tree_files(objects_dir, commit_obj.tree_sha)

    # Acquire locks for reset
    from deep.core.locks import RepositoryLock
    repo_lock = RepositoryLock(dg_dir)
    try:
        repo_lock.acquire()
    except TimeoutError as e:
        print(f"Deep: error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        from deep.storage.txlog import TransactionLog
        txlog = TransactionLog(dg_dir)
        previous_head = resolve_revision(dg_dir, "HEAD")
        branch = get_current_branch(dg_dir)

        tx_id = txlog.begin(
            operation=f"reset-{mode}",
            details=f"reset {mode} to {raw_target}",
            target_object_id=target_sha,
            branch_ref=f"refs/heads/{branch}" if branch else "HEAD",
            previous_commit_sha=previous_head or "",
        )

        try:
            if mode == "hard":
                # 1. Clear current items in index from workdir
                current_index = read_index_no_lock(dg_dir)
                for p in current_index.entries:
                    full = repo_root / p
                    if full.exists():
                        full.unlink()
                        parent = full.parent
                        while parent != repo_root:
                            try:
                                parent.rmdir()
                            except OSError:
                                break
                            parent = parent.parent

                # 2. Restore target tree to workdir and build new index
                new_index = DeepIndex()
                for p, sha in target_files.items():
                    full = repo_root / p
                    full.parent.mkdir(parents=True, exist_ok=True)
                    full.write_bytes(read_object(objects_dir, sha).serialize_content())
                    stat = full.stat()
                    new_index.entries[p] = DeepIndexEntry(
                        content_hash=sha, 
                        mtime_ns=int(stat.st_mtime * 1e9),
                        size=stat.st_size, 
                        path_hash=int(hashlib.sha256(p.encode()).hexdigest()[:16], 16)
                    )
                write_index_no_lock(dg_dir, new_index)
                print(f"Deep: HEAD is now at {target_sha[:7]} (hard reset)")

            elif mode == "mixed":
                new_index = DeepIndex()
                for p, sha in target_files.items():
                    new_index.entries[p] = DeepIndexEntry(
                        content_hash=sha, 
                        mtime_ns=0,
                        size=0, 
                        path_hash=int(hashlib.sha256(p.encode()).hexdigest()[:16], 16)
                    )
                write_index_no_lock(dg_dir, new_index)
                print(f"Deep: HEAD is now at {target_sha[:7]} (mixed reset)")

            else:  # soft
                print(f"Deep: HEAD is now at {target_sha[:7]} (soft reset)")

            # Crash hook
            if os.environ.get("DEEP_CRASH_TEST") == "RESET_BEFORE_REF_UPDATE":
                raise BaseException("Deep: simulated crash before ref update")

            # Update HEAD/Branch
            if branch:
                update_branch(dg_dir, branch, target_sha)
            else:
                update_head(dg_dir, target_sha)

            txlog.commit(tx_id)
        except Exception as e:
            txlog.rollback(tx_id, str(e))
            raise

    finally:
        repo_lock.release()

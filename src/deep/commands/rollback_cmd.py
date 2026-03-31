"""
deep.commands.rollback_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep rollback [<commit>]`` command implementation.

Hard-reset rollback: moves HEAD, resets INDEX, and resets WORKING DIRECTORY
to match the target commit. Default target is HEAD~1 (parent of current HEAD).
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import hashlib
import struct
import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'rollback' command parser."""
    p_rollback = subparsers.add_parser(
        "rollback",
        help="Undo the last repository transaction",
        description="""Roll back the repository state (HEAD, index, and working tree) to a previous commit or transaction.

This command is a powerful safety net for undoing accidental merges, deletions, or corrupting operations.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
\033[1m  QUICK UNDO:\033[0m
  \033[1;34m⚓️ deep rollback\033[0m
     Undo the most recent command (reset to HEAD~1)

\033[1m  TARGETED RESTORATION:\033[0m
  \033[1;34m⚓️ deep rollback abc1234\033[0m
     Reset exactly to the specified commit SHA
  \033[1;34m⚓️ deep rollback --force\033[0m
     Force rollback even with uncommitted changes
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_rollback.add_argument("commit", nargs="?", default="HEAD~1", help="The commit identifier to rollback to (default: HEAD~1)")
    p_rollback.add_argument("--force", action="store_true", help="Force rollback even if the working tree is dirty")


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
    """Execute the rollback command (hard reset to target commit)."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    from deep.core.refs import resolve_head, get_current_branch, update_branch, write_head
    from deep.storage.objects import read_object, Commit
    from deep.storage.index import DeepIndex, DeepIndexEntry, write_index

    # 1. Determine target commit
    target_arg = getattr(args, "commit", None)
    head_sha = resolve_head(dg_dir)

    if head_sha is None:
        print("Deep: error: no commits to rollback to", file=sys.stderr)
        raise DeepCLIException(1)

    if target_arg and target_arg != "HEAD~1":
        # Try to resolve as a revision
        from deep.core.refs import resolve_revision
        resolved = resolve_revision(dg_dir, target_arg)
        if not resolved:
            print(f"Deep: error: cannot resolve '{target_arg}'", file=sys.stderr)
            raise DeepCLIException(1)
        target_sha = resolved
    else:
        head_commit = read_object(objects_dir, head_sha)
        if not isinstance(head_commit, Commit) or not head_commit.parent_shas:
            print("Everything up-to-date. No previous commit to rollback to.")
            return
        target_sha = head_commit.parent_shas[0]

    # Verify target is a valid commit
    target_commit = read_object(objects_dir, target_sha)
    if not isinstance(target_commit, Commit):
        print(f"Deep: error: {target_sha[:7]} is not a commit", file=sys.stderr)
        raise DeepCLIException(1)

    print(f"Rolling back to {Color.wrap(Color.YELLOW, target_sha[:7])}: {target_commit.message.split(chr(10))[0]}")

    # 2. Collect target tree files
    target_files = _get_tree_files(objects_dir, target_commit.tree_sha)

    # 3. Reset WORKING DIRECTORY
    # Remove files not in target
    from deep.storage.index import read_index
    current_index = read_index(dg_dir)
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

    # Write target files to working directory
    for p, sha in target_files.items():
        full = repo_root / p
        full.parent.mkdir(parents=True, exist_ok=True)
        blob = read_object(objects_dir, sha)
        if hasattr(blob, "data"):
            full.write_bytes(blob.data)
        else:
            full.write_bytes(blob.serialize_content())

    # 4. Reset INDEX to match target tree
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

    # 5. Move HEAD to target commit
    branch = get_current_branch(dg_dir)
    if branch:
        update_branch(dg_dir, branch, target_sha)
    else:
        write_head(dg_dir, target_sha)

    from deep.core.state import validate_repo_state
    validate_repo_state(repo_root)

    print(f"{Color.wrap(Color.SUCCESS, 'Rollback complete.')} HEAD is now at {target_sha[:7]}")
    print(f"  Files restored: {len(target_files)}")

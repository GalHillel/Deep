"""
deep_git.commands.commit_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git commit -m <msg>`` command implementation.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from deep_git.core.index import read_index
from deep_git.core.objects import Blob, Commit, Tree, TreeEntry
from deep_git.core.refs import get_current_branch, resolve_head, update_branch
from deep_git.core.repository import DEEP_GIT_DIR, find_repo


def _build_tree_from_index(dg_dir: Path) -> str:
    """Read the index and build a flat Tree object, returning its SHA."""
    index = read_index(dg_dir)
    if not index.entries:
        print("Error: nothing to commit (empty index)", file=sys.stderr)
        sys.exit(1)

    objects_dir = dg_dir / "objects"
    entries = []
    for rel_path, entry in sorted(index.entries.items()):
        # Use only the basename for the tree entry name
        # (flat tree — no nested directories for now).
        name = rel_path.replace("/", "_") if "/" in rel_path else rel_path
        entries.append(TreeEntry(mode="100644", name=name, sha=entry.sha))

    tree = Tree(entries=entries)
    return tree.write(objects_dir)


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``commit`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"

    tree_sha = _build_tree_from_index(dg_dir)

    parent_sha = resolve_head(dg_dir)
    parent_shas = [parent_sha] if parent_sha else []

    commit = Commit(
        tree_sha=tree_sha,
        parent_shas=parent_shas,
        message=args.message,
        timestamp=int(time.time()),
    )
    commit_sha = commit.write(objects_dir)

    # Update the branch ref.
    branch = get_current_branch(dg_dir)
    if branch:
        update_branch(dg_dir, branch, commit_sha)
    else:
        # Detached HEAD — just update HEAD directly.
        from deep_git.core.refs import update_head
        update_head(dg_dir, commit_sha)

    short = commit_sha[:7]
    print(f"[{branch or 'detached HEAD'} {short}] {args.message}")

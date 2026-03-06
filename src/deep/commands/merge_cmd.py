"""
deep.commands.merge_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep merge <branch>`` command implementation.

Supports:
- "Already up to date" (LCA == target)
- Fast-forward merge (LCA == HEAD)
- Basic 3-way merge with conflict detection
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from deep.storage.index import Index, IndexEntry, read_index, write_index
from deep.core.merge import find_lca, three_way_merge
from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep.core.refs import (
    get_branch,
    get_current_branch,
    resolve_head,
    update_branch,
)
from deep.core.repository import DEEP_GIT_DIR, find_repo


def _restore_tree_to_workdir(
    repo_root: Path,
    objects_dir: Path,
    tree: Tree,
    index: Index,
    prefix: str = "",
) -> None:
    """Restore a tree's blobs into the working directory and update index."""
    for entry in tree.entries:
        rel_path = entry.name if not prefix else f"{prefix}/{entry.name}"
        obj = read_object(objects_dir, entry.sha)
        if isinstance(obj, Blob):
            file_path = repo_root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(obj.data)
            stat = file_path.stat()
            index.entries[rel_path] = IndexEntry(
                sha=entry.sha,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
        elif isinstance(obj, Tree):
            _restore_tree_to_workdir(repo_root, objects_dir, obj, index, prefix=rel_path)


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``merge`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    target_branch = args.branch

    from deep.storage.txlog import TransactionLog
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    # Resolve current HEAD.
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        print("Error: no commits on current branch.", file=sys.stderr)
        sys.exit(1)

    # Resolve target branch.
    from deep.core.refs import resolve_revision
    target_sha = resolve_revision(dg_dir, target_branch)
    if target_sha is None:
        print(f"Error: revision '{target_branch}' not found.", file=sys.stderr)
        sys.exit(1)

    if head_sha == target_sha:
        print("Already up to date.")
        return

    # Find LCA.
    lca_sha = find_lca(objects_dir, head_sha, target_sha)

    # Case 1: LCA == target → already up to date.
    if lca_sha == target_sha:
        print("Already up to date.")
        return

    tx_id = txlog.begin("merge", f"{target_branch} into HEAD")
    try:
        with Timer(telemetry, "merge"):
            # Case 2: LCA == HEAD → fast-forward.
            if lca_sha == head_sha:
                current_branch = get_current_branch(dg_dir)
                if current_branch:
                    update_branch(dg_dir, current_branch, target_sha)

                target_commit = read_object(objects_dir, target_sha)
                if isinstance(target_commit, Commit):
                    tree = read_object(objects_dir, target_commit.tree_sha)
                    if isinstance(tree, Tree):
                        for rel_path in read_index(dg_dir).entries:
                            full = repo_root / rel_path
                            if full.exists():
                                full.unlink()
                        new_index = Index()
                        _restore_tree_to_workdir(repo_root, objects_dir, tree, new_index)
                        write_index(dg_dir, new_index)

                txlog.commit(tx_id)
                audit.record("local", "merge", ref=target_branch, sha=target_sha,
                             details=f"fast-forward {head_sha[:7]}..{target_sha[:7]}")
                print(f"Fast-forward merge: {head_sha[:7]}..{target_sha[:7]}")
                return

            # Case 3: True merge — 3-way.
            head_commit = read_object(objects_dir, head_sha)
            target_commit = read_object(objects_dir, target_sha)
            if not isinstance(head_commit, Commit) or not isinstance(target_commit, Commit):
                print("Error: could not read commits.", file=sys.stderr)
                sys.exit(1)

            lca_commit = read_object(objects_dir, lca_sha) if lca_sha else None
            base_tree_sha = lca_commit.tree_sha if isinstance(lca_commit, Commit) else None

            merged_entries, conflicts = three_way_merge(
                objects_dir, base_tree_sha, head_commit.tree_sha, target_commit.tree_sha,
            )

            if conflicts:
                txlog.rollback(tx_id, f"conflicts: {conflicts}")
                print(f"CONFLICT in: {', '.join(conflicts)}")
                print("Merge aborted. Please resolve conflicts manually.", file=sys.stderr)
                sys.exit(1)

            merged_tree = Tree(entries=merged_entries)
            merged_tree_sha = merged_tree.write(objects_dir)

            current_branch = get_current_branch(dg_dir)
            merge_commit = Commit(
                tree_sha=merged_tree_sha,
                parent_shas=[head_sha, target_sha],
                message=f"Merge branch '{target_branch}' into {current_branch or 'HEAD'}",
                timestamp=int(time.time()),
            )
            merge_commit_sha = merge_commit.write(objects_dir)

            if current_branch:
                update_branch(dg_dir, current_branch, merge_commit_sha)

            for rel_path in read_index(dg_dir).entries:
                full = repo_root / rel_path
                if full.exists():
                    full.unlink()
            new_index = Index()
            merged_tree_obj = read_object(objects_dir, merged_tree_sha)
            if isinstance(merged_tree_obj, Tree):
                _restore_tree_to_workdir(repo_root, objects_dir, merged_tree_obj, new_index)
            write_index(dg_dir, new_index)

        txlog.commit(tx_id)
        audit.record("local", "merge", ref=target_branch, sha=merge_commit_sha,
                     details=f"3-way merge")
        print(f"Merge made: {merge_commit_sha[:7]}")
    except SystemExit:
        raise
    except Exception as e:
        txlog.rollback(tx_id, str(e))
        raise


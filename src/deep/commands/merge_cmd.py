"""
deep.commands.merge_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
DeepBridge ``merge <branch>`` command implementation.

Supports:
- "Already up to date" (LCA == target)
- Fast-forward merge (LCA == HEAD)
- Basic 3-way merge with conflict detection
- WAL-based crash recovery and proper locking
"""

from __future__ import annotations

import os
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
from deep.core.config import Config
from deep.core.telemetry import TelemetryCollector, Timer
from deep.core.audit import AuditLog


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


def _get_tree_files(objects_dir: Path, tree_sha: str, prefix: str = "") -> dict[str, str]:
    """Recursively collect all {rel_path: sha} from a tree."""
    files = {}
    tree = read_object(objects_dir, tree_sha)
    if not isinstance(tree, Tree):
        return {}
    for entry in tree.entries:
        rel_path = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.mode == "40000":
            files.update(_get_tree_files(objects_dir, entry.sha, rel_path))
        else:
            files[rel_path] = entry.sha
    return files


def _apply_tree_to_workdir(
    repo_root: Path,
    objects_dir: Path,
    target_files: dict[str, str],
    current_index: Index,
) -> Index:
    """Apply a set of tree files to the working directory and return new index."""
    # Remove files in current index not in target
    for p in [p for p in current_index.entries if p not in target_files]:
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

    # Write target files
    new_index = Index()
    for p, sha in target_files.items():
        full = repo_root / p
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(read_object(objects_dir, sha).serialize_content())
        stat = full.stat()
        new_index.entries[p] = IndexEntry(sha=sha, size=stat.st_size, mtime=stat.st_mtime)
    return new_index


def run(args) -> None:  # type: ignore[no-untyped_def]
    """Execute the ``merge`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepBridge: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    target_branch = args.branch

    # Resolve current HEAD.
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        print("DeepBridge: error: no commits on current branch.", file=sys.stderr)
        sys.exit(1)

    # Resolve target branch.
    from deep.core.refs import resolve_revision
    target_sha = resolve_revision(dg_dir, target_branch)
    if target_sha is None:
        print(f"DeepBridge: error: revision '{target_branch}' not found.", file=sys.stderr)
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

    # Acquire locks for the merge operation
    from deep.core.locks import RepositoryLock
    repo_lock = RepositoryLock(dg_dir)
    try:
        repo_lock.acquire()
    except TimeoutError as e:
        print(f"DeepBridge: error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        from deep.storage.txlog import TransactionLog
        txlog = TransactionLog(dg_dir)
        telemetry = TelemetryCollector(dg_dir)
        audit = AuditLog(dg_dir)
        
        config = Config(repo_root)
        author_name = config.get("user.name", "DeepBridge User")
        
        with Timer(telemetry, "merge"):
            current_branch = get_current_branch(dg_dir)

            # Case 2: LCA == HEAD → fast-forward.
            if lca_sha == head_sha:
                tx_id = txlog.begin(
                    operation="merge",
                    details=f"fast-forward merge {target_branch}",
                    target_object_id=target_sha,
                    branch_ref=f"refs/heads/{current_branch}" if current_branch else "HEAD",
                    previous_commit_sha=head_sha,
                )
                try:
                    print(f"Updating {head_sha[:7]}..{target_sha[:7]}")
                    print("Fast-forward")

                    target_commit = read_object(objects_dir, target_sha)
                    target_files = _get_tree_files(objects_dir, target_commit.tree_sha)
                    current_index = read_index(dg_dir)

                    new_index = _apply_tree_to_workdir(repo_root, objects_dir, target_files, current_index)
                    write_index(dg_dir, new_index)

                    # Crash hook: after index update, before ref update
                    if os.environ.get("DEEP_CRASH_TEST") == "MERGE_FF_AFTER_INDEX_UPDATE":
                        raise BaseException("DeepBridge: simulated crash during FF merge (after index update)")

                    if current_branch:
                        update_branch(dg_dir, current_branch, target_sha)
                    else:
                        from deep.core.refs import update_head
                        update_head(dg_dir, target_sha)

                    txlog.commit(tx_id)
                    audit.record(author_name, "merge", ref=current_branch or "HEAD", details=f"FF merged {target_branch}")
                except Exception as e:
                    txlog.rollback(tx_id, str(e))
                    raise
                return

            # Case 3: True merge — 3-way.
            head_commit = read_object(objects_dir, head_sha)
            target_commit = read_object(objects_dir, target_sha)
            lca_commit = read_object(objects_dir, lca_sha) if lca_sha else None
            base_tree_sha = lca_commit.tree_sha if isinstance(lca_commit, Commit) else None

            merged_entries, conflicts = three_way_merge(
                objects_dir, base_tree_sha, head_commit.tree_sha, target_commit.tree_sha,
            )

            if conflicts:
                print(f"DeepBridge: CONFLICT in: {', '.join(conflicts)}", file=sys.stderr)
                # Write conflict markers to working directory
                for conflict_name in conflicts:
                    _write_conflict_markers(repo_root, objects_dir, conflict_name,
                                            head_commit.tree_sha, target_commit.tree_sha, base_tree_sha)
                print("DeepBridge: fix conflicts and then run 'deep commit'.", file=sys.stderr)
                sys.exit(1)

            merged_tree = Tree(entries=merged_entries)
            merged_tree_sha = merged_tree.write(objects_dir)

            merge_commit = Commit(
                tree_sha=merged_tree_sha,
                parent_shas=[head_sha, target_sha],
                message=f"Merge branch '{target_branch}' into {current_branch or 'HEAD'}",
                timestamp=int(time.time()),
            )

            merge_commit_sha = merge_commit.write(objects_dir)

            tx_id = txlog.begin(
                operation="merge",
                details=f"3-way merge {target_branch}",
                target_object_id=merge_commit_sha,
                branch_ref=f"refs/heads/{current_branch}" if current_branch else "HEAD",
                previous_commit_sha=head_sha,
            )

            try:
                # Crash hook
                if os.environ.get("DEEP_CRASH_TEST") == "MERGE_BEFORE_REF_UPDATE":
                    raise BaseException("DeepBridge: simulated crash before ref update")

                target_files = _get_tree_files(objects_dir, merged_tree_sha)
                current_index = read_index(dg_dir)
                new_index = _apply_tree_to_workdir(repo_root, objects_dir, target_files, current_index)
                write_index(dg_dir, new_index)

                if current_branch:
                    update_branch(dg_dir, current_branch, merge_commit_sha)
                else:
                    from deep.core.refs import update_head
                    update_head(dg_dir, merge_commit_sha)

                txlog.commit(tx_id)
                audit.record(author_name, "merge", ref=current_branch or "HEAD", details=f"merged {target_branch}")
            except Exception as e:
                txlog.rollback(tx_id, str(e))
                raise
    
            print(f"DeepBridge: merge made by 3-way merge: {merge_commit_sha[:7]}")

    finally:
        repo_lock.release()


def _write_conflict_markers(
    repo_root: Path,
    objects_dir: Path,
    name: str,
    ours_tree_sha: str,
    theirs_tree_sha: str,
    base_tree_sha: str | None,
) -> None:
    """Write conflict markers for a conflicting file into the working directory."""
    from deep.core.merge import _tree_entries_map_full

    ours_map = _tree_entries_map_full(objects_dir, ours_tree_sha)
    theirs_map = _tree_entries_map_full(objects_dir, theirs_tree_sha)
    base_map = _tree_entries_map_full(objects_dir, base_tree_sha) if base_tree_sha else {}

    def _get_content(entries_map: dict, file_name: str) -> str:
        entry = entries_map.get(file_name)
        if not entry:
            return ""
        try:
            obj = read_object(objects_dir, entry.sha)
            if isinstance(obj, Blob):
                return obj.data.decode("utf-8", errors="replace")
        except Exception:
            pass
        return ""

    ours_content = _get_content(ours_map, name)
    theirs_content = _get_content(theirs_map, name)

    conflict_content = (
        f"<<<<<<< HEAD\n"
        f"{ours_content}"
        f"=======\n"
        f"{theirs_content}"
        f">>>>>>> {name}\n"
    )

    file_path = repo_root / name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(conflict_content, encoding="utf-8")

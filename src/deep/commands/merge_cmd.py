"""
deep.commands.merge_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``merge <branch>`` command implementation.

Supports:
- "Already up to date" (LCA == target)
- Fast-forward merge (LCA == HEAD)
- Basic 3-way merge with conflict detection
- WAL-based crash recovery and proper locking
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import os
import sys
import time
import hashlib
from pathlib import Path

from deep.storage.index import DeepIndex, DeepIndexEntry, read_index, write_index, read_index_no_lock, write_index_no_lock
from deep.core.merge import find_lca, three_way_merge
from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep.core.refs import (
    get_branch,
    get_current_branch,
    resolve_head,
    update_branch,
)
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'merge' command parser."""
    p_merge = subparsers.add_parser(
        "merge",
        help="Join two or more development histories",
        description=format_description("Merge changes from the specified branch or commit into the current branch. Supports fast-forward and 3-way merges with automatic conflict detection."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep merge feature", "Merge the 'feature' branch into current branch")}
{format_example("deep merge main", "Bring 'main' branch changes into current branch")}
{format_example("deep merge --no-commit dev", "Merge 'dev' but don't automatically commit")}
{format_example("deep merge --abort", "Cancel a conflicted merge and restore previous state")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_merge.add_argument("branch", nargs="?", help="The branch name or commit SHA to merge into current branch")
    p_merge.add_argument("--abort", action="store_true", help="Abort the current conflicted merge and restore to pre-merge state")
    p_merge.add_argument("--no-commit", action="store_true", help="Perform the merge but do not automatically create a commit")
    p_merge.add_argument("--ff-only", action="store_true", help="Refuse to merge and exit with a non-zero status unless the merge is a fast-forward")
from deep.storage.transaction import TransactionManager
from deep.core.config import Config
from deep.core.telemetry import TelemetryCollector, Timer
from deep.core.audit import AuditLog
from deep.core.hooks import run_hook
from deep.core.state import validate_repo_state


def _restore_tree_to_workdir(
    repo_root: Path,
    objects_dir: Path,
    tree: Tree,
    index: DeepIndex,
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
            import struct
            index.entries[rel_path] = DeepIndexEntry(
                content_hash=entry.sha,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                path_hash=struct.unpack(">Q", hashlib.sha256(rel_path.encode()).digest()[:8])[0]
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
    current_index: DeepIndex,
) -> DeepIndex:
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
    new_index = DeepIndex()
    for p, sha in target_files.items():
        full = repo_root / p
        full.parent.mkdir(parents=True, exist_ok=True)
        obj = read_object(objects_dir, sha)
        if hasattr(obj, "data"):
            full.write_bytes(obj.data)
        else:
            full.write_bytes(obj.serialize_content())
        stat = full.stat()
        import struct
        new_index.entries[p] = DeepIndexEntry(
            content_hash=sha, 
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size, 
            path_hash=struct.unpack(">Q", hashlib.sha256(p.encode()).digest()[:8])[0]
        )
    return new_index


def run(args) -> None:  # type: ignore[no-untyped_def]
    """Execute the ``merge`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    target_branch = args.branch

    # Resolve current HEAD.
    head_sha = resolve_head(dg_dir)
    if head_sha is None:
        print("Deep: error: no commits on current branch.", file=sys.stderr)
        raise DeepCLIException(1)

    # Handle --abort
    if getattr(args, "abort", False):
        print("Aborting merge: resetting working directory and index to HEAD.")
        from deep.commands.reset_cmd import run as reset_run
        reset_args = type('Namespace', (), {'commit': 'HEAD', 'hard': True, 'soft': False})()
        reset_run(reset_args)
        return

    # 1. Dirty check (REQUIRED for safety)
    from deep.core.status import compute_status
    status = compute_status(repo_root)
    if status.staged_new or status.staged_modified or status.staged_deleted or status.modified or status.deleted:
        print("Deep: error: working directory not clean. Please commit or stash your changes.", file=sys.stderr)
        raise DeepCLIException(1)

    # 2. Resolve target branch.
    from deep.core.refs import resolve_revision
    target_sha = resolve_revision(dg_dir, target_branch)
    if target_sha is None:
        print(f"Deep: error: revision '{target_branch}' not found.", file=sys.stderr)
        raise DeepCLIException(1)

    if head_sha == target_sha:
        print("Already up to date.")
        return

    # 3. Find LCA.
    lca_sha = find_lca(objects_dir, head_sha, target_sha)
    if lca_sha == target_sha:
        print("Already up to date.")
        return

    with TransactionManager(dg_dir) as tm:
        telemetry = TelemetryCollector(dg_dir)
        audit = AuditLog(dg_dir)
        config = Config(repo_root)
        author_name = config.get("user.name", "Deep User")
        
        with Timer(telemetry, "merge"):
            current_branch = get_current_branch(dg_dir)

            # Case A: Fast-forward.
            if lca_sha == head_sha:
                tm.begin(
                    operation="merge",
                    details=f"fast-forward merge {target_branch}",
                    target_object_id=target_sha,
                    branch_ref=f"refs/heads/{current_branch}" if current_branch else "HEAD",
                    previous_commit_sha=head_sha,
                )
                print(f"Updating {head_sha[:7]}..{target_sha[:7]}")
                print("Fast-forward")

                target_commit = read_object(objects_dir, target_sha)
                target_files = _get_tree_files(objects_dir, target_commit.tree_sha)
                current_index = read_index_no_lock(dg_dir)

                new_index = _apply_tree_to_workdir(repo_root, objects_dir, target_files, current_index)
                write_index_no_lock(dg_dir, new_index)

                # Crash hook: before ref update
                if os.environ.get("DEEP_CRASH_TEST") == "MERGE_BEFORE_REF_UPDATE":
                    raise BaseException("Deep: simulated crash before ref update")

                if current_branch:
                    update_branch(dg_dir, current_branch, target_sha)
                else:
                    from deep.core.refs import update_head
                    update_head(dg_dir, target_sha)

                tm.commit()
                validate_repo_state(repo_root)
                audit.record(author_name, "merge", ref=current_branch or "HEAD", details=f"FF merged {target_branch}")
                run_hook(dg_dir, "post-merge", args=[target_sha])
                return

            # Case B: True merge — 3-way.
            head_commit = read_object(objects_dir, head_sha)
            target_commit = read_object(objects_dir, target_sha)
            lca_commit = read_object(objects_dir, lca_sha) if lca_sha else None
            base_tree_sha = lca_commit.tree_sha if isinstance(lca_commit, Commit) else None

            merged_tree_sha, conflicts = three_way_merge(
                objects_dir, base_tree_sha, head_commit.tree_sha, target_commit.tree_sha,
            )

            if conflicts:
                print(f"Deep: CONFLICT in: {', '.join(conflicts)}", file=sys.stderr)
                # Write conflict markers to working directory
                for conflict_name in conflicts:
                    _write_conflict_markers(repo_root, objects_dir, conflict_name,
                                            head_commit.tree_sha, target_commit.tree_sha, base_tree_sha)
                # Write MERGE_HEAD so commit creates a proper merge commit
                merge_head_path = dg_dir / "MERGE_HEAD"
                merge_head_path.write_text(target_sha + "\n", encoding="utf-8")
                print("Deep: fix conflicts and then run 'deep commit'.", file=sys.stderr)
                raise DeepCLIException(1)

            merge_commit = Commit(
                tree_sha=merged_tree_sha,
                parent_shas=[head_sha, target_sha],
                message=f"Merge branch '{target_branch}' into {current_branch or 'HEAD'}",
                timestamp=int(time.time()),
            )
            merge_commit_sha = merge_commit.write(objects_dir)

            tm.begin(
                operation="merge",
                details=f"3-way merge {target_branch}",
                target_object_id=merge_commit_sha,
                branch_ref=f"refs/heads/{current_branch}" if current_branch else "HEAD",
                previous_commit_sha=head_sha,
            )

            target_files = _get_tree_files(objects_dir, merged_tree_sha)
            current_index = read_index_no_lock(dg_dir)
            new_index = _apply_tree_to_workdir(repo_root, objects_dir, target_files, current_index)
            write_index_no_lock(dg_dir, new_index)

            # Crash hook: before ref update
            if os.environ.get("DEEP_CRASH_TEST") == "MERGE_BEFORE_REF_UPDATE":
                raise BaseException("Deep: simulated crash before ref update")

            if current_branch:
                update_branch(dg_dir, current_branch, merge_commit_sha)
            else:
                from deep.core.refs import update_head
                update_head(dg_dir, merge_commit_sha)

            tm.commit()
            validate_repo_state(repo_root)
            audit.record(author_name, "merge", ref=current_branch or "HEAD", details=f"merged {target_branch}")
            run_hook(dg_dir, "post-merge", args=[merge_commit_sha])
    
            print(f"Deep: merge made by 3-way merge: {merge_commit_sha[:7]}")


def _is_binary(data: bytes) -> bool:
    return b'\x00' in data

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

    def _get_raw_content(entries_map: dict, file_name: str) -> bytes | None:
        entry = entries_map.get(file_name)
        if not entry:
            return None
        try:
            obj = read_object(objects_dir, entry.sha)
            if isinstance(obj, Blob):
                return obj.data
        except Exception:
            pass
        return None

    ours_raw = _get_raw_content(ours_map, name)
    theirs_raw = _get_raw_content(theirs_map, name)

    if (ours_raw and _is_binary(ours_raw)) or (theirs_raw and _is_binary(theirs_raw)):
        print(f"Deep: error: cannot merge binary file {name}", file=sys.stderr)
        raise DeepCLIException(1)

    ours_content = ours_raw.decode("utf-8", errors="replace") if ours_raw else ""
    theirs_content = theirs_raw.decode("utf-8", errors="replace") if theirs_raw else ""

    conflict_content = (
        f"<<<<<<< OURS\n"
        f"{ours_content}"
        f"=======\n"
        f"{theirs_content}"
        f">>>>>>> THEIRS\n"
    )

    file_path = repo_root / name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(conflict_content, encoding="utf-8")

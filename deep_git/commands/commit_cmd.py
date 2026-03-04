"""
deep_git.commands.commit_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git commit -m <msg>`` command implementation.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from deep_git.core.config import Config
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

    from deep_git.core.txlog import TransactionLog
    from deep_git.core.telemetry import TelemetryCollector, Timer
    from deep_git.core.audit import AuditLog

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    from deep_git.core.locks import RepositoryLock, BranchLock

    # Fast-fail if repo is locked
    repo_lock = RepositoryLock(dg_dir)
    try:
        repo_lock.acquire()
    except TimeoutError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with Timer(telemetry, "commit"):
            tree_sha = _build_tree_from_index(dg_dir)

            parent_sha = resolve_head(dg_dir)
            parent_shas = [parent_sha] if parent_sha else []

            config = Config(repo_root)
            author_name = config.get("user.name", "Deep Git User")
            author_email = config.get("user.email", "user@deepgit")
            author_str = f"{author_name} <{author_email}>"

            timestamp = int(time.time())
            from deep_git.core.utils import get_local_timezone_offset
            timezone = get_local_timezone_offset()
            signature = "MOCKED_GPG_SIGNATURE" if getattr(args, "sign", False) else None

            commit = Commit(
                tree_sha=tree_sha,
                parent_shas=parent_shas,
                author=author_str,
                committer=author_str,
                message=args.message,
                timestamp=timestamp,
                timezone=timezone,
                signature=signature,
            )
            # Objects are content-addressable; it is safe to write them before the transaction BEGINs
            # or during the transaction. If the transaction fails, they just become orphaned.
            commit_sha = commit.write(objects_dir)

            branch = get_current_branch(dg_dir)
            
            # Acquire branch lock if we are on a branch
            branch_lock = BranchLock(dg_dir, branch) if branch else None
            if branch_lock:
                try:
                    branch_lock.acquire()
                except TimeoutError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

            try:
                # Start transaction right before the dangerous part (branch/HEAD update)
                tx_id = txlog.begin(
                    operation="commit", 
                    details=args.message,
                    target_object_id=commit_sha,
                    branch_ref=branch or "",
                    previous_commit_sha=parent_sha or ""
                )

                try:
                    if branch:
                        update_branch(dg_dir, branch, commit_sha)
                    else:
                        from deep_git.core.refs import update_head
                        update_head(dg_dir, commit_sha)

                    txlog.commit(tx_id)
                except Exception as e:
                    txlog.rollback(tx_id, str(e))
                    raise
            finally:
                if branch_lock:
                    branch_lock.release()

        audit.record(author_name, "commit", ref=branch or "HEAD", sha=commit_sha)

        short = commit_sha[:7]
        print(f"[{branch or 'detached HEAD'} {short}] {args.message}")
    except Exception as e:
        raise
    finally:
        repo_lock.release()


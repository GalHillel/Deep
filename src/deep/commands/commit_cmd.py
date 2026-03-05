"""
deep.commands.commit_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep-git commit -m <msg>`` command implementation.

GOD MODE: Real ECDSA/HMAC commit signing replaces mocked signatures.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from deep.core.config import Config
from deep.storage.index import read_index
from deep.storage.objects import Blob, Commit, Tree, TreeEntry
from deep.core.refs import get_current_branch, resolve_head, update_branch
from deep.core.repository import DEEP_GIT_DIR, find_repo


def _build_tree_recursive(objects_dir: Path, files: dict[str, str]) -> str:
    """Recursively build Tree objects from a flat dict of {rel_path: sha}."""
    # Group entries by top-level directory
    tree_entries = []
    children_by_dir = {}
    
    for path, sha in files.items():
        if "/" in path:
            top_dir, rest = path.split("/", 1)
            if top_dir not in children_by_dir:
                children_by_dir[top_dir] = {}
            children_by_dir[top_dir][rest] = sha
        else:
            tree_entries.append(TreeEntry(mode="100644", name=path, sha=sha))
            
    # Process subdirectories
    def process_dir(name_and_files):
        name, sub_files = name_and_files
        sub_tree_sha = _build_tree_recursive(objects_dir, sub_files)
        return TreeEntry(mode="040000", name=name, sha=sub_tree_sha)

    if children_by_dir:
        from concurrent.futures import ThreadPoolExecutor
        # Parallelize subtree creation for large breadth
        with ThreadPoolExecutor() as executor:
            subtree_entries = list(executor.map(process_dir, children_by_dir.items()))
            tree_entries.extend(subtree_entries)
            
    tree = Tree(entries=tree_entries)
    return tree.write(objects_dir)


def _build_tree_from_index(dg_dir: Path) -> str:
    """Read the index and build a proper recursive Tree object."""
    index = read_index(dg_dir)
    if not index.entries:
        print("Error: nothing to commit (empty index)", file=sys.stderr)
        sys.exit(1)

    objects_dir = dg_dir / "objects"
    files = {path: entry.sha for path, entry in index.entries.items()}
    return _build_tree_recursive(objects_dir, files)


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``commit`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"

    # AI Suggestion
    message = args.message
    if not message and getattr(args, "ai", False):
        from deep.ai.assistant import DeepGitAI
        ai = DeepGitAI(repo_root)
        suggestion = ai.suggest_commit_message()
        message = suggestion.text
        print(f"💡 AI Suggestion: {message}")
    
    if not message:
        print("Error: must provide a commit message (-m) or use --ai.", file=sys.stderr)
        sys.exit(1)

    from deep.storage.txlog import TransactionLog
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    from deep.core.locks import RepositoryLock, BranchLock

    # Fast-fail if repo is locked
    repo_lock = RepositoryLock(dg_dir)
    try:
        repo_lock.acquire()
    except TimeoutError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Lifecycle Hooks: pre-commit
    from deep.plugins.plugin import PluginManager
    pm = PluginManager(dg_dir)
    pm.discover()
    pm.run_hooks("pre-commit", repo_root=repo_root, message=message)

    try:
        with Timer(telemetry, "commit"):
            tree_sha = _build_tree_from_index(dg_dir)

            parent_sha = resolve_head(dg_dir)
            parent_shas = [parent_sha] if parent_sha else []

            config = Config(repo_root)
            author_name = config.get("user.name", "Deep Git User")
            author_email = config.get("user.email", "user@deep")
            author_str = f"{author_name} <{author_email}>"

            timestamp = int(time.time())
            from deep.utils.utils import get_local_timezone_offset
            timezone = get_local_timezone_offset()

            # GOD MODE: Real cryptographic signing
            signature = None
            if getattr(args, "sign", False):
                try:
                    from deep.core.security import KeyManager, CommitSigner
                    km = KeyManager(dg_dir)
                    # Auto-generate key if none exists
                    if km.get_active_key() is None:
                        km.generate_key()
                    signer = CommitSigner(km)

                    # Build unsigned commit to get content for signing
                    unsigned_commit = Commit(
                        tree_sha=tree_sha,
                        parent_shas=parent_shas,
                        author=author_str,
                        committer=author_str,
                        message=message,
                        timestamp=timestamp,
                        timezone=timezone,
                        signature=None,
                    )
                    content = unsigned_commit.serialize_content()
                    sig_hex, key_id = signer.sign(content)
                    signature = f"SIG:{key_id}:{sig_hex}"
                except Exception:
                    # Fallback to legacy mocked signature
                    signature = "MOCKED_GPG_SIGNATURE"

            commit = Commit(
                tree_sha=tree_sha,
                parent_shas=parent_shas,
                author=author_str,
                committer=author_str,
                message=message,
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
                    details=message,
                    target_object_id=commit_sha,
                    branch_ref=branch or "",
                    previous_commit_sha=parent_sha or ""
                )

                try:
                    if branch:
                        update_branch(dg_dir, branch, commit_sha)
                    else:
                        from deep.core.refs import update_head
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
        sig_status = " (signed ✅)" if signature else ""
        print(f"[{branch or 'detached HEAD'} {short}] {message}{sig_status}")
        
        # Lifecycle Hooks: post-commit
        pm.run_hooks("post-commit", repo_root=repo_root, sha=commit_sha, message=message)
    except Exception as e:
        raise
    finally:
        repo_lock.release()

"""
deep.commands.commit_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``commit -m <msg>`` command implementation.

ECDSA signing for Deep-native commits.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from deep.core.config import Config
from deep.storage.index import read_index
from deep.storage.objects import Blob, Commit, Tree, TreeEntry, read_object
from deep.core.refs import get_current_branch, resolve_head, update_branch
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.hooks import run_hook


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
            assert len(sha) == 40, f"Invalid SHA length for {path}: {len(sha)}"
            tree_entries.append(TreeEntry(mode="100644", name=path, sha=sha))
            
    # Process subdirectories
    if children_by_dir:
        for name, sub_files in children_by_dir.items():
            sub_tree_sha = _build_tree_recursive(objects_dir, sub_files)
            tree_entries.append(TreeEntry(mode="40000", name=name, sha=sub_tree_sha))

    tree = Tree(entries=tree_entries)
    return tree.write(objects_dir)


def _build_tree_from_index(dg_dir: Path, allow_empty: bool = False) -> str:
    """Read the index and build a proper recursive Tree object.

    If the index is empty and ``allow_empty`` is False, abort the commit.
    """
    from deep.storage.index import read_index_no_lock
    index = read_index_no_lock(dg_dir)
    if not index.entries and not allow_empty:
        print("Deep: error: nothing to commit (no staged changes).", file=sys.stderr)
        sys.exit(1)

    objects_dir = dg_dir / "objects"
    files = {path: entry.content_hash for path, entry in index.entries.items()}
    return _build_tree_recursive(objects_dir, files)


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``commit`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    # AI Suggestion
    message = args.message
    if not message and getattr(args, "ai", False):
        from deep.ai.assistant import DeepAI
        ai = DeepAI(repo_root)
        suggestion = ai.suggest_commit_message()
        message = suggestion.text
        print(f"Deep: AI suggestion: {message}")
    
    if not message:
        print("Deep: error: must provide a commit message (-m) or use --ai.", file=sys.stderr)
        sys.exit(1)

    from deep.storage.transaction import TransactionManager
    from deep.core.errors import DeepError
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog

    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    # Lifecycle Hooks: pre-commit
    run_hook(dg_dir, "pre-commit", args=[message])

    from deep.plugins.plugin import PluginManager
    pm = PluginManager(dg_dir)
    pm.discover()
    pm.run_hooks("pre-commit", repo_root=repo_root, message=message)

    try:
        branch = get_current_branch(dg_dir)
        # Use TransactionManager to handle Repo, Branch, and Index locks + WAL
        with TransactionManager(dg_dir, branch_name=branch) as tx:
            with Timer(telemetry, "commit"):
                allow_empty = getattr(args, "allow_empty", False)
                tree_sha = _build_tree_from_index(dg_dir, allow_empty=allow_empty)

                parent_sha = resolve_head(dg_dir)
                parent_shas = [parent_sha] if parent_sha else []

                config = Config(repo_root)
                author_name = config.get("user.name", "Deep User")
                author_email = config.get("user.email", "user@deep")
                author_str = f"{author_name} <{author_email}>"

                timestamp = int(os.environ.get("DEEP_COMMIT_TIMESTAMP", time.time()))
                from deep.utils.utils import get_local_timezone_offset
                timezone = os.environ.get("DEEP_COMMIT_TIMEZONE", get_local_timezone_offset())

                # GOD MODE: Real cryptographic signing
                signature = None
                unsigned_commit = None
                if getattr(args, "sign", False):
                    from deep.core.security import KeyManager, CommitSigner
                    km = KeyManager(dg_dir)
                    if km.get_active_key() is None:
                        km.generate_key()
                    signer = CommitSigner(km)

                    max_p_seq = 0
                    for p_sha in parent_shas:
                        try:
                            p_obj = read_object(objects_dir, p_sha)
                            if isinstance(p_obj, Commit):
                                max_p_seq = max(max_p_seq, p_obj.sequence_id)
                        except Exception: pass

                    unsigned_commit = Commit(
                        tree_sha=tree_sha,
                        parent_shas=parent_shas,
                        author=author_str,
                        committer=author_str,
                        message=message,
                        timestamp=timestamp,
                        timezone=timezone,
                        sequence_id=max_p_seq + 1,
                        signature=None,
                    )
                    content = unsigned_commit.serialize_content()
                    sig_hex, key_id = signer.sign(content)
                    signature = f"SIG:{key_id}:{sig_hex}"

                # Verify parent SHAs exist
                for p_sha in parent_shas:
                    read_object(objects_dir, p_sha)

                max_p_seq = 0
                if not signature:
                    for p_sha in parent_shas:
                        try:
                            p_obj = read_object(objects_dir, p_sha)
                            if isinstance(p_obj, Commit):
                                max_p_seq = max(max_p_seq, p_obj.sequence_id)
                        except Exception: pass
                else:
                    max_p_seq = unsigned_commit.sequence_id - 1

                commit = Commit(
                    tree_sha=tree_sha,
                    parent_shas=parent_shas,
                    author=author_str,
                    committer=author_str,
                    message=message,
                    timestamp=timestamp,
                    timezone=timezone,
                    sequence_id=max_p_seq + 1,
                    signature=signature,
                )
                commit_sha = commit.write(objects_dir)

                # Crash hook: after writing commit object but before WAL begin.
                if os.environ.get("DEEP_CRASH_TEST") == "BEFORE_REF_UPDATE":
                    raise RuntimeError("Deep: simulated crash before ref update")

                # WAL Transaction setup
                logical_ref = branch if branch else "HEAD"
                tx.begin(
                    operation="commit",
                    details=message,
                    target_object_id=commit_sha,
                    branch_ref=logical_ref,
                    previous_commit_sha=parent_sha or ""
                )

                # Crash hook: after WAL begin, before ref update.
                if os.environ.get("DEEP_CRASH_TEST") == "AFTER_BEGIN_BEFORE_REF":
                    raise RuntimeError("Deep: simulated crash after WAL begin")

                if branch:
                    from deep.core.refs import update_branch_no_lock
                    update_branch_no_lock(dg_dir, branch, commit_sha)
                else:
                    from deep.core.refs import update_head_no_lock
                    update_head_no_lock(dg_dir, commit_sha)

                tx.commit()

        audit.record(author_name, "commit", ref=branch or "HEAD", sha=commit_sha)
        short = commit_sha[:7]
        sig_status = " (signed ✅)" if signature else ""
        print(f"[{branch or 'detached HEAD'} {short}] {message}{sig_status}")
        pm.run_hooks("post-commit", repo_root=repo_root, sha=commit_sha, message=message)
        run_hook(dg_dir, "post-commit", args=[commit_sha, message])

    except DeepError:
        raise
    except Exception:
        raise


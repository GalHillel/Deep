"""
deep.commands.commit_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deep ``commit -m <msg>`` command implementation.

ECDSA signing for Deep-native commits.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

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
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'commit' command parser."""
    p_commit = subparsers.add_parser(
        "commit",
        help="Record changes to the repository history",
        description="Create a new commit containing the current contents of the index.",
        epilog=f"""
{format_header("Examples")}
{format_example("deep commit -m 'Fix bug'", "Create a commit with a manual message")}
{format_example("deep commit -a -m 'Rel'", "Auto-stage tracked changes and commit")}
{format_example("deep commit --ai -a", "AI-generated message with auto-stage")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_commit.add_argument("-m", "--message", help="The commit message describing the changes")
    p_commit.add_argument("-a", "--all", action="store_true", help="Automatically stage modified and deleted tracked files")
    p_commit.add_argument("--ai", action="store_true", help="Use AI to generate a commit message based on staged changes")
    p_commit.add_argument("-S", "--sign", action="store_true", help="Create a cryptographically signed commit")
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
        raise DeepCLIException(1)

    objects_dir = dg_dir / "objects"
    files = {path: entry.content_hash for path, entry in index.entries.items()}
    return _build_tree_recursive(objects_dir, files)


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``commit`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    allow_empty = getattr(args, "allow_empty", False)
    tree_sha = _build_tree_from_index(dg_dir, allow_empty=allow_empty)
    parent_sha = resolve_head(dg_dir)
    parent_tree_sha = None
    if parent_sha:
        try:
            p_obj = read_object(objects_dir, parent_sha)
            if isinstance(p_obj, Commit):
                parent_tree_sha = p_obj.tree_sha
        except Exception:
            pass

    # Phase 7 / 5: Commit Without Changes Guard (skip for --amend)
    if parent_tree_sha and tree_sha == parent_tree_sha and not allow_empty and not getattr(args, "amend", False):
        print("No changes to commit.")
        raise DeepCLIException(1)

    message = getattr(args, "message", None)
    if not message and getattr(args, "ai", False):
        from deep.ai.assistant import DeepAI
        ai = DeepAI(repo_root)
        suggestion = ai.suggest_commit_message()
        message = suggestion.text
        
        print(f"Deep: AI suggestion (confidence: {suggestion.confidence:.2f}):\n---")
        print(message)
        print("---")
        ans = input("Accept this commit message? [y/N]: ")
        if ans.lower() != "y":
            print("Commit aborted.", file=sys.stderr)
            raise DeepCLIException(1)
    
    # Handle --amend message logic
    if getattr(args, "amend", False):
        if not message:
            parent_sha = resolve_head(dg_dir)
            if parent_sha:
                try:
                    p_obj = read_object(objects_dir, parent_sha)
                    if isinstance(p_obj, Commit):
                        message = p_obj.message
                except Exception:
                    pass
    
    if not message:
        print("Deep: error: must provide a commit message (-m) or use --ai.", file=sys.stderr)
        raise DeepCLIException(1)

    if getattr(args, "all", False):
        from deep.core.status import compute_status

        status = compute_status(repo_root)

        files_to_update = list(status.modified)
        files_to_remove = list(status.deleted)

        if files_to_update or files_to_remove:
            from deep.storage.index import (
                add_multiple_to_index,
                remove_multiple_from_index
            )
            from deep.commands.add_cmd import _add_file_worker
            from concurrent.futures import ThreadPoolExecutor, as_completed

            index = read_index(dg_dir)

            # --- Handle deletions ---
            if files_to_remove:
                remove_multiple_from_index(dg_dir, files_to_remove)

            # --- Handle modifications ---
            if files_to_update:
                results = []
                max_workers = min(os.cpu_count() or 4, len(files_to_update))

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []

                    for rel_path in files_to_update:
                        file_path = repo_root / rel_path
                        entry = index.entries.get(rel_path)

                        p_sha = entry.content_hash if entry else None
                        p_size = entry.size if entry else None
                        p_mtime_ns = entry.mtime_ns if entry else None

                        futures.append(executor.submit(
                            _add_file_worker,
                            repo_root,
                            dg_dir,
                            file_path,
                            p_sha,
                            p_size,
                            p_mtime_ns
                        ))

                    for future in as_completed(futures):
                        results.append(future.result())

                actual_results = [r for r in results if r[1] is not None]

                if actual_results:
                    add_multiple_to_index(dg_dir, actual_results)

            print(f"Deep: Auto-staged {len(files_to_update)} modified and {len(files_to_remove)} deleted files.")

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
                if getattr(args, "amend", False) and parent_sha:
                    try:
                        p_obj = read_object(objects_dir, parent_sha)
                        if isinstance(p_obj, Commit):
                            parent_shas = p_obj.parent_shas
                    except Exception:
                        parent_shas = [parent_sha]
                else:
                    parent_shas = [parent_sha] if parent_sha else []

                # Check for MERGE_HEAD (conflict resolution creates merge commit)
                merge_head_path = dg_dir / "MERGE_HEAD"
                found_merge_head = False
                if merge_head_path.exists():
                    try:
                        merge_sha = merge_head_path.read_text(encoding="utf-8").strip()
                        if merge_sha and merge_sha not in parent_shas:
                            parent_shas.append(merge_sha)
                            found_merge_head = True
                    except Exception:
                        pass

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

                # Clean up MERGE_HEAD after successful commit
                merge_head_path = dg_dir / "MERGE_HEAD"
                if merge_head_path.exists():
                    try:
                        merge_head_path.unlink()
                    except Exception:
                        pass

        # Commit Intelligence (Part 4)
        import re
        patterns = [
            (r"(?i)fix\s+#(\d+)", "fixed"),
            (r"(?i)closes\s+#(\d+)", "closed"),
            (r"(?i)resolve\s+issue\s+#(\d+)", "resolved"),
        ]
        
        from deep.core.issue import IssueManager
        im = IssueManager(dg_dir)
        
        found_issues = []
        for pattern, action in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                try:
                    issue_id = int(match.group(1))
                    found_issues.append((issue_id, action))
                except Exception: pass
        
        for issue_id, action in found_issues:
            try:
                issue = im.get_issue(issue_id)
                if issue:
                    im.add_timeline_event(issue.id, "commit_linked", sha=commit_sha)
                    if "fix" in message.lower() or "close" in message.lower():
                        issue.status = "closed"
                        im.add_timeline_event(issue.id, "closed", reason=f"Commit {commit_sha[:7]} {action}")
                        im.save_issue(issue)
                        print(f"✔ Linked Issue #{issue_id} {action} automatically")
                    else:
                        print(f"✔ Linked Commit {commit_sha[:7]} to Issue #{issue_id}")
            except Exception:
                pass

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


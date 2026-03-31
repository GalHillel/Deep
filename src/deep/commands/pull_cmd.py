"""
deep.commands.pull_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep pull <remote> <branch>`` command implementation.

Native fetch + merge:
1. Discover remote refs via smart protocol
2. Fetch missing objects
3. Merge remote branch into current

No external VCS CLI dependency.
"""
from deep.core.constants import DEEP_DIR
from deep.utils.ux import Color

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from argparse import Namespace
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import update_branch, resolve_head, get_branch, update_remote_ref, get_remote_ref
from deep.core.config import Config

import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'pull' command parser."""
    p_pull = subparsers.add_parser(
        "pull",
        help="Fetch from and integrate with another repository",
        description="""Fetch changes from a remote repository and merge them into the current branch.

This command is a combination of 'deep fetch' and 'deep merge'.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep pull origin main\033[0m
     Fetch and merge 'main' from 'origin' remote
  \033[1;34m⚓️ deep pull\033[0m
     Pull changes from the default upstream branch
  \033[1;34m⚓️ deep pull --rebase\033[0m
     Fetch and rebase your local commits onto remote changes
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_pull.add_argument("url", nargs="?", help="The remote repository name or URL (default: origin)")
    p_pull.add_argument("branch", nargs="?", help="The remote branch name to pull from")
    p_pull.add_argument("--rebase", action="store_true", help="Rebase current branch onto the tip of the remote branch instead of merging")
    p_pull.add_argument("--no-commit", action="store_true", help="Perform the pull but do not automatically create a merge commit")

def run(args) -> None:
    """Execute the ``pull`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    from deep.core.refs import get_current_branch

    dg_dir = repo_root / DEEP_DIR

    url_or_name = args.url or "origin"
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)

    branch = args.branch or get_current_branch(dg_dir)
    if not branch:
        print("Deep: error: could not determine branch to pull. Specify a branch.", file=sys.stderr)
        raise DeepCLIException(1)

    from deep.storage.transaction import TransactionManager
    from deep.objects.hash_object import object_exists

    with TransactionManager(dg_dir) as tm:
        tm.begin("pull")
        try:
            from deep.network.client import get_remote_client
            from deep.network.auth import get_auth_token

            auth_token = config.get("auth.token") or get_auth_token()
            client = get_remote_client(url, auth_token=auth_token)

            print(Color.wrap(Color.CYAN, f"Pulling from {url}..."))

            # 1. Discover remote refs
            remote_refs = client.ls_remote()
            remote_ref = f"refs/heads/{branch}"
            remote_sha = remote_refs.get(remote_ref)

            if not remote_sha:
                print(f"Deep: error: Remote branch '{branch}' not found", file=sys.stderr)
                raise DeepCLIException(1)

            # 2. Determine what we have locally
            have_shas = []
            local_sha = get_branch(dg_dir, branch)
            if local_sha and object_exists(dg_dir / "objects", local_sha):
                have_shas.append(local_sha)
            
            head_sha = resolve_head(dg_dir)
            if head_sha and object_exists(dg_dir / "objects", head_sha):
                have_shas.append(head_sha)

            # Also check remote tracking refs
            tracked = get_remote_ref(dg_dir, url_or_name, branch)
            if tracked and object_exists(dg_dir / "objects", tracked):
                have_shas.append(tracked)

            # 3. Fetch
            # BUG 2 FIX: Even if tracking ref matches remote_sha, we MUST re-fetch if object is missing.
            if object_exists(dg_dir / "objects", remote_sha) and remote_sha in have_shas:
                print("Already up to date.")
            else:
                print(f"Fetching {branch} ({remote_sha[:7]})...")
                count = client.fetch(
                    dg_dir / "objects",
                    want_shas=[remote_sha],
                    have_shas=have_shas,
                )
                if count:
                    print(f"Fetched {count} objects.")
                else:
                    # Double check if fetch returned 0 but object is STILL missing
                    if not object_exists(dg_dir / "objects", remote_sha):
                        print(f"Deep: error: Remote reported object {remote_sha} as existing, but fetch failed to download it.", file=sys.stderr)
                        raise DeepCLIException(1)

            # Update remote tracking ref
            update_remote_ref(dg_dir, url_or_name, branch, remote_sha)
            if url_or_name != "origin":
                update_remote_ref(dg_dir, "origin", branch, remote_sha)

            # 4. Merge (or fast-forward if local has no commits)
            head_sha = resolve_head(dg_dir)
            if not head_sha:
                # Empty repo: fast-forward by setting branch and checking out
                print(f"Fast-forwarding empty branch to {remote_sha[:7]}...")
                update_branch(dg_dir, branch, remote_sha)
                from deep.core.refs import update_head
                update_head(dg_dir, f"ref: refs/heads/{branch}")
                try:
                    from deep.commands.checkout_cmd import run as checkout_run
                    checkout_run(Namespace(target=branch, force=True, branch=None, files=[]))
                except Exception:
                    pass  # Working tree update is best-effort
            else:
                print(f"Merging {remote_sha[:7]} into current branch...")
                from deep.commands.merge_cmd import run as merge_run
                merge_args = Namespace(branch=remote_sha)
                try:
                    merge_run(merge_args)
                except DeepCLIException:
                    # Write MERGE_HEAD
                    merge_head = dg_dir / "MERGE_HEAD"
                    if not merge_head.exists():
                        merge_head.write_text(remote_sha + "\n", encoding="utf-8")
                    raise

            tm.commit()

        except Exception as e:
            if not isinstance(e, DeepCLIException):
                print(f"Deep: error: pull failed: {e}", file=sys.stderr)
            raise e

"""
deep.commands.pull_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep pull <remote> <branch>`` command implementation.

Native fetch + merge:
1. Discover remote refs via Git protocol
2. Fetch missing objects
3. Merge remote branch into current

No git CLI dependency.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import update_branch, resolve_head, get_branch, update_remote_ref, get_remote_ref
from deep.core.config import Config
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``pull`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)

    branch = args.branch
    dg_dir = repo_root / DEEP_DIR

    try:
        from deep.network.git_protocol import GitTransportClient
        from deep.network.auth import get_auth_token

        auth_token = config.get("auth.token") or get_auth_token()
        client = GitTransportClient(url, token=auth_token)

        print(Color.wrap(Color.CYAN, f"Pulling from {url}..."))

        # 1. Discover remote refs
        remote_refs = client.ls_remote()
        remote_ref = f"refs/heads/{branch}"
        remote_sha = remote_refs.get(remote_ref)

        if not remote_sha:
            print(f"Deep: error: Remote branch '{branch}' not found", file=sys.stderr)
            sys.exit(1)

        # 2. Determine what we have locally
        have_shas = []
        local_sha = get_branch(dg_dir, branch)
        if local_sha:
            have_shas.append(local_sha)
        head_sha = resolve_head(dg_dir)
        if head_sha:
            have_shas.append(head_sha)

        # Also check remote tracking refs
        tracked = get_remote_ref(dg_dir, url_or_name, branch)
        if tracked:
            have_shas.append(tracked)

        # 3. Fetch
        print(f"Fetching {branch} ({remote_sha[:7]})...")
        count = client.fetch(
            dg_dir / "objects",
            want_shas=[remote_sha],
            have_shas=have_shas,
        )
        if count:
            print(f"Fetched {count} objects.")
        else:
            print("Already up to date.")

        # Update remote tracking ref
        update_remote_ref(dg_dir, url_or_name, branch, remote_sha)
        if url_or_name != "origin":
            update_remote_ref(dg_dir, "origin", branch, remote_sha)

        # 4. Merge
        print(f"Merging {remote_sha[:7]} into current branch...")
        from deep.commands.merge_cmd import run as merge_run
        merge_args = Namespace(branch=remote_sha)
        merge_run(merge_args)

    except Exception as e:
        print(f"Deep: error: pull failed: {e}", file=sys.stderr)
        sys.exit(1)

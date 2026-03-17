"""
deep.commands.clone_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep clone`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.refs import update_head, update_branch, resolve_head
from deep.core.config import Config
from deep.network.client import get_remote_client
from deep.commands import init_cmd, checkout_cmd
import argparse


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``clone`` command."""
    url = args.url
    # Derive name from URL
    name = url.split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    if ":" in name and "/" not in name:
        name = name.split(":")[-1]
    
    target_dir = Path(args.dir or name).resolve()
    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"DeepGit: error: Target directory '{target_dir}' already exists and is not empty", file=sys.stderr)
        sys.exit(1)
        
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Init new repo
    import os
    old_cwd = os.getcwd()
    os.chdir(target_dir)
    try:
        init_cmd.run(argparse.Namespace(path=None))
        
        # Connect to remote
        auth_token = getattr(args, "token", None)
        client = get_remote_client(url, auth_token=auth_token)
        client.connect()
        
        print(f"DeepGit: cloning into '{target_dir}'...")
        
        # Discovery
        refs = client.ls_refs()
        main_sha = refs.get("refs/heads/main")
        if not main_sha:
            # Fallback to first branch found
            if refs:
                main_sha = list(refs.values())[0]
            else:
                print("DeepGit: error: Remote repository is empty or has no branches", file=sys.stderr)
                sys.exit(1)

        # Fetch
        dg_dir = target_dir / DEEP_DIR
        client.fetch(dg_dir / "objects", main_sha, depth=getattr(args, "depth", None), filter_spec=getattr(args, "filter", None))
        
        # Update refs and checkout
        update_branch(dg_dir, "main", main_sha)
        update_head(dg_dir, "ref: refs/heads/main")
        
        # Add origin remote
        config = Config(target_dir)
        config.set_local("remote.origin.url", url)
        
        # Checkout files (may fail if partial clone)
        try:
            checkout_cmd.run(argparse.Namespace(target="main", force=True, branch=None))
        except (FileNotFoundError, ValueError) as e:
            if getattr(args, "filter", None):
                print(f"Partial clone: skipping initial checkout (some objects missing: {e})")
            else:
                raise
        
        print("Done.")
        
    finally:
        os.chdir(old_cwd)

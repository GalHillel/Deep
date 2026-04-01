"""
deep.commands.clone_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep clone`` command implementation.

Full native smart protocol clone pipeline:
1. Discover refs via smart protocol
2. Choose HEAD ref
3. Request packfile (want/done)
4. Parse standard packfile → write objects to Deep store
5. Reconstruct working directory from tree

No external VCS CLI dependency.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
import os
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.refs import update_head, update_branch, resolve_head
from deep.core.config import Config
from deep.commands import init_cmd, checkout_cmd
import argparse

def ns(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``clone`` command."""
    url = args.url
    # Derive name from URL
    name = url.split("/")[-1]
    if name.endswith(".deep") or name.endswith(".git"):
        name = name[:-4]
    if name.endswith(".deep"):
        name = name[:-5]
    if ":" in name and "/" not in name:
        name = name.split(":")[-1]

    target_dir = Path(args.dir or name).resolve()
    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"Deep: error: Target directory '{target_dir}' already exists and is not empty", file=sys.stderr)
        raise DeepCLIException(1)

    mirror = getattr(args, "mirror", False)
    shallow_since_val = getattr(args, "shallow_since", None)
    
    # Parse shallow_since into a timestamp for the protocol
    shallow_since_ts = None
    if shallow_since_val:
        try:
            # Try as a float/int timestamp first
            shallow_since_ts = int(float(shallow_since_val))
        except ValueError:
            # Try ISO format or similar
            from datetime import datetime
            try:
                # Basic ISO format support
                dt = datetime.fromisoformat(shallow_since_val.replace("Z", "+00:00"))
                shallow_since_ts = int(dt.timestamp())
            except ValueError:
                # If we can't parse it, pass it through as is to the wire (maybe server can parse)
                # But for LocalClient we need an int.
                print(f"Deep: warning: Could not parse date '{shallow_since_val}', using as raw timestamp", file=sys.stderr)
                try:
                    shallow_since_ts = int(shallow_since_val)
                except ValueError:
                    shallow_since_ts = None

    target_dir.mkdir(parents=True, exist_ok=True)
    success = False

    old_cwd = os.getcwd()
    os.chdir(target_dir)
    try:
        init_cmd.run(ns(path=None, files=[], bare=mirror))

        dg_dir = target_dir if mirror else target_dir / DEEP_DIR
        from deep.utils.logger import setup_repo_logging
        setup_repo_logging(target_dir, is_bare=mirror) # Initialize file logging in the new repo
        
        objects_dir = dg_dir / "objects"

        # Use native smart protocol
        from deep.network.client import get_remote_client
        from deep.network.auth import get_auth_token

        token = getattr(args, "token", None) or get_auth_token()
        client = get_remote_client(url, auth_token=token)

        print(f"Deep: cloning into '{target_dir}'...")

        # Clone — discover refs + download packfile + unpack
        refs, head_ref = client.clone(
            objects_dir,
            depth=getattr(args, "depth", None),
            filter_spec=getattr(args, "filter", None),
            shallow_since=shallow_since_ts,
        )

        # Determine main branch
        head_sha = refs.get("HEAD", "")
        main_branch = "main"

        # Try to find the branch name for HEAD
        if head_ref and head_ref.startswith("refs/heads/"):
            main_branch = head_ref[len("refs/heads/"):]
        else:
            # Fall back through common branch names
            for branch_name in ("main", "master"):
                ref = f"refs/heads/{branch_name}"
                if ref in refs:
                    main_branch = branch_name
                    head_sha = refs[ref]
                    break

        if not head_sha:
            for ref_name, sha in refs.items():
                if ref_name.startswith("refs/heads/"):
                    main_branch = ref_name[len("refs/heads/"):]
                    head_sha = sha
                    break

        # Update refs
        if head_sha:
            update_branch(dg_dir, main_branch, head_sha)
            update_head(dg_dir, f"ref: refs/heads/{main_branch}")

        # Store all remote refs as remote tracking branches
        for ref_name, sha in refs.items():
            if ref_name.startswith("refs/heads/"):
                branch = ref_name[len("refs/heads/"):]
                from deep.core.refs import update_remote_ref
                update_remote_ref(dg_dir, "origin", branch, sha)

        # Save remote URL
        config = Config(dg_dir.parent if not mirror else dg_dir)
        config.set_local("remote.origin.url", url)
        config.set_local(f"branch.{main_branch}.remote", "origin")
        config.set_local(f"branch.{main_branch}.merge", f"refs/heads/{main_branch}")
        if mirror:
            config.set_local("remote.origin.mirror", "true")
            config.set_local("remote.origin.fetch", "+refs/*:refs/*")

        if not head_sha:
            print("Deep: warning: Remote repository appears empty", file=sys.stderr)
            success = True # Ambiguous, but repo is initialized
            return

        # Checkout working tree
        if not mirror:
            try:
                checkout_cmd.run(ns(
                    target=main_branch, force=True, branch=None, files=[]
                ))
            except (FileNotFoundError, ValueError) as e:
                if getattr(args, "filter", None) or getattr(args, "depth", None):
                    print(f"Partial clone: skipping initial checkout ({e})")
                else:
                    print(f"Deep: warning: checkout failed: {e}", file=sys.stderr)

        print("Done.")
        success = True

    except Exception as e:
        # Step back to original CWD before deletion on Windows
        os.chdir(old_cwd)
        from deep.utils.logger import shutdown_logging
        from deep.utils.system import safe_rmtree
        
        # Release log handle before cleanup
        shutdown_logging()
        
        if target_dir.exists():
            try:
                safe_rmtree(target_dir, ignore_errors=True)
            except OSError:
                # Best effort cleanup
                pass
        raise e
    finally:
        if os.getcwd() == str(target_dir):
            os.chdir(old_cwd)

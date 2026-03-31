"""
deep.commands.push_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep push`` command implementation.

Native smart protocol push:
1. Discover remote refs
2. Compute missing objects via DAG walk
3. Build v2 packfile
4. Send via receive-pack protocol
5. Parse status response

No external VCS CLI dependency.
"""
from deep.core.constants import DEEP_DIR
from deep.utils.ux import Color

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import resolve_head, get_branch
from deep.core.config import Config

import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'push' command parser."""
    p_push = subparsers.add_parser(
        "push",
        help="Update remote refs and associated objects",
        description="""Upload local branch commits to a remote repository and update remote references.

This command ensures your collaborators can access your latest changes.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep push origin main\033[0m
     Push the 'main' branch to the 'origin' remote
  \033[1;34m⚓️ deep push\033[0m
     Push current branch to its configured upstream
  \033[1;34m⚓️ deep push --force\033[0m
     Force update the remote branch (overwrites history!)
  \033[1;34m⚓️ deep push -u origin feature\033[0m
     Push and set 'origin' as the upstream for 'feature'
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_push.add_argument("url", nargs="?", help="The remote repository name or URL (default: origin)")
    p_push.add_argument("branch", nargs="?", help="The local branch name to push")
    p_push.add_argument("-f", "--force", action="store_true", help="Force update the remote branch (disables safety checks)")
    p_push.add_argument("-u", "--set-upstream", action="store_true", help="Set up tracking information for the pushed branch")
    p_push.add_argument("--tags", action="store_true", help="Push all local tags in addition to commits")

def run(args: Any) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    config = Config(repo_root)
    from deep.core.refs import get_current_branch

    # Resolving Remote URL
    url_or_name = args.url or "origin"
    url = config.get(f"remote.{url_or_name}.url", url_or_name)

    # Resolving Branch
    branch = args.branch or get_current_branch(dg_dir)
    if not branch:
        print("Deep: error: could not determine branch to push (specify <branch> or set upstream).", file=sys.stderr)
        raise DeepCLIException(1)

    local_sha = get_branch(dg_dir, branch)
    if not local_sha:
        print(f"Deep: error: Branch '{branch}' not found locally", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    from deep.storage.transaction import TransactionManager
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog
    from deep.core.refs import get_current_branch, update_branch, update_remote_ref

    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    with TransactionManager(dg_dir) as tm:
        tm.begin("push")
        try:
            run_hook(dg_dir, "pre-push", args=[url, branch])
            with Timer(telemetry, "push"):
                # Use native smart protocol
                from deep.network.client import get_remote_client
                from deep.network.auth import get_auth_token

                auth_token = config.get("auth.token") or get_auth_token()
                client = get_remote_client(url, auth_token=auth_token)
                
                # BUG 1 FIX: SmartTransportClient manages its own connection. 
                # LocalClient also doesn't need manual connect().
                if hasattr(client, 'connect'):
                    client.connect()

                # Discover remote refs
                print(f"Checking remote {branch} state...")
                remote_refs = client.ls_remote()

                remote_ref = f"refs/heads/{branch}"
                remote_sha = remote_refs.get(remote_ref, "0" * 40)

                if remote_sha == local_sha:
                    print("Everything up-to-date.")
                    tm.commit()
                    return

                objects_dir = dg_dir / "objects"

                # Fetch remote objects before FF check so is_ancestor
                # can walk the DAG reliably even after merge/conflict resolution
                if remote_sha and remote_sha != "0" * 40:
                    from deep.objects.hash_object import object_exists
                    if not object_exists(objects_dir, remote_sha):
                        try:
                            client.fetch(
                                objects_dir,
                                want_shas=[remote_sha],
                                have_shas=[local_sha],
                            )
                        except Exception:
                            pass  # Best-effort; is_ancestor will still try

                # Check for divergence/non-fast-forward
                if remote_sha and remote_sha != "0" * 40:
                    from deep.core.refs import is_ancestor
                    from deep.storage.objects import read_object as _ro, Commit as _Commit

                    is_ff = is_ancestor(objects_dir, remote_sha, local_sha)

                    if not is_ff:
                        print(Color.wrap(Color.YELLOW,
                              "hint: Updates were rejected because the tip of your current branch is behind\n"
                              "hint: its remote counterpart. Integrate the remote changes (e.g.,\n"
                              "hint: 'deep pull ...') before pushing again.\n"
                              "hint: See the 'Note about fast-forwards' in 'deep push --help' for details."),
                              file=sys.stderr)
                        
                        if not getattr(args, 'force', False):
                            raise DeepCLIException(1)

                print(f"Pushing {branch} to {url}...")
                resp = client.push(
                    objects_dir,
                    remote_ref,
                    remote_sha,
                    local_sha,
                )
                print(f"Push result: {resp}")

                # Update remote tracking ref
                update_remote_ref(dg_dir, url_or_name, branch, local_sha)
                if url_or_name != "origin":
                    update_remote_ref(dg_dir, "origin", branch, local_sha)

                # Support --set-upstream
                if getattr(args, "set_upstream", False):
                    config.set_local(f"branch.{branch}.remote", url_or_name)
                    config.set_local(f"branch.{branch}.merge", f"refs/heads/{branch}")
                    print(f"Branch '{branch}' set up to track remote branch '{branch}' from '{url_or_name}'.")

            tm.commit()
            audit.record("local", "push", ref=branch, sha=local_sha, client=url)

        except Exception as e:
            # Re-raise to let TransactionManager handle rollback and main.py handle exit
            if not isinstance(e, DeepCLIException):
                print(f"Deep: error: push failed: {e}", file=sys.stderr)
            raise e

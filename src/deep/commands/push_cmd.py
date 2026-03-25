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

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import resolve_head, get_branch
from deep.core.config import Config
from deep.utils.ux import Color
from deep.core.hooks import run_hook


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``push`` command."""
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

                # Check for divergence/non-fast-forward
                if remote_sha and remote_sha != "0" * 40:
                    from deep.core.refs import is_ancestor
                    objects_dir = dg_dir / "objects"

                    # Try to check if remote is ancestor of local (FF check)
                    is_ff = is_ancestor(objects_dir, remote_sha, local_sha)
                    
                    if not is_ff:
                        # Extra check: if local is ancestor of remote, it's definitely divergent/behind
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
                    dg_dir / "objects",
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

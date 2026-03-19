"""
deep.commands.push_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep push`` command implementation.

Native Git protocol push:
1. Discover remote refs
2. Compute missing objects via DAG walk
3. Build Git v2 packfile
4. Send via receive-pack protocol
5. Parse status response

No git CLI dependency.
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

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)

    branch = args.branch
    local_sha = get_branch(repo_root / DEEP_DIR, branch)
    if not local_sha:
        print(f"Deep: error: Branch '{branch}' not found locally", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    from deep.storage.txlog import TransactionLog
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog
    from deep.core.refs import get_current_branch, update_branch, update_remote_ref

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    tx_id = txlog.begin("push", f"{branch} -> {url}")
    try:
        run_hook(dg_dir, "pre-push", args=[url, branch])
        with Timer(telemetry, "push"):
            # Use native Git protocol
            from deep.network.client import get_remote_client
            from deep.network.auth import get_auth_token

            auth_token = config.get("auth.token") or get_auth_token()
            client = get_remote_client(url, auth_token=auth_token)
            client.connect()

            # Discover remote refs
            print(f"Checking remote {branch} state...")
            remote_refs = client.ls_remote()

            remote_ref = f"refs/heads/{branch}"
            remote_sha = remote_refs.get(remote_ref, "0" * 40)

            if remote_sha == local_sha:
                print("Everything up-to-date.")
                txlog.commit(tx_id)
                return

            # Check for divergence/non-fast-forward
            if remote_sha and remote_sha != "0" * 40:
                from deep.core.refs import is_ancestor
                objects_dir = dg_dir / "objects"

                # Try to check if remote is ancestor of local
                from deep.objects.hash_object import object_exists
                if object_exists(objects_dir, remote_sha):
                    if not is_ancestor(objects_dir, remote_sha, local_sha):
                        print(Color.wrap(Color.YELLOW,
                              "Warning: Non-fast-forward push. "
                              "Remote has diverged. Use 'deep pull' first or push with --force."),
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

        txlog.commit(tx_id)
        audit.record("local", "push", ref=branch, sha=local_sha, client=url)

    except Exception as e:
        txlog.rollback(tx_id, str(e))
        print(f"Deep: error: push failed: {e}", file=sys.stderr)
        raise DeepCLIException(1)

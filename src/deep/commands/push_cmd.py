"""
deep.commands.push_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep push`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_GIT_DIR
from deep.core.refs import resolve_head, get_branch
from deep.core.config import Config
from deep.network.client import get_remote_client
from deep.utils.ux import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``push`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)
    
    branch = args.branch
    local_sha = get_branch(repo_root / DEEP_GIT_DIR, branch)
    if not local_sha:
        print(f"Error: Branch '{branch}' not found locally", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR

    auth_token = config.get("auth.token")
    client = get_remote_client(url, auth_token=auth_token)

    from deep.storage.txlog import TransactionLog
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    tx_id = txlog.begin("push", f"{branch} -> {url}")
    try:
        with Timer(telemetry, "push"):
            client.connect()
            print(f"Pushing {branch} to {url}...")
            resp = client.push(dg_dir / "objects", f"refs/heads/{branch}", "0"*40, local_sha)
            print(resp)
        txlog.commit(tx_id)
        audit.record("local", "push", ref=branch, sha=local_sha, client=url)
    except Exception as e:
        txlog.rollback(tx_id, str(e))
        print(f"Push failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


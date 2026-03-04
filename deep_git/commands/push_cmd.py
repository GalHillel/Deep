"""
deep_git.commands.push_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit push`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.repository import find_repo, DEEP_GIT_DIR
from deep_git.core.refs import resolve_head, get_branch
from deep_git.network.client import RemoteClient


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``push`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    url = args.url
    if ":" not in url:
        print("Error: URL must be in host:port format", file=sys.stderr)
        sys.exit(1)
        
    host, port_str = url.split(":", 1)
    port = int(port_str)
    
    branch = args.branch
    local_sha = get_branch(repo_root / DEEP_GIT_DIR, branch)
    if not local_sha:
        print(f"Error: Branch '{branch}' not found locally", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR

    from deep_git.core.txlog import TransactionLog
    from deep_git.core.telemetry import TelemetryCollector, Timer
    from deep_git.core.audit import AuditLog

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    tx_id = txlog.begin("push", f"{branch} -> {url}")
    try:
        client = RemoteClient(host, port)
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


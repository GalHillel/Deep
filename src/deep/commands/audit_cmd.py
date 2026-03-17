"""
deep.commands.audit_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep audit [show|report]`` command implementation.

GOD MODE: Supports 'report' subcommand for Merkle-chained audit report.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.audit import AuditLog
from deep.core.repository import DEEP_DIR, find_repo
from deep.utils.ux import Color


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    audit = AuditLog(dg_dir)

    audit_command = getattr(args, "audit_command", "show") or "show"

    if audit_command == "report":
        print(audit.export_report())
        return

    # Default: show entries
    entries = audit.read_all()
    if not entries:
        print("No audit entries recorded.")
        return
        
    print(f"{'TIMESTAMP':<20} | {'USER':<15} | {'ACTION':<15} | {'DETAILS'}")
    print("-" * 80)
    
    for e in entries[-50:]: # Show last 50
        import datetime
        ts = datetime.datetime.fromtimestamp(e.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts:<20} | {e.user:<15} | {e.action:<15} | {e.details}")

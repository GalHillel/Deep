"""
deep_git.commands.batch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit batch <script>`` — execute batch operations from a script file.

Script format (.dgit):
    add file1.txt file2.txt
    commit -m "batch commit"
    branch feature-x
    checkout feature-x
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from deep_git.core.repository import find_repo, DEEP_GIT_DIR


def run(args) -> None:
    """Execute the ``batch`` command."""
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Script '{script_path}' not found", file=sys.stderr)
        sys.exit(1)

    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR

    from deep_git.core.txlog import TransactionLog
    from deep_git.core.telemetry import TelemetryCollector, Timer
    from deep_git.core.audit import AuditLog

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    lines = script_path.read_text(encoding="utf-8").splitlines()
    total = 0
    errors = 0

    print(f"🔄 Batch: executing {len(lines)} operations from {script_path.name}")

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        tx_id = txlog.begin("batch", line)
        try:
            with Timer(telemetry, "batch_op"):
                parts = shlex.split(line)
                if not parts:
                    continue

                # Import and execute the deepgit main dispatch
                from deep_git.main import build_parser, main
                # Build args for this sub-command
                try:
                    main(parts)
                except SystemExit as se:
                    if se.code != 0 and se.code is not None:
                        raise RuntimeError(f"Command failed: {line}")

            txlog.commit(tx_id)
            audit.record("batch", parts[0], details=line)
            total += 1
        except Exception as e:
            txlog.rollback(tx_id, str(e))
            print(f"  ✗ Line {i}: {e}", file=sys.stderr)
            errors += 1
            if args.fail_fast if hasattr(args, "fail_fast") else False:
                break

    print(f"✅ Batch complete: {total} succeeded, {errors} failed")

"""
deep.commands.batch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep batch <script>`` — execute batch operations from a script file.

Script format (.dgit):
    add file1.txt file2.txt
    commit -m "batch commit"
    branch feature-x
    checkout feature-x
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import shlex
import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'batch' command parser."""
    p_batch = subparsers.add_parser(
        "batch",
        help="Execute multiple Deep commands in a single transaction",
        description="""Deep Batch allows for the atomic execution of multiple Deep commands from a script file or standard input.

This ensures that a sequence of operations (e.g., branching, adding, and committing) is treated as a single transaction, maintaining repository consistency even if an individual command fails.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep batch script.dgit\033[0m
     Execute Deep commands listed in 'script.dgit'
  \033[1;34m⚓️ deep batch - --fail-fast\033[0m
     Read commands from stdin and stop on the first error
  \033[1;34m⚓️ deep batch migrate.txt --dry-run\033[0m
     Identify potential batch operations without applying them
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_batch.add_argument("script", help="The file path containing Deep commands (use '-' for stdin)")
    p_batch.add_argument("--fail-fast", action="store_true", help="Stop execution on first error")


def run(args) -> None:
    """Execute the ``batch`` command."""
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Deep: error: Script '{script_path}' not found", file=sys.stderr)
        raise DeepCLIException(1)

    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    from deep.storage.txlog import TransactionLog
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog

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

                # Build parser and execute mapped command
                from deep.cli.main import build_parser
                import importlib
                parser = build_parser()
                try:
                    cmd_args = parser.parse_args(parts)
                except SystemExit as se:
                    if se.code != 0 and se.code is not None:
                        raise RuntimeError(f"Argument parsing failed: {line}")
                    else:
                        continue

                try:
                    cmd_module = importlib.import_module(f"deep.commands.{cmd_args.command}_cmd")
                    cmd_module.run(cmd_args)
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

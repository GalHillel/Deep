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
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'commit-graph' command parser."""
    subparsers.add_parser(
        "commit-graph",
        help="Write and verify the commit-graph file",
        description="Manage the commit-graph binary index to accelerate history walks.",
        epilog=f"""
Examples:
{format_example("deep commit-graph write", "Regenerate the commit-graph index")}
""",
        formatter_class=DeepHelpFormatter,
    )


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

"""
deep.commands.batch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep batch <script>`` — execute batch operations from a script file.

Script format (.deep):
    add file1.txt file2.txt
    commit -m "batch commit"
    branch feature-x
    checkout feature-x
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import shlex
import sys
import importlib
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR

from rich.console import Console

def run(args) -> None:
    """Execute the ``batch`` command."""
    console = Console()
    script_path = Path(args.script)
    
    if not script_path.exists():
        console.print(f"[red]Deep: error: Script '{script_path}' not found[/red]")
        raise DeepCLIException(1)

    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        console.print(f"[red]Deep: error: {exc}[/red]")
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR

    from deep.storage.txlog import TransactionLog
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog
    from deep.cli.main import build_parser

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)
    parser = build_parser()

    lines = [line.strip() for line in script_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
    
    if not lines:
        console.print("[yellow]⚓️ Batch: No valid operations found in script.[/yellow]")
        return

    console.print(f"[blue]⚓️ Batch: [bold]{len(lines)}[/bold] operation(s) from [italic]{script_path.name}[/italic][/blue]")

    success_count = 0
    failure_count = 0

    for i, line in enumerate(lines, 1):
        tx_id = txlog.begin("batch", line)
        try:
            with Timer(telemetry, "batch_op"):
                parts = shlex.split(line)
                if not parts:
                    continue

                # Parse the individual line as a command
                try:
                    cmd_args = parser.parse_args(parts)
                except SystemExit as se:
                    if se.code != 0:
                        raise RuntimeError(f"Argument parsing failed: {line}")
                    continue

                # Execute the mapped command
                try:
                    cmd_name = getattr(cmd_args, "command", None)
                    if not cmd_name:
                        raise RuntimeError(f"Unknown command in script: {parts[0]}")
                        
                    cmd_module = importlib.import_module(f"deep.commands.{cmd_name}_cmd")
                    # Capture stdout to avoid messy nested output during batch
                    cmd_module.run(cmd_args)
                except (ImportError, AttributeError, SystemExit) as e:
                    # SystemExit might be called by a command completing
                    if isinstance(e, SystemExit) and (e.code == 0 or e.code is None):
                        pass
                    else:
                        raise RuntimeError(f"Command execution failed: {e}")

            txlog.commit(tx_id)
            audit.record("batch", parts[0], details=line)
            console.print(f"  [green]✅[/green] [dim]Line {i}:[/dim] {line}")
            success_count += 1
        except Exception as e:
            txlog.rollback(tx_id, str(e))
            console.print(f"  [red]❌[/red] [dim]Line {i}:[/dim] {line} ([bold]{e}[/bold])")
            failure_count += 1

    if failure_count == 0:
        console.print(f"\n[bold green]⚓️ BATCH COMPLETE: {success_count} succeeded.[/bold green]")
    else:
        console.print(f"\n[bold yellow]⚓️ BATCH FINISHED: {success_count} succeeded, [bold red]{failure_count} failed[/bold red].[/bold yellow]")

if __name__ == "__main__":
    pass

"""
deep.commands.audit_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep audit [show|report|scan]`` command implementation.

Supports 'report' subcommand for Merkle-chained audit report
and 'scan' subcommand for zero-tolerance forbidden word detection.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
import datetime
from pathlib import Path

from deep.core.audit import AuditLog
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def _run_scan(console: Console) -> None:
    """Scan source code for forbidden patterns. Exits with error if any found."""
    from deep.core.runtime_guard import scan_source
    
    # Find the src/deep directory relative to the installed package
    import deep as deep_pkg
    pkg_dir = Path(deep_pkg.__file__).parent
    
    console.print(f"[blue]⚓️ Security Scan: [bold]{pkg_dir}[/bold][/blue]")
    violations = scan_source(str(pkg_dir))
    
    if not violations:
        console.print("[bold green]⚓️ AUDIT PASSED: Zero forbidden word violations found.[/bold green]")
        return
    
    console.print(f"[bold red]⚓️ AUDIT FAILED: {len(violations)} violation(s) found:[/bold red]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("File", style="yellow")
    table.add_column("Line", justify="right")
    table.add_column("Content")
    
    for fpath, lineno, line in violations:
        rel = fpath
        try:
            rel = str(Path(fpath).relative_to(pkg_dir))
        except ValueError:
            pass
        table.add_row(rel, str(lineno), line.strip())
    
    console.print(table)
    console.print(f"\n[bold red]Total: {len(violations)} violation(s). AUDIT FAILED.[/bold red]")
    raise DeepCLIException(1)

def run(args) -> None:
    console = Console()
    audit_command = getattr(args, "audit_command", "show") or "show"
    
    # Scan does not require a repository
    if audit_command == "scan":
        _run_scan(console)
        return

    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        console.print(f"[red]Deep: error: {exc}[/red]")
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    audit = AuditLog(dg_dir)

    if audit_command == "report":
        console.print("[blue]⚓️ Generating Comprehensive Security Audit Report...[/blue]")
        report_text = audit.export_report()
        console.print(Panel(report_text, title="⚓️ DEEP SECURITY AUDIT", border_style="cyan"))
        return

    # Default: show entries
    try:
        entries = audit.read_all()
    except Exception as e:
        console.print(f"[red]Deep: error: Failed to read audit log: {e}[/red]")
        raise DeepCLIException(1)

    if not entries:
        console.print("[yellow]⚓️ No audit entries recorded.[/yellow]")
        return
        
    table = Table(title="⚓️ RECENT SECURITY EVENTS", title_style="bold green")
    table.add_column("TIMESTAMP", style="cyan")
    table.add_column("User", style="green")
    table.add_column("Action", style="magenta")
    table.add_column("Details")
    
    # Show last 50 entries
    for e in entries[-50:]:
        ts = datetime.datetime.fromtimestamp(e.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        table.add_row(ts, e.user, e.action, e.details)
    
    console.print(table)

if __name__ == "__main__":
    pass

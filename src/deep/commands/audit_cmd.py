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
from pathlib import Path

from deep.core.audit import AuditLog
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description, Color
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'audit' command parser."""
    p_audit = subparsers.add_parser(
        "audit",
        help="Display the repository audit log",
        description=format_description("Browse through the cryptographically-signed audit logs of repository actions. Deep maintains a Merkle-chain of all significant events, allowing for zero-tolerance security auditing and verification of the repository's history."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep audit", "Display the 50 most recent audit log entries")}
{format_example("deep audit report", "Generate a cryptographically-verified Merkle-chain report")}
{format_example("deep audit scan", "Perform a high-security source code scan for forbidden patterns")}
""",
        formatter_class=DeepHelpFormatter,
    )
    # Define sub-commands as destinations
    p_audit.add_argument("audit_command", choices=["show", "report", "scan"], nargs="?", default="show", help="The audit action to perform (default: show)")


def _run_scan() -> None:
    """Scan source code for forbidden patterns. Exits with error if any found."""
    from deep.core.runtime_guard import scan_source
    
    # Find the src/deep directory relative to the installed package
    import deep as deep_pkg
    pkg_dir = Path(deep_pkg.__file__).parent
    
    print(f"Scanning: {pkg_dir}")
    violations = scan_source(str(pkg_dir))
    
    if not violations:
        print(Color.wrap(Color.SUCCESS, "✅ AUDIT PASSED: Zero forbidden word violations found."))
        return
    
    print(Color.wrap(Color.ERROR, f"❌ AUDIT FAILED: {len(violations)} violation(s) found:\n"))
    for fpath, lineno, line in violations:
        rel = fpath
        try:
            rel = str(Path(fpath).relative_to(pkg_dir))
        except ValueError:
            pass
        print(f"  {Color.wrap(Color.YELLOW, rel)}:{lineno}: {line}")
    
    print(f"\n{Color.wrap(Color.ERROR, f'Total: {len(violations)} violation(s). AUDIT FAILED.')}")
    raise DeepCLIException(1)


def run(args) -> None:
    audit_command = getattr(args, "audit_command", "show") or "show"
    
    # Scan does not require a repository
    if audit_command == "scan":
        _run_scan()
        return

    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    audit = AuditLog(dg_dir)

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
    
    for e in entries[-50:]:  # Show last 50
        import datetime
        ts = datetime.datetime.fromtimestamp(e.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts:<20} | {e.user:<15} | {e.action:<15} | {e.details}")

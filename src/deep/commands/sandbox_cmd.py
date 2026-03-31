"""
deep.commands.sandbox_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep sandbox run <script>`` — Execute scripts in a secure sandbox
with filesystem restrictions, timeout, and operation logging.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'sandbox' command parser."""
    p_sandbox = subparsers.add_parser(
        "sandbox",
        help="Manage isolated execution environments",
        description=format_description("Deep Sandbox provides a secure, isolated execution environment for running untrusted scripts, isolated builds, or experimental code. Sandboxes enforce filesystem restrictions, memory limits, and timeouts to protect the host system."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep sandbox run app.py", "Execute 'app.py' within a secure, restricted sandbox")}
{format_example("deep sandbox run build.sh --image ubuntu", "Run a build script in an Ubuntu container sandbox")}
{format_example("deep sandbox list", "Display all active and recently terminated sandboxes")}
{format_example("deep sandbox remove dev-env", "Permanently delete a specific sandbox environment")}
""",
        formatter_class=DeepHelpFormatter,
    )
    rs = p_sandbox.add_subparsers(dest="sandbox_command", metavar="ACTION")
    
    p_run = rs.add_parser("run", help="Execute code in a secure sandbox")
    p_run.add_argument("script", help="The script or command to execute in the sandbox")
    p_run.add_argument("--image", help="The container image to use (default: deep-minimal)")
    p_run.add_argument("--timeout", type=int, default=30, help="Execution timeout in seconds (default: 30)")
    
    rs.add_parser("list", help="List active and recent sandboxes")
    
    p_remove = rs.add_parser("remove", help="Remove a sandbox environment")
    p_remove.add_argument("name", help="The name of the sandbox to remove")


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    script_path = Path(args.script).resolve()

    if not script_path.exists():
        print(f"Deep: error: Script not found: {script_path}", file=sys.stderr)
        raise DeepCLIException(1)

    from deep.core.security import SandboxRunner

    # Setup allowed write paths
    allowed = [
        dg_dir / "wal",
        dg_dir / "tmp",
    ]
    (dg_dir / "tmp").mkdir(exist_ok=True)

    runner = SandboxRunner(dg_dir, allowed_write_paths=allowed)
    timeout = getattr(args, "timeout", 30) or 30

    print(f"🔒 Sandbox: Executing {script_path.name}")
    print(f"   Timeout: {timeout}s")
    print(f"   Allowed writes: {[str(p) for p in allowed]}")
    print("-" * 50)

    result = runner.run(script_path, timeout=timeout)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    print("-" * 50)
    print(f"  Exit code:  {result.exit_code}")
    print(f"  Duration:   {result.duration:.3f}s")
    print(f"  Timed out:  {'Yes ⚠' if result.timed_out else 'No'}")
    print(f"  Operations: {len(result.operations_log)} logged")

    # Log to audit
    from deep.core.audit import AuditLog
    audit = AuditLog(dg_dir)
    audit.record(
        user="sandbox",
        action="sandbox_exec",
        details=f"script={script_path.name} exit={result.exit_code} duration={result.duration:.3f}s",
    )

    status = "✅" if result.exit_code == 0 and not result.timed_out else "❌"
    print(f"\n  Sandbox: {status}")

"""
deep.commands.sandbox_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep sandbox run <script>`` — Execute scripts in a secure sandbox
with filesystem restrictions, timeout, and operation logging.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    script_path = Path(args.script).resolve()

    if not script_path.exists():
        print(f"Deep: error: Script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

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

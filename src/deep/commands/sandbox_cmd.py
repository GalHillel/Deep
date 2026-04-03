"""
deep.commands.sandbox_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep sandbox run <cmd>`` — Execute commands in a secure sandbox
with filesystem restrictions, timeout, and operation logging.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
import os
import tempfile
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    sandbox_dir = dg_dir / "sandbox"
    tmp_dir = dg_dir / "tmp"

    action = getattr(args, "sandbox_command", None)

    if action == "init":
        print(f"⚓️ Initializing sandbox environment in {sandbox_dir}")
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        # Ensure allowed paths exist
        (dg_dir / "wal").mkdir(parents=True, exist_ok=True)
        print("✅ Sandbox initialized.")
        return

    if action == "run":
        if not args.cmd:
            print("Deep: error: Missing command string for 'run' action.", file=sys.stderr)
            raise DeepCLIException(1)

        from deep.core.security import SandboxRunner

        # Setup allowed write paths
        allowed = [
            dg_dir / "wal",
            dg_dir / "tmp",
        ]
        tmp_dir.mkdir(exist_ok=True)

        runner = SandboxRunner(dg_dir, allowed_write_paths=allowed)
        timeout = getattr(args, "timeout", 30) or 30

        # Forensic handling of command vs script
        cmd_input = args.cmd
        if Path(cmd_input).is_file():
            script_path = Path(cmd_input).resolve()
            print(f"🔒 Sandbox: Executing script {script_path.name}")
        else:
            # Wrap shell command in a temporary Python script
            fd, temp_script = tempfile.mkstemp(suffix=".py", prefix="deep_sandbox_cmd_")
            with os.fdopen(fd, 'w') as f:
                f.write(f"import subprocess, sys\n")
                f.write(f"result = subprocess.run({repr(cmd_input)}, shell=True)\n")
                f.write(f"sys.exit(result.returncode)\n")
            script_path = Path(temp_script)
            print(f"🔒 Sandbox: Executing command \"{cmd_input}\"")

        print(f"   Timeout: {timeout}s")
        print(f"   Allowed writes: {[str(p) for p in allowed]}")
        print("-" * 50)

        try:
            result = runner.run(script_path, timeout=timeout)
        finally:
            # Cleanup temp script if we created one
            if "deep_sandbox_cmd_" in script_path.name:
                try:
                    script_path.unlink()
                except Exception:
                    pass

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
            details=f"cmd={cmd_input} exit={result.exit_code} duration={result.duration:.3f}s",
        )

        status = "✅" if result.exit_code == 0 and not result.timed_out else "❌"
        print(f"\n  Sandbox: {status}")
    else:
        print(f"Deep: error: Unknown sandbox action '{action}'", file=sys.stderr)
        raise DeepCLIException(1)

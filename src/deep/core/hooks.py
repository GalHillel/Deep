"""
deep.core.hooks
~~~~~~~~~~~~~~~

Repository hook system for extensibility.
Supports pre-commit, pre-push, post-merge, etc.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List

from deep.utils.utils import DeepError

class HookError(DeepError):
    """Raised when a hook fails."""
    pass

def run_hook(dg_dir: Path, hook_name: str, args: Optional[List[str]] = None) -> bool:
    """Run a repository hook script.
    
    Hooks are located in .deep/hooks/<hook_name>.
    On Windows, it looks for <hook_name>.bat, <hook_name>.exe, or <hook_name>.py.
    
    Args:
        dg_dir: Path to the .deep directory.
        hook_name: Name of the hook (e.g., 'pre-commit').
        args: Optional list of command-line arguments.
        
    Returns:
        True if the hook succeeded or doesn't exist.
        
    Raises:
        HookError: If the hook script fails (returns non-zero).
    """
    hooks_dir = dg_dir / "hooks"
    if not hooks_dir.exists():
        return True
        
    # Find the hook script
    hook_path = None
    possible_extensions = ["", ".bat", ".exe", ".py", ".cmd"]
    if sys.platform != "win32":
        possible_extensions = [""]
        
    for ext in possible_extensions:
        p = hooks_dir / f"{hook_name}{ext}"
        if p.exists() and (os.access(p, os.X_OK) or p.suffix == ".py"):
            hook_path = p
            break
            
    if not hook_path:
        return True
        
    cmd = [str(hook_path)]
    if hook_path.suffix == ".py":
        cmd = [sys.executable, str(hook_path)]
        
    if args:
        cmd.extend(args)
        
    try:
        # Run the hook
        result = subprocess.run(
            cmd,
            cwd=dg_dir.parent,
            capture_output=True,
            text=True,
            env={**os.environ, "DEEP_DIR": str(dg_dir)}
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise HookError(f"Hook '{hook_name}' failed (exit {result.returncode}):\n{error_msg}")
            
        return True
    except Exception as e:
        if isinstance(e, HookError):
            raise
        raise HookError(f"Failed to execute hook '{hook_name}': {e}")

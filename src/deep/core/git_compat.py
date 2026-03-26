"""
deep.core.git_compat
~~~~~~~~~~~~~~~~~~~~~
Utilities for Git coexistence.
"""

import os
import subprocess
from pathlib import Path
from typing import Set

def is_git_repository(path: Path) -> bool:
    """Check if the given path is inside a Git repository."""
    return (path / ".git").is_dir()

def get_git_tracked_files(repo_root: Path) -> Set[str]:
    """Return a set of relative paths tracked by Git."""
    if not is_git_repository(repo_root):
        return set()
    
    try:
        # We use git ls-files if available
        output = subprocess.check_output(
            ["git", "ls-files"], 
            cwd=repo_root, 
            stderr=subprocess.DEVNULL,
            encoding="utf-8"
        )
        return set(output.splitlines())
    except (subprocess.SubprocessError, FileNotFoundError):
        # Fallback: if Git is not installed, we can't accurately know
        return set()

def is_git_managed(repo_root: Path, rel_path: str, git_tracked: Set[str] = None) -> bool:
    """Check if a file is managed by Git.
    
    A file is managed by Git if:
    1. It is in the .git directory (skipped by status walk).
    2. It is tracked by Git.
    """
    if rel_path.startswith(".git/") or rel_path == ".git":
        return True
    
    if git_tracked is None:
        git_tracked = get_git_tracked_files(repo_root)
    
    # Standardize path for comparison if needed (git uses forward slashes)
    norm_path = rel_path.replace("\\", "/")
    return norm_path in git_tracked

"""
deep.core.platform
~~~~~~~~~~~~~~~~~~~~~~
Platform-level logic for managing multiple repositories on a DeepGit server.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

from deep.core.repository import DEEP_GIT_DIR

class PlatformManager:
    """Manages multiple repositories under a server root."""

    def __init__(self, server_root: Path):
        self.server_root = server_root
        self.repos_dir = server_root / "repos"
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def create_repo(self, name: str) -> Path:
        repo_path = self.repos_dir / name
        if repo_path.exists():
            raise ValueError(f"Repository '{name}' already exists.")
        
        # Internal init
        from deep.commands.init_cmd import run as init_run
        class Args:
            path = str(repo_path)
        
        init_run(Args())
        return repo_path

    def delete_repo(self, name: str):
        repo_path = self.repos_dir / name
        if not repo_path.exists():
            raise ValueError(f"Repository '{name}' does not exist.")
        shutil.rmtree(repo_path)

    def list_repos(self) -> List[str]:
        if not self.repos_dir.exists():
            return []
        return [d.name for d in self.repos_dir.iterdir() if d.is_dir() and (d / DEEP_GIT_DIR).exists()]

    def get_repo_path(self, name: str) -> Path:
        return self.repos_dir / name

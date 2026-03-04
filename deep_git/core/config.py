"""
deep_git.core.config
~~~~~~~~~~~~~~~~~~~~~
Configuration system for Deep Git.

Hierarchy:
1. Local: `.deep_git/config`
2. Global: `~/.deepgitconfig`
3. Defaults
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Optional

from deep_git.core.repository import DEEP_GIT_DIR


class Config:
    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.parser = configparser.ConfigParser()
        
        # Determine paths
        self.global_path = Path.home() / ".deepgitconfig"
        self.local_path = None
        if repo_root:
            self.local_path = repo_root / DEEP_GIT_DIR / "config"
            
        self.reload()

    def reload(self) -> None:
        """Reload configuration from disk. Local overrides global."""
        self.parser.clear()
        
        # Read in order so local overrides global
        paths_to_read = []
        if self.global_path.exists():
            paths_to_read.append(self.global_path)
            
        if self.local_path and self.local_path.exists():
            paths_to_read.append(self.local_path)
            
        self.parser.read(paths_to_read)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a configuration value, e.g. 'user.name'.
        
        If the key doesn't have a dot, it defaults to the 'core' section.
        """
        if "." in key:
            section, option = key.split(".", 1)
        else:
            section, option = "core", key
            
        return self.parser.get(section, option, fallback=default)

    def set_local(self, key: str, value: str) -> None:
        """Set a configuration value in the local repo config."""
        if not self.local_path:
            raise ValueError("Not in a deepgit repository")
            
        self._set_in_file(self.local_path, key, value)
        self.reload()

    def set_global(self, key: str, value: str) -> None:
        """Set a configuration value in the global config."""
        self._set_in_file(self.global_path, key, value)
        self.reload()

    def _set_in_file(self, config_file: Path, key: str, value: str) -> None:
        parser = configparser.ConfigParser()
        if config_file.exists():
            parser.read(config_file)
            
        if "." in key:
            section, option = key.split(".", 1)
        else:
            section, option = "core", key
            
        if not parser.has_section(section):
            parser.add_section(section)
            
        parser.set(section, option, value)
        
        # Use AtomicWriter or standard write
        from deep_git.core.utils import AtomicWriter
        # Need to write to string first
        import io
        buf = io.StringIO()
        parser.write(buf)
        with AtomicWriter(config_file, mode="w") as aw:
            aw.write(buf.getvalue())

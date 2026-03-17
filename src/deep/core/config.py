"""
deep.core.config
~~~~~~~~~~~~~~~~~~~~~
Configuration system for DeepBridge.

Hierarchy:
1. Local: `.deep/config`
2. Global: `~/.deepconfig`
3. Defaults
"""

from __future__ import annotations

import json
import configparser
from pathlib import Path
from typing import Optional

from deep.core.constants import DEEP_DIR # type: ignore


class Config:
    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.parser = configparser.ConfigParser()
        
        # Determine paths
        self.global_path = Path.home() / ".deepconfig"
        self.local_path = None
        if repo_root:
            self.local_path = repo_root / DEEP_DIR / "config"
            
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
            parts = key.split(".")
            if len(parts) > 2:
                section = ".".join(parts[:-1])
                option = parts[-1]
            else:
                section, option = parts
        else:
            section, option = "core", key
            
        return self.parser.get(section, option, fallback=default)

    def set_local(self, key: str, value: str) -> None:
        """Set a configuration value in the local repo config."""
        if not self.local_path:
            raise ValueError("Not in a deep repository")
            
        self._set_in_file(self.local_path, key, value)
        self.reload()

    def remove_local(self, section: str) -> None:
        """Remove a section from the local repo config."""
        if not self.local_path or not self.local_path.exists():
            return
            
        parser = configparser.ConfigParser()
        parser.read(self.local_path)
        if parser.has_section(section):
            parser.remove_section(section)
            
            import io
            buf = io.StringIO()
            parser.write(buf)
            from deep.utils.utils import AtomicWriter
            with AtomicWriter(self.local_path, mode="w") as aw:
                aw.write(buf.getvalue())
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
            # Handle remote.origin.url -> section 'remote.origin', option 'url'
            parts = key.split(".")
            if len(parts) > 2:
                section = ".".join(parts[:-1])
                option = parts[-1]
            else:
                section, option = parts
        else:
            section, option = "core", key
            
        if not parser.has_section(section):
            parser.add_section(section)
            
        parser.set(section, option, value)
        
        from deep.utils.utils import AtomicWriter
        import io
        buf = io.StringIO()
        parser.write(buf)
        with AtomicWriter(config_file, mode="w") as aw:
            aw.write(buf.getvalue())

def get_config(dg_dir: Path) -> dict[str, Any]:
    """Read the repository configuration file (INI format)."""
    # For backward compatibility with JSON-calling code, we return the 'core' section as a dict
    config = Config(dg_dir.parent)
    res = {}
    if config.parser.has_section("core"):
        res.update(dict(config.parser.items("core")))
    # Also include other sections if they look like simple keys
    for section in config.parser.sections():
        if section != "core":
            for k, v in config.parser.items(section):
                res[f"{section}.{k}"] = v
    return res

def set_config(dg_dir: Path, config_dict: dict[str, Any]) -> None:
    """Write the repository configuration file (INI format)."""
    config = Config(dg_dir.parent)
    for k, v in config_dict.items():
        config.set_local(k, str(v))

def is_partial_clone(dg_dir: Path) -> bool:
    """Check if the repository is a partial clone (has a promisor remote)."""
    config = Config(dg_dir.parent)
    return config.get("core.promisor") is not None or config.get("promisor") is not None

def get_promisor_remote(dg_dir: Path) -> Optional[str]:
    """Get the URL of the promisor remote if configured."""
    config = Config(dg_dir.parent)
    return config.get("core.promisor") or config.get("promisor")

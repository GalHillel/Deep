"""
deep.core.plugin
~~~~~~~~~~~~~~~~~~~~
Plugin management system.
Allows extending Deep with custom subcommands and lifecycle hooks.
Plugins are discovery from .deep/plugins/*.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

class PluginManager:
    """Discovers and loads Deep plugins."""
    
    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.plugin_dir = dg_dir / "plugins"
        self.commands: Dict[str, Callable] = {}
        self.hooks: Dict[str, list[Callable]] = {
            "pre-commit": [],
            "post-commit": [],
            "pre-push": []
        }

    def discover(self):
        """Scan for and load plugins."""
        if not self.plugin_dir.exists():
            return

        for p in self.plugin_dir.glob("*.py"):
            if p.name == "__init__.py":
                continue
            self._load_plugin(p)

    def _load_plugin(self, path: Path):
        """Import a single plugin file."""
        module_name = f"deep_plugin_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            return

        module = importlib.util.module_from_spec(spec)
        # Inject 'deep' into the module global namespace if needed
        # but usually plugins just import from deep.core
        
        # Add a reference to the manager so the plugin can register itself
        setattr(module, "__plugin_manager__", self)
        
        try:
            spec.loader.exec_module(module)
            # Plugins usually call manager.register_command or manager.register_hook in their top-level code
        except Exception as e:
            print(f"Error loading plugin {path.name}: {e}", file=sys.stderr)

    def register_command(self, name: str, handler: Callable, help_text: str = ""):
        """Register a new CLI subcommand."""
        self.commands[name] = handler
        # Note: Actual parser registration happens in main.py by iterating over this dict

    def register_hook(self, hook_name: str, callback: Callable):
        """Register a lifecycle hook."""
        if hook_name in self.hooks:
            self.hooks[hook_name].append(callback)

    def run_hooks(self, hook_name: str, *args, **kwargs):
        """Execute all callbacks for a given hook."""
        for cb in self.hooks.get(hook_name, []):
            try:
                cb(*args, **kwargs)
            except Exception as e:
                print(f"Error in {hook_name} hook: {e}", file=sys.stderr)

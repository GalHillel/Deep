"""
tests.test_plugins
~~~~~~~~~~~~~~~~~~
Tests for Phase 10 features:
1. Plugin discovery
2. Custom command registration
3. Lifecycle hooks (pre-commit, post-commit)
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from deep.cli.main import main
from deep.core.repository import DEEP_DIR

def test_plugin_discovery_and_command(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    os.chdir(repo)
    main(["init"])
    
    # Create a plugin
    plugin_dir = repo / DEEP_DIR / "plugins"
    plugin_dir.mkdir()
    
    plugin_code = """
def my_command(args):
    print(f"HELLO FROM PLUGIN: {args}")

__plugin_manager__.register_command("hello-plugin", my_command)
"""
    (plugin_dir / "my_plugin.py").write_text(plugin_code)
    
    # Run the plugin command
    from io import StringIO
    import sys
    
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    try:
        # Note: In a real process, main() would reload pm. 
        # In this test, we call main which should rediscover.
        main(["hello-plugin", "arg1", "arg2"])
    finally:
        sys.stdout = old_stdout
        
    output = mystdout.getvalue()
    assert "HELLO FROM PLUGIN: ['arg1', 'arg2']" in output

def test_plugin_hooks(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    os.chdir(repo)
    main(["init"])
    
    plugin_dir = repo / DEEP_DIR / "plugins"
    plugin_dir.mkdir()
    
    log_file = repo / "hook_log.txt"
    
    plugin_code = f"""
def pre_hook(repo_root, message):
    with open(r"{log_file}", "a") as f:
        f.write(f"PRE: {{message}}\\n")

def post_hook(repo_root, sha, message):
    with open(r"{log_file}", "a") as f:
        f.write(f"POST: {{sha[:7]}}\\n")

__plugin_manager__.register_hook("pre-commit", pre_hook)
__plugin_manager__.register_hook("post-commit", post_hook)
"""
    (plugin_dir / "hook_plugin.py").write_text(plugin_code)
    
    # Trigger hooks via commit
    (repo / "f.txt").write_text("content")
    main(["add", "f.txt"])
    main(["commit", "-m", "test-hook"])
    
    log_content = log_file.read_text()
    assert "PRE: test-hook" in log_content
    assert "POST: " in log_content # Should have a short SHA

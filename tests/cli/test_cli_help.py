import subprocess
import pytest
import sys

from deep.cli.main import main

COMMANDS = [
    "init", "add", "commit", "status", "log", "diff", "branch", "checkout",
    "merge", "rebase", "reset", "rm", "mv", "tag", "stash", "clone", "push",
    "pull", "fetch", "remote", "mirror", "daemon", "p2p", "sync", "server",
    "repo", "user", "auth", "pr", "issue", "pipeline", "studio", "audit", "doctor",
    "verify", "search", "ai", "ultra", "gc", "graph", "batch", "rollback",
    "sandbox", "fsck", "inspect-tree"
]

@pytest.mark.parametrize("cmd", COMMANDS)
def test_cli_help_text(cmd):
    """Verify that each command accepts --help and returns 0."""
    # We use main() directly to avoid subprocess overhead and capture output
    try:
        main([cmd, "--help"])
    except SystemExit as e:
        assert e.code == 0, f"Command 'deep {cmd} --help' exited with code {e.code}"

def test_cli_root_help():
    """Verify root level help."""
    try:
        main(["--help"])
    except SystemExit as e:
        assert e.code == 0

def test_cli_version():
    """Verify version command."""
    try:
        main(["version"])
    except SystemExit as e:
        assert e.code == 0

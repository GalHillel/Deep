"""
deep.commands.ls_remote_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep ls-remote <url>`` command implementation.

Uses native smart protocol (SSH/HTTPS) for remote ref discovery.
No external VCS CLI dependency.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.refs import list_branches, list_tags, get_branch, get_tag
from deep.core.constants import DEEP_DIR
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'ls-remote' command parser."""
    p_ls_remote = subparsers.add_parser(
        "ls-remote",
        help="List references in a remote repository",
        description="Displays the references (branches, tags) available at a remote URL.",
        epilog=f"""
Examples:
{format_example("deep ls-remote origin", "List refs from 'origin'")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_ls_remote.add_argument("url", help="The remote URL or name to query")


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``ls-remote`` command."""
    url = args.url
    repo_root = None
    try:
        from deep.core.repository import find_repo
        repo_root = find_repo()
    except Exception:
        pass

    if repo_root:
        from deep.core.config import Config
        config = Config(repo_root)
        url = config.get(f"remote.{url}.url", url)

    # Check if it's a local path first
    target = Path(url).resolve()
    if (target / DEEP_DIR).exists():
        _ls_remote_local(target / DEEP_DIR)
        return
    if target.name == DEEP_DIR or target.suffix == ".deep":
        if target.exists():
            _ls_remote_local(target)
            return

    # Remote URL — use smart protocol
    try:
        from deep.network.client import get_remote_client
        client = get_remote_client(url)
        refs = client.ls_remote()

        if not refs:
            print("(empty repository)", file=sys.stderr)
            return

        for ref_name in sorted(refs.keys()):
            sha = refs[ref_name]
            print(f"{sha}\t{ref_name}")

    except Exception as e:
        print(f"Deep: error: ls-remote failed: {e}", file=sys.stderr)
        raise DeepCLIException(1)


def _ls_remote_local(dg_dir: Path) -> None:
    """List refs from a local repository."""
    # Debug
    print(f"DEBUG: ls-remote-local dg_dir={dg_dir}", file=sys.stderr)
    from deep.core.refs import resolve_head
    head_sha = resolve_head(dg_dir)
    if head_sha:
        print(f"{head_sha}\tHEAD")
        
    for branch in list_branches(dg_dir):
        sha = get_branch(dg_dir, branch)
        if sha:
            print(f"{sha}\trefs/heads/{branch}")

    for tag in list_tags(dg_dir):
        sha = get_tag(dg_dir, tag)
        if sha:
            print(f"{sha}\trefs/tags/{tag}")

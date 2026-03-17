"""
deep.commands.ls_remote_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep ls-remote <url>`` command implementation.
Outputs available references (branches, tags) and their target SHAs locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.refs import list_branches, list_tags, get_branch, get_tag
from deep.core.constants import DEEP_DIR

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``ls-remote`` command."""
    url = args.url
    
    # If it's a local path, try to read the refs directly.
    target = Path(url).resolve()
    if (target / DEEP_DIR).exists():
        dg_dir = target / DEEP_DIR
    elif target.name == DEEP_DIR or target.suffix == ".deep":
        dg_dir = target
    else:
        print(f"Deep: error: ls-remote only supports local paths in this mock implementation. URL given: {url}", file=sys.stderr)
        sys.exit(1)
        
    if not dg_dir.exists():
        print(f"Deep: error: repository not found at {url}", file=sys.stderr)
        sys.exit(1)
        
    for branch in list_branches(dg_dir):
        sha = get_branch(dg_dir, branch)
        if sha:
            print(f"{sha}\trefs/heads/{branch}")
            
    for tag in list_tags(dg_dir):
        sha = get_tag(dg_dir, tag)
        if sha:
            print(f"{sha}\trefs/tags/{tag}")

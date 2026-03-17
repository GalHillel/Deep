"""
deep.commands.pr_cmd
~~~~~~~~~~~~~~~~~~~~~~~~
``deep pr`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_DIR, find_repo
from deep.core.pr import PRManager
from deep.utils.ux import Color
from deep.core.config import Config

def run(args) -> None:
    """Execute the ``pr`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print("DeepGit: error: Not a DeepGit repository.", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    manager = PRManager(dg_dir)
    config = Config(repo_root)
    author = config.get("user.name") or "unknown"
    
    cmd = getattr(args, "pr_command", "list")
    
    if cmd == "create":
        # Need extra args for create: --title, --source, --target, --desc
        title = getattr(args, "title", "Untitled PR")
        source = getattr(args, "source", "feature")
        target = getattr(args, "target", "main")
        desc = getattr(args, "description", "")
        
        pr = manager.create_pr(title, author, source, target, desc)
        print(Color.wrap(Color.GREEN, f"Pull Request #{pr.id} created: {pr.title}"))
        print(f"  {pr.source_branch} -> {pr.target_branch}")
        
    elif cmd == "list":
        prs = manager.list_prs()
        if not prs:
            print("No open pull requests.")
            return
        print(f"{'ID':<5} {'Status':<10} {'Author':<15} {'Title'}")
        print("-" * 60)
        for pr in prs:
            col = Color.GREEN if pr.status == 'open' else Color.DIM
            print(f"#{pr.id:<4} {Color.wrap(col, pr.status):<10} {pr.author:<15} {pr.title}")
            
    elif cmd == "merge":
        pr_id = int(args.pr_id)
        try:
            pr = manager.merge_pr(pr_id)
            print(Color.wrap(Color.PURPLE, f"Pull Request #{pr.id} merged successfully!"))
        except ValueError as e:
            print(f"DeepGit: error: {e}", file=sys.stderr)
            sys.exit(1)

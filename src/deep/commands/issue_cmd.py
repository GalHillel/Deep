"""
deep.commands.issue_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep issue`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.issue import IssueManager
from deep.utils.ux import Color
from deep.core.config import Config

def run(args) -> None:
    """Execute the ``issue`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print("Deep: error: Not a Deep repository.", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    manager = IssueManager(dg_dir)
    config = Config(repo_root)
    author = config.get("user.name") or "unknown"
    
    cmd = getattr(args, "issue_command", "list")
    
    if cmd == "create":
        title = getattr(args, "title", "Untitled Issue")
        desc = getattr(args, "description", "")
        assignee = getattr(args, "assignee", None)
        labels = getattr(args, "labels", None)
        if labels:
            labels = labels.split(",")
            
        issue = manager.create_issue(title, author, desc, assignee, labels)
        print(Color.wrap(Color.GREEN, f"Issue #{issue.id} created: {issue.title}"))
        
    elif cmd == "list":
        issues = manager.list_issues()
        if not issues:
            print("No open issues.")
            return
        print(f"{'ID':<5} {'Status':<10} {'Assignee':<15} {'Title'}")
        print("-" * 60)
        for issue in issues:
            col = Color.GREEN if issue.status == 'open' else Color.DIM
            assign = issue.assignee or "unassigned"
            print(f"#{issue.id:<4} {Color.wrap(col, issue.status):<10} {assign:<15} {issue.title}")
            
    elif cmd == "close":
        issue_id = int(args.issue_id)
        try:
            issue = manager.close_issue(issue_id)
            print(Color.wrap(Color.YELLOW, f"Issue #{issue.id} closed."))
        except ValueError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)

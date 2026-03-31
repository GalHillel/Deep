"""
deep.commands.issue_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Smart, production-grade hybrid issue management engine.
"""
from deep.core.pr import PR
from deep.storage.objects import Commit
from deep.utils.ux import Color
from deep.utils.ux import print_error
from deep.utils.ux import print_info
from deep.utils.ux import print_success
from deep.utils.ux import print_warning

from __future__ import annotations
import json
import os
import sys
import time
import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from deep.core.config import Config
from deep.core.repository import find_repo
from deep.core.constants import DEEP_DIR
from deep.core.issue import IssueManager, Issue
from deep.utils.ux import (
    Color, print_error, print_success, print_info, print_warning
)
import argparse
from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'issue' command parser."""
    p_issue = subparsers.add_parser(
        "issue",
        help="Manage repository issues",
        description="""Deep Issue tracking allows for local-first, decentralized task management.

Issues are stored as objects in your repository and can be synchronized with GitHub or other Deep instances.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep issue create\033[0m
     Open an interactive template to create a new issue
  \033[1;34m⚓️ deep issue list\033[0m
     Display all open issues in the current repository
  \033[1;34m⚓️ deep issue show 12\033[0m
     Show full details and timeline for Issue #12
  \033[1;34m⚓️ deep issue close 12\033[0m
     Mark Issue #12 as resolved/closed
  \033[1;34m⚓️ deep issue sync\033[0m
     Synchronize local issues with the remote platform
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    rs = p_issue.add_subparsers(dest="issue_command", metavar="ACTION")
    
    # Core Actions
    p_create = rs.add_parser("create", help="Create a new issue")
    p_create.add_argument("--title", help="Short summary of the issue")
    p_create.add_argument("--type", choices=["bug", "feature", "task"], default="bug", help="The type of issue (bug, feature, task)")
    
    rs.add_parser("list", help="List all issues in the repository")
    
    p_show = rs.add_parser("show", help="Show detailed information for an issue")
    p_show.add_argument("id", help="The ID of the issue to display")
    
    # Workflow Actions
    p_close = rs.add_parser("close", help="Mark an issue as closed")
    p_close.add_argument("id", help="The ID of the issue to close")
    
    p_reopen = rs.add_parser("reopen", help="Reopen a closed issue")
    p_reopen.add_argument("id", help="The ID of the issue to reopen")
    
    rs.add_parser("sync", help="Synchronize local issues with remote (GitHub/Deep)")

def get_author(repo_root: Path) -> str:
    """Get the current user name from config."""
    config = Config(repo_root)
    name = config.get("user.name")
    if name:
        return name
    try:
        return os.getlogin()
    except Exception:
        return "unknown"

def interactive_create(manager: IssueManager, repo_root: Path) -> Issue:
    """Smart interactive issue creation flow."""
    is_interactive = sys.stdin.isatty()
    if not is_interactive:
        # Should not be reached if run() handles it, but safety first
        return manager.create_issue("New Issue", "Auto Description", "bug", get_author(repo_root))

    print(Color.wrap(Color.CYAN, "\n--- Create Issue ---"))
    
    print("\nSelect issue type:")
    print(f"1. {Color.wrap(Color.RED, 'Bug')}")
    print(f"2. {Color.wrap(Color.CYAN, 'Feature')}")
    print(f"3. {Color.wrap(Color.YELLOW, 'Task')}")
    
    choice = input("\nSelect [1-3]: ").strip()
    if choice == "1":
        itype = "bug"
    elif choice == "2":
        itype = "feature"
    else:
        itype = "task"
    
    print(f"\nCreating {Color.wrap(Color.BOLD, itype.upper())}...")
    
    title = input(f"{Color.wrap(Color.BOLD, 'Title')}: ").strip()
    
    description = ""
    if itype == "bug":
        steps = input("Steps to reproduce: ").strip()
        expected = input("Expected behavior: ").strip()
        actual = input("Actual behavior: ").strip()
        description = f"[BUG]\nSteps:\n{steps}\n\nExpected:\n{expected}\n\nActual:\n{actual}"
    elif itype == "feature":
        problem = input("What problem does this solve? ").strip()
        solution = input("Proposed solution: ").strip()
        description = f"[FEATURE]\nProblem:\n{problem}\n\nSolution:\n{solution}"
    else:
        details = input("Details: ").strip()
        description = details

    # Smart Suggestions
    if not title and description:
        title = description.split('\n')[0][:50]
        if len(description.split('\n')[0]) > 50:
            title += "..."
        print_info(f"Auto-generated title: {title}")
    
    if not title:
        print_error("Title cannot be empty.")
        raise DeepCLIException(1)
    
    if len(description) < 10:
        warn = input(Color.wrap(Color.YELLOW, "Description is very short. Continue? [y/N]: ")).strip().lower()
        if warn != 'y':
            print("Aborted.")
            raise DeepCLIException(0)

    author = get_author(repo_root)
    issue = manager.create_issue(title, description, itype, author)
    manager.add_event(issue.id, author, "created", f"Issue created via CLI")
    
    # Optional GitHub Sync
    gh_repo = net.get_github_remote(repo_root)
    if gh_repo:
        push = input(f"Push issue to GitHub ({gh_repo})? [y/N]: ").strip().lower()
        if push == 'y':
            token = net.get_token()
            if not token:
                print_error("GitHub token (GH_TOKEN or DEEP_TOKEN) required for push.")
            else:
                print_info("Pushing to GitHub...")
                res = net.api_request(f"repos/{gh_repo}/issues", method="POST", data={
                    "title": title,
                    "body": description
                })
                if res and isinstance(res, dict) and "html_url" in res:
                    print_success(f"✔ GitHub Issue created")
                    print(f"  URL: {res['html_url']}")
                else:
                    print_error("Failed to push to GitHub.")

    return issue

def run(args: Any) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print_error("Not a Deep repository.")
        raise DeepCLIException(1)

    manager = IssueManager(repo_root / DEEP_DIR)
    cmd = getattr(args, "issue_command", "list")

    if cmd == "create":
        title = getattr(args, "title", None)
        itype = getattr(args, "type", "bug")
        
        if title:
            # Non-interactive creation
            author = get_author(repo_root)
            issue = manager.create_issue(title, "", itype, author)
            manager.add_event(issue.id, author, "created", "Issue created via CLI")
            print_success(f"Issue #{issue.id} created locally (non-interactive).")
        else:
            try:
                issue = interactive_create(manager, repo_root)
                print_success(f"Issue #{issue.id} created locally.")
            except KeyboardInterrupt:
                print("\nAborted.")
                return

    elif cmd == "list":
        issues = manager.list_issues()
        if not issues:
            print_info("No issues found.")
            return

        print(f"\n{Color.wrap(Color.BOLD, 'Issues:')}")
        for issue in issues:
            status_col = Color.GREEN if issue.status == "open" else Color.RED
            type_col = Color.RED if issue.type == "bug" else (Color.CYAN if issue.type == "feature" else Color.YELLOW)
            
            print(f"#{issue.id:<3} [{Color.wrap(status_col, issue.status.upper())}]   "
                  f"{Color.wrap(type_col, issue.type.lower()):<8} "
                  f"{issue.title}")
        print()

    elif cmd == "show":
        if not args.id:
            print_error("Usage: deep issue show <id>")
            return
        
        try:
            issue = manager.get_issue(int(args.id))
        except (ValueError, TypeError):
            print_error(f"Invalid ID: {args.id}")
            return

        if not issue:
            print_error(f"Issue #{args.id} not found.")
            return

        status_col = Color.GREEN if issue.status == "open" else Color.RED
        print(f"\n=== Issue #{issue.id} ===")
        print(f"Type:   {issue.type.upper()}")
        print(f"Status: {Color.wrap(status_col, issue.status.upper())}")
        print(f"Author: {issue.author}")
        print(f"Title:  {issue.title}")
        print("-" * 20)
        print(issue.description)
        print("-" * 20)

        if issue.linked_prs:
            print(f"Linked PRs: {', '.join(f'#{pr_id}' for pr_id in issue.linked_prs)}")

        if issue.events:
            print(f"\nTimeline:")
            for event in issue.events:
                ts = event.get("timestamp", "")
                if ts:
                    try:
                        dt = datetime.datetime.fromisoformat(ts)
                        ts = dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass
                
                ev_type = event.get("event", "unknown")
                if ev_type == "created":
                    print(f"  - {ts} Created")
                elif ev_type == "linked_pr":
                    print(f"  - {ts} PR #{event.get('pr')} linked")
                elif ev_type == "closed_by_pr":
                    print(f"  - {ts} PR #{event.get('pr')} merged, issue closed")
                elif ev_type == "commit_linked":
                    sha = event.get("sha", "unknown")[:7]
                    print(f"  - {ts} Commit {sha} added")
                elif ev_type == "closed":
                    print(f"  - {ts} Issue closed")
                elif ev_type == "reopened":
                    print(f"  - {ts} Issue reopened")
                elif ev_type == "thread_created":
                    print(f"  - {ts} Thread #{event.get('thread')} started (PR #{event.get('pr')})")
                elif ev_type == "reply_added":
                    print(f"  - {ts} Reply added to Thread #{event.get('thread')} (PR #{event.get('pr')})")
                elif ev_type == "thread_resolved":
                    print(f"  - {ts} Thread #{event.get('thread')} resolved (PR #{event.get('pr')})")
                elif ev_type == "review_added":
                    print(f"  - {ts} PR #{event.get('pr')} reviewed: {Color.wrap(Color.BOLD, event.get('status', '').upper())}")
                elif ev_type == "review_updated":
                    print(f"  - {ts} PR #{event.get('pr')} review updated: {Color.wrap(Color.BOLD, event.get('status', '').upper())}")
                else:
                    print(f"  - {ts} {ev_type.replace('_', ' ').capitalize()}")
        print("")

    elif cmd == "close":
        if not args.id:
            print_error("Usage: deep issue close <id>")
            return
        try:
            manager.close_issue(int(args.id))
            print_success(f"Issue #{args.id} closed.")
        except Exception as e:
            print_error(str(e))

    elif cmd == "reopen":
        if not args.id:
            print_error("Usage: deep issue reopen <id>")
            return
        try:
            manager.reopen_issue(int(args.id))
            print_success(f"Issue #{args.id} reopened.")
        except Exception as e:
            print_error(str(e))
    else:
        print_error(f"Unknown command: {cmd}")

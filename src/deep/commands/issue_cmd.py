"""
deep.commands.issue_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Smart, production-grade hybrid issue management engine.
"""

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
from deep.utils.ux import Color, print_error, print_success, print_info, print_warning
from deep.core.errors import DeepCLIException
from deep.core.issue import IssueManager, Issue
import deep.utils.network as net

def get_description() -> str:
    return "Smart, production-grade hybrid issue management engine."

def get_epilog() -> str:
    examples_title = Color.wrap(Color.CYAN, "Examples:")
    create_ex = f"  {Color.wrap(Color.YELLOW, 'deep issue create')}   {Color.wrap(Color.GREEN, '# Interactive smart creation')}"
    list_ex   = f"  {Color.wrap(Color.YELLOW, 'deep issue list')}     {Color.wrap(Color.GREEN, '# List local issues with status colors')}"
    show_ex   = f"  {Color.wrap(Color.YELLOW, 'deep issue show 1')}   {Color.wrap(Color.GREEN, '# Show issue details')}"
    close_ex  = f"  {Color.wrap(Color.YELLOW, 'deep issue close 1')}  {Color.wrap(Color.GREEN, '# Close an issue')}"
    
    return f"\n{examples_title}\n{create_ex}\n{list_ex}\n{show_ex}\n{close_ex}\n"

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
    manager.add_timeline_event(issue.id, "created")
    
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

    manager = IssueManager(repo_root / ".deep")
    cmd = getattr(args, "issue_command", "list")

    if cmd == "create":
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

        if issue.timeline:
            print(f"\nTimeline:")
            for event in issue.timeline:
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
                else:
                    print(f"  - {ts} {ev_type.capitalize()}")
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

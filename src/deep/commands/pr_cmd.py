"""
deep.commands.pr_cmd
~~~~~~~~~~~~~~~~~~~~~~~~
``deep pr`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.pr import PRManager
from deep.core.config import Config
from deep.utils.ux import Color, print_error, print_success, print_info
import deep.utils.network as net

def get_description() -> str:
    """Return a color-coded description for the pr command."""
    return "Manage Pull Requests locally and optionally sync with GitHub."

def get_epilog() -> str:
    """Return a color-coded epilog with usage examples."""
    examples_title = Color.wrap(Color.CYAN, "Examples:")
    note_title = Color.wrap(Color.RED, "Note:")
    
    create_ex  = f"  {Color.wrap(Color.YELLOW, 'deep pr create')}      {Color.wrap(Color.GREEN, '# Open a new PR interactively')}"
    list_ex    = f"  {Color.wrap(Color.YELLOW, 'deep pr list')}        {Color.wrap(Color.GREEN, '# List all local PRs')}"
    show_ex    = f"  {Color.wrap(Color.YELLOW, 'deep pr show 3')}      {Color.wrap(Color.GREEN, '# Show details for PR #3')}"
    close_ex   = f"  {Color.wrap(Color.YELLOW, 'deep pr close 3')}     {Color.wrap(Color.GREEN, '# Close PR #3')}"
    merge_ex   = f"  {Color.wrap(Color.YELLOW, 'deep pr merge 3')}     {Color.wrap(Color.GREEN, '# Merge PR #3')}"
    sync_ex    = f"  {Color.wrap(Color.YELLOW, 'deep pr sync')}        {Color.wrap(Color.GREEN, '# Sync local PRs with GitHub')}"
    
    token_ex  = f"\n{Color.wrap(Color.CYAN, 'Setup Token (Windows):')}\n" \
                f"  {Color.wrap(Color.YELLOW, '$env:GH_TOKEN=\"...\"')}  {Color.wrap(Color.GREEN, '# PowerShell')}\n" \
                f"  {Color.wrap(Color.YELLOW, 'set GH_TOKEN=...')}      {Color.wrap(Color.GREEN, '# CMD')}"

    sync_note = f"\n{note_title} 'sync' requires a GitHub remote and GH_TOKEN/DEEP_TOKEN. \n      Without these, all operations remain local-only."
    
    return f"\n{examples_title}\n{create_ex}\n{list_ex}\n{show_ex}\n{close_ex}\n{merge_ex}\n{sync_ex}\n{token_ex}\n{sync_note}\n"

def run(args) -> None:
    """Execute the ``pr`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print_error("Not a Deep repository.")
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    manager = PRManager(dg_dir)
    config = Config(repo_root)
    verbose = getattr(args, "verbose", False)
    
    cmd = getattr(args, "pr_command", "list")
    
    if cmd == "create":
        title = getattr(args, "title", None)
        desc = getattr(args, "description", None)
        source = getattr(args, "source", "feature")
        target = getattr(args, "target", "main")
        
        if not title:
            print_info("Creating new Pull Request...")
            title = input("PR Title: ").strip()
            if not desc:
                desc = input("Description (optional): ").strip()
        
        if not title:
            print_error("PR Title cannot be empty.")
            raise DeepCLIException(1)
            
        author = config.get("user.name") or "unknown"
        pr = manager.create_pr(title, author, source, target, desc or "")
        print_success(f"Pull Request #{pr.id} created locally: {pr.title}")
        print(f"  {pr.source_branch} -> {pr.target_branch}")
        
    elif cmd == "list":
        prs = manager.list_prs()
        print(Color.wrap(Color.CYAN, f"\nRepository: {repo_root}"))
        open_count = len([p for p in prs if p.status == "open"])
        print(Color.wrap(Color.CYAN, f"Pull Requests: {len(prs)} total | {open_count} open\n"))
        
        if not prs:
            print("No pull requests found.")
            return

        print(f"{'ID':<5} {'Status':<10} {'Author':<15} {'Branches'}")
        print("-" * 75)
        for pr in prs:
            if pr.status == "open":
                col = Color.GREEN
            elif pr.status == "merged":
                col = Color.PURPLE
            else:
                col = Color.RED
            
            branches = f"{pr.source_branch} -> {pr.target_branch}"
            print(f"#{pr.id:<4} {Color.wrap(col, pr.status.upper()):<10} {pr.author:<15} {branches}")
            print(f"      {pr.title}\n")
            
    elif cmd == "show":
        if not args.id:
            print_error("Missing PR ID.")
            raise DeepCLIException(1)
        
        try:
            pr_id = int(args.id)
        except ValueError:
            print_error(f"Invalid ID: {args.id}")
            raise DeepCLIException(1)
            
        pr = manager.get_pr(pr_id)
        if not pr:
            print_error(f"PR #{pr_id} not found locally.")
            raise DeepCLIException(1)
            
        if pr.status == "open":
            col = Color.GREEN
        elif pr.status == "merged":
            col = Color.PURPLE
        else:
            col = Color.RED

        print(Color.wrap(Color.CYAN, f"\nPR #{pr.id}: {pr.title}"))
        print(Color.wrap(Color.CYAN, "-" * 65))
        print(f"Status:   {Color.wrap(col, pr.status.upper())}")
        print(f"Author:   {pr.author}")
        print(f"Branches: {pr.source_branch} -> {pr.target_branch}")
        if pr.github_id:
            print(f"GitHub:   #{pr.github_id}")
        print(f"\n{Color.wrap(Color.BOLD, 'Description:')}")
        print(f"{pr.description or 'No description provided.'}\n")

    elif cmd in ("close", "reopen", "merge"):
        if not args.id:
            print_error(f"Missing PR ID for {cmd}.")
            raise DeepCLIException(1)
        
        try:
            pr_id = int(args.id)
        except ValueError:
            print_error(f"Invalid ID: {args.id}")
            raise DeepCLIException(1)

        try:
            if cmd == "close":
                pr = manager.close_pr(pr_id)
            elif cmd == "reopen":
                pr = manager.reopen_pr(pr_id)
            else:
                pr = manager.merge_pr(pr_id)
            print_success(f"Pull Request #{pr_id} is now {pr.status}.")
        except ValueError as e:
            print_error(str(e))
            raise DeepCLIException(1)

    elif cmd == "sync":
        gh_repo = net.get_github_remote(repo_root)
        token = net.get_token()
        
        if not gh_repo or not token:
            print_error("Sync requires a GitHub remote and GH_TOKEN.")
            raise DeepCLIException(1)
            
        print_info(f"Syncing local PRs with {gh_repo}...")
        prs = manager.list_prs()
        synced_count = 0
        for pr in prs:
            if not pr.github_id:
                # Create on GitHub
                path = f"{gh_repo}/pulls"
                res = net.api_request(path, method="POST", data={
                    "title": pr.title,
                    "body": pr.description,
                    "head": pr.source_branch,
                    "base": pr.target_branch
                }, verbose=verbose)
                
                if res and isinstance(res, dict) and "number" in res:
                    pr.github_id = res["number"]
                    manager.save_pr(pr)
                    synced_count += 1
            else:
                # Update state on GitHub if closed/merged
                path = f"{gh_repo}/pulls/{pr.github_id}"
                if pr.status == "closed":
                    net.api_request(path, method="PATCH", data={"state": "closed"}, verbose=verbose)
                elif pr.status == "merged":
                    # GitHub merge is separate
                    merge_path = f"{path}/merge"
                    net.api_request(merge_path, method="PUT", data={}, verbose=verbose)
                synced_count += 1

        print_success(f"Successfully synced {synced_count} PRs with GitHub.")

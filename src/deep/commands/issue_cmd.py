"""
deep.commands.issue_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Hybrid Local + GitHub Issue Management for Deep.
"""

from __future__ import annotations
import urllib.request
import urllib.error
import json
import os
import sys
import re
import time
import shutil
from typing import Dict, Any, List, Optional
from pathlib import Path

from deep.core.config import Config
from deep.core.repository import find_repo
from deep.utils.ux import Color, print_error, print_success, print_info
from deep.core.errors import DeepCLIException
import deep.utils.network as net

def get_description() -> str:
    """Return a color-coded description for the issue command."""
    return "Manage issues locally and optionally sync with GitHub."

def get_epilog() -> str:
    """Return a color-coded epilog with usage examples."""
    examples_title = Color.wrap(Color.CYAN, "Examples:")
    note_title = Color.wrap(Color.RED, "Note:")
    
    # Use Color.wrap for all examples as requested
    create_ex = f"  {Color.wrap(Color.YELLOW, 'deep issue create')}   {Color.wrap(Color.GREEN, '# Create a new issue interactively')}"
    list_ex   = f"  {Color.wrap(Color.YELLOW, 'deep issue list')}     {Color.wrap(Color.GREEN, '# List all local issues')}"
    show_ex   = f"  {Color.wrap(Color.YELLOW, 'deep issue show 5')}   {Color.wrap(Color.GREEN, '# Show detailed info for issue #5')}"
    close_ex  = f"  {Color.wrap(Color.YELLOW, 'deep issue close 5')}  {Color.wrap(Color.GREEN, '# Close issue #5')}"
    reopen_ex = f"  {Color.wrap(Color.YELLOW, 'deep issue reopen 5')} {Color.wrap(Color.GREEN, '# Reopen issue #5')}"
    sync_ex   = f"  {Color.wrap(Color.YELLOW, 'deep issue sync')}     {Color.wrap(Color.GREEN, '# Sync local issues with GitHub')}"
    
    token_ex  = f"\n{Color.wrap(Color.CYAN, 'Setup Token (Windows):')}\n" \
                f"  {Color.wrap(Color.YELLOW, '$env:GH_TOKEN=\"...\"')}  {Color.wrap(Color.GREEN, '# PowerShell')}\n" \
                f"  {Color.wrap(Color.YELLOW, 'set GH_TOKEN=...')}      {Color.wrap(Color.GREEN, '# CMD')}"

    sync_note = f"\n{note_title} 'sync' requires a GitHub remote and GH_TOKEN/DEEP_TOKEN. \n      Without these, all operations remain local-only."
    
    return f"\n{examples_title}\n{create_ex}\n{list_ex}\n{show_ex}\n{close_ex}\n{reopen_ex}\n{sync_ex}\n{token_ex}\n{sync_note}\n"

class LocalIssueManager:
    """Manages local persistent issue storage in .deep/issues.json."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.issue_file = repo_root / ".deep" / "issues.json"
        self.dg_dir = repo_root / ".deep"
        
    def _ensure_dir(self):
        if not self.dg_dir.exists():
            self.dg_dir.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> List[Dict[str, Any]]:
        """Load all issues from the local JSON file."""
        if not self.issue_file.exists():
            return []
        try:
            with open(self.issue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    raise ValueError("Issues file must be a JSON list.")
                return data
        except (json.JSONDecodeError, ValueError) as e:
            bak_path = self.issue_file.with_suffix(".json.bak")
            shutil.copy(self.issue_file, bak_path)
            print_error(f"Issue storage corrupted: {e}")
            print_info(f"Existing file backed up to {bak_path.name}. Resetting local issues.")
            return []
        except Exception as e:
            print_error(f"Failed to load issues: {e}")
            return []

    def save_all(self, issues: List[Dict[str, Any]]):
        """Save all issues to the local JSON file with Windows-safe encoding."""
        self._ensure_dir()
        try:
            with open(self.issue_file, "w", encoding="utf-8") as f:
                json.dump(issues, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print_error(f"Failed to save issues: {e}")
            raise DeepCLIException(1)

    def get_next_id(self, issues: List[Dict[str, Any]]) -> int:
        """Calculate the next available issue ID."""
        if not issues:
            return 1
        return max(issue.get("id", 0) for issue in issues) + 1

    def find_by_id(self, issues: List[Dict[str, Any]], issue_id: int) -> Optional[Dict[str, Any]]:
        """Find an issue by its numeric ID."""
        for issue in issues:
            if issue.get("id") == issue_id:
                return issue
        return None

def get_github_remote(repo_root: Path) -> str | None:
    """Extract owner/repo from remote.origin.url."""
    config = Config(repo_root)
    url = config.get("remote.origin.url")
    if not url:
        return None
    pattern = r"(?:https://github\.com/|git@github\.com:)([^/]+)/([^/.]+)(?:\.git)?"
    match = re.search(pattern, url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None

def get_token() -> str | None:
    return os.environ.get("GH_TOKEN") or os.environ.get("DEEP_TOKEN")

def api_request(path: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, verbose: bool = False) -> Any:
    token = get_token()
    if not token:
        return None  # Silent fail for sync detection if no token

    url = f"{GITHUB_API_BASE}/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Deep-VCS-Client"
    }

    req_data = None
    if data:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        if verbose:
            print_info(f"GitHub Sync: {method} {url}")
        with urllib.request.urlopen(req) as response:
            if response.status == 204:
                return True
            res_body = response.read().decode("utf-8")
            return json.loads(res_body)
    except Exception as e:
        if verbose:
            print_error(f"GitHub API error: {e}")
        return None

def run(args: Any) -> None:
    """Execute the ``issue`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print_error("Not a Deep repository.")
        raise DeepCLIException(1)

    manager = LocalIssueManager(repo_root)
    issues = manager.load_all()
    
    cmd = getattr(args, "issue_command", "list")
    verbose = getattr(args, "verbose", False)

    if cmd == "list":
        open_count = sum(1 for i in issues if i.get("state") == "open")
        closed_count = len(issues) - open_count
        
        print(Color.wrap(Color.CYAN, f"\nRepository Issues: {repo_root}"))
        print(Color.wrap(Color.CYAN, f"Total: {len(issues)} | {Color.wrap(Color.GREEN, f'Open: {open_count}')} | {Color.wrap(Color.RED, f'Closed: {closed_count}')}"))
        print(Color.wrap(Color.CYAN, "=" * 65))
        
        if not issues:
            print(Color.wrap(Color.DIM, " No local issues found."))
        else:
            # Sorted by ID ascending
            for issue in sorted(issues, key=lambda x: x.get("id", 0)):
                state = issue.get("state", "open")
                col = Color.GREEN if state == "open" else Color.RED
                state_label = Color.wrap(col, f"[{state.upper()}]")
                created = time.strftime('%Y-%m-%d', time.localtime(issue.get("created_at", 0)))
                
                print(f"#{issue.get('id'):<5} {state_label:<15} {issue.get('title')[:40]:<40} ({created})")
        print()

    elif cmd == "create":
        title = getattr(args, "title", "").strip()
        body = getattr(args, "description", "").strip()
        
        if not title:
            try:
                print(Color.wrap(Color.BOLD, "New Local Issue"))
                title = input("Title: ").strip()
                if not title:
                    print_error("Title cannot be empty.")
                    return
                body = input("Description: ").strip()
            except KeyboardInterrupt:
                print("\nAborted.")
                return

        now = time.time()
        new_issue = {
            "id": manager.get_next_id(issues),
            "title": title,
            "body": body,
            "state": "open",
            "created_at": now,
            "updated_at": now,
            "github_id": None
        }
        issues.append(new_issue)
        manager.save_all(issues)
        print_success(f"Issue #{new_issue['id']} saved locally.")

    elif cmd == "show":
        if not args.id:
            print_error("Missing issue ID.")
            raise DeepCLIException(1)
        
        try:
            issue_id = int(args.id)
        except ValueError:
            print_error(f"Invalid ID format: {args.id}")
            raise DeepCLIException(1)
            
        issue = manager.find_by_id(issues, issue_id)
        if not issue:
            print_error(f"Issue #{issue_id} not found locally.")
            raise DeepCLIException(1)
            
        col = Color.GREEN if issue.get("state") == "open" else Color.RED
        print(Color.wrap(Color.CYAN, f"\nIssue #{issue['id']}: {issue['title']}"))
        print(Color.wrap(Color.CYAN, "-" * 65))
        print(f"Status:  {Color.wrap(col, issue['state'].upper())}")
        print(f"Created: {time.ctime(issue.get('created_at', 0))}")
        print(f"Updated: {time.ctime(issue.get('updated_at', 0))}")
        if issue.get("github_id"):
            print(f"GitHub:  #{issue['github_id']}")
        print(f"\n{Color.wrap(Color.BOLD, 'Description:')}")
        print(f"{issue.get('body') or 'No description provided.'}\n")

    elif cmd in ("close", "reopen"):
        if not args.id:
            print_error(f"Missing issue ID for {cmd}.")
            raise DeepCLIException(1)
        
        try:
            issue_id = int(args.id)
        except ValueError:
            print_error(f"Invalid ID format: {args.id}")
            raise DeepCLIException(1)

        issue = manager.find_by_id(issues, issue_id)
        if not issue:
            print_error(f"Issue #{issue_id} not found.")
            raise DeepCLIException(1)
            
        new_state = "closed" if cmd == "close" else "open"
        issue["state"] = new_state
        issue["updated_at"] = time.time()
        manager.save_all(issues)
        print_success(f"Issue #{issue_id} is now {new_state}.")

    elif cmd == "sync":
        gh_repo = net.get_github_remote(repo_root)
        token = net.get_token()
        
        if not gh_repo or not token:
            print_error("Sync requires a GitHub remote and GH_TOKEN.")
            if not gh_repo:
                print("No GitHub remote found in config.")
            if not token:
                print("No GH_TOKEN or DEEP_TOKEN found in environment.")
            raise DeepCLIException(1)
            
        print_info(f"Syncing local issues with {gh_repo}...")
        synced_count = 0
        for issue in issues:
            # Only sync if not already on GitHub
            if not issue.get("github_id"):
                path = f"{gh_repo}/issues"
                res = net.api_request(path, method="POST", data={
                    "title": issue["title"],
                    "body": f"{issue['body']}\n\n---\n*Synced from DeepDVCS local issue #{issue['id']}*"
                }, verbose=verbose)
                
                if res and isinstance(res, dict) and "number" in res:
                    issue["github_id"] = res["number"]
                    synced_count += 1
            else:
                # Update existing GitHub issue state?
                path = f"{gh_repo}/issues/{issue['github_id']}"
                net.api_request(path, method="PATCH", data={"state": issue["state"]}, verbose=verbose)
                synced_count += 1
                
        manager.save_all(issues)
        print_success(f"Successfully synced {synced_count} issues with GitHub.")

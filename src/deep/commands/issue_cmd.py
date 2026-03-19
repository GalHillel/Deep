"""
deep.commands.issue_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
GitHub-native ``deep issue`` implementation.
"""

from __future__ import annotations
import urllib.request
import urllib.error
import json
import os
import sys
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from deep.core.config import Config
from deep.core.repository import find_repo
from deep.utils.ux import Color, print_error, print_success, print_info
from deep.core.errors import DeepCLIException

GITHUB_API_BASE = "https://api.github.com/repos"

def get_github_remote(repo_root: Path) -> str | None:
    """Extract owner/repo from remote.origin.url."""
    config = Config(repo_root)
    url = config.get("remote.origin.url")
    if not url:
        return None
    
    # Supported patterns:
    # https://github.com/owner/repo(.git)
    # git@github.com:owner/repo(.git)
    pattern = r"(?:https://github\.com/|git@github\.com:)([^/]+)/([^/.]+)(?:\.git)?"
    match = re.search(pattern, url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None

def get_token() -> str | None:
    """Retrieve GitHub token from environment."""
    return os.environ.get("GH_TOKEN") or os.environ.get("DEEP_TOKEN")

def api_request(path: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, verbose: bool = False) -> Any:
    """Perform a GitHub API request using urllib."""
    token = get_token()
    if not token:
        print_error("Missing authentication token.")
        print(Color.wrap(Color.DIM, "Please set GH_TOKEN or DEEP_TOKEN environment variable."))
        raise DeepCLIException(1)

    url = f"{GITHUB_API_BASE}/{path}"
    if verbose:
        print_info(f"API Request: {method} {url}")

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Deep-VCS-Client"
    }

    req_data = None
    if data:
        # Support mixed Windows/UTF-8 by ensuring UTF-8 encoding
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 204:
                return None
            res_body = response.read().decode("utf-8")
            return json.loads(res_body)
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            error_data = json.loads(e.read().decode("utf-8"))
            msg = error_data.get("message", str(e))
        except Exception:
            msg = str(e)
        print_error(f"GitHub API Error {status}: {msg}")
        raise DeepCLIException(1)
    except urllib.error.URLError as e:
        print_error(f"Network error: {e.reason}")
        raise DeepCLIException(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        raise DeepCLIException(1)

def run(args: Any) -> None:
    """Execute the ``issue`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print_error("Not a Deep repository.")
        raise DeepCLIException(1)

    gh_repo = get_github_remote(repo_root)
    if not gh_repo:
        print_error("Could not find a valid GitHub remote (remote.origin.url).")
        print(Color.wrap(Color.DIM, "Expected: https://github.com/owner/repo or git@github.com:owner/repo"))
        raise DeepCLIException(1)

    cmd = getattr(args, "issue_command", "list")
    verbose = getattr(args, "verbose", False)

    if cmd == "list":
        # List issues, skipping PRs
        path = f"{gh_repo}/issues"
        issues = api_request(path, verbose=verbose)
        if not issues:
            print(Color.wrap(Color.YELLOW, "No open issues found."))
            return

        print(Color.wrap(Color.CYAN, f"\nIssues for {gh_repo}"))
        print(Color.wrap(Color.CYAN, "=" * 60))
        
        found_any = False
        for issue in issues:
            # GitHub API returns PRs in the issues endpoint unless filtered
            if "pull_request" in issue:
                continue
            
            found_any = True
            num = issue.get("number")
            title = issue.get("title", "No Title")
            state = issue.get("state", "unknown")
            user = issue.get("user", {}).get("login", "unknown")
            
            state_col = Color.GREEN if state == "open" else Color.RED
            state_label = Color.wrap(state_col, f"[{state.upper()}]")
            
            # Print with nice fixed-width columns
            print(f"#{num:<5} {state_label:<15} {title[:45]:<45} ({user})")
        
        if not found_any:
            print(Color.wrap(Color.YELLOW, "No issues found (only Pull Requests)."))
        print()

    elif cmd == "show":
        if not args.id:
            print_error("Missing issue ID. Usage: deep issue show <id>")
            raise DeepCLIException(1)
        
        path = f"{gh_repo}/issues/{args.id}"
        issue = api_request(path, verbose=verbose)
        
        num = issue.get("number")
        title = issue.get("title")
        state = issue.get("state")
        author = issue.get("user", {}).get("login")
        html_url = issue.get("html_url")
        body = issue.get("body") or "No description provided."
        
        print(Color.wrap(Color.CYAN, f"\nIssue #{num}: {title}"))
        print(Color.wrap(Color.CYAN, "-" * 60))
        print(f"Status:  {Color.wrap(Color.GREEN if state == 'open' else Color.RED, state)}")
        print(f"Author:  {author}")
        print(f"URL:     {Color.wrap(Color.UL, html_url)}")
        print(f"\n{Color.wrap(Color.BOLD, 'Description:')}\n{body}")
        print()

    elif cmd == "create":
        title = getattr(args, "title", None)
        body = getattr(args, "description", "")
        
        if not title:
            print(Color.wrap(Color.BOLD, "Creating new GitHub Issue"))
            try:
                title = input("Title: ").strip()
                if not title:
                    print_error("Title is required.")
                    return
                if not body:
                    print(Color.wrap(Color.DIM, "(Tip: You can also use -d/--description)"))
                    body = input("Description: ").strip()
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                return

        path = f"{gh_repo}/issues"
        issue = api_request(path, method="POST", data={"title": title, "body": body}, verbose=verbose)
        
        print_success(f"Issue #{issue.get('number')} created!")
        print(f"Link: {Color.wrap(Color.GREEN, issue.get('html_url'))}")

    elif cmd == "close":
        if not args.id:
            print_error("Missing issue ID. Usage: deep issue close <id>")
            raise DeepCLIException(1)
        
        path = f"{gh_repo}/issues/{args.id}"
        api_request(path, method="PATCH", data={"state": "closed"}, verbose=verbose)
        print_success(f"Issue #{args.id} successfully closed.")

    elif cmd == "reopen":
        if not args.id:
            print_error("Missing issue ID. Usage: deep issue reopen <id>")
            raise DeepCLIException(1)
        
        path = f"{gh_repo}/issues/{args.id}"
        api_request(path, method="PATCH", data={"state": "open"}, verbose=verbose)
        print_success(f"Issue #{args.id} successfully reopened.")

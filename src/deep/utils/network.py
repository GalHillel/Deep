"""
deep.utils.network
~~~~~~~~~~~~~~~~~~~
Shared network utilities for GitHub API integration.
"""

from __future__ import annotations
import urllib.request
import urllib.error
import json
import os
import re
from typing import Dict, Any, Optional
from pathlib import Path

from deep.core.config import Config
from deep.utils.ux import print_error, print_info

GITHUB_API_BASE = "https://api.github.com/repos"

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
    """Retrieve GitHub token from environment."""
    return os.environ.get("GH_TOKEN") or os.environ.get("DEEP_TOKEN")

def api_request(path: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, verbose: bool = False) -> Any:
    """Perform a GitHub API request using urllib."""
    token = get_token()
    if not token:
        return None

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
            print_info(f"GitHub API: {method} {url}")
        with urllib.request.urlopen(req) as response:
            if response.status == 204:
                return True
            res_body = response.read().decode("utf-8")
            return json.loads(res_body)
    except Exception as e:
        if verbose:
            print_error(f"GitHub API error: {e}")
        return None

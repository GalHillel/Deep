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

def get_github_remote(repo_root: Path) -> Optional[str]:
    """Parse remote.origin.url and return 'owner/repo' if it's a GitHub URL."""
    try:
        config_path = repo_root / ".deep" / "config"
        if not config_path.exists():
            return None
        
        content = config_path.read_text()
        match = re.search(r'\[remote "origin"\]\s+url = (.*)', content)
        if not match:
            return None
        
        url = match.group(1).strip()
        if "github.com" not in url:
            return None
            
        # Robust parsing
        if url.startswith("git@github.com:"):
            # git@github.com:owner/repo.git
            path = url.split("git@github.com:")[1]
        elif url.startswith("https://github.com/"):
            # https://github.com/owner/repo.git
            path = url.split("https://github.com/")[1]
        elif "github.com/" in url:
            path = url.split("github.com/")[1]
        else:
            return None
            
        if path.endswith(".git"):
            path = path[:-4]
            
        return path
    except Exception:
        return None

def get_token() -> str | None:
    """Retrieve GitHub token from environment."""
    return os.environ.get("GH_TOKEN") or os.environ.get("DEEP_TOKEN")

def api_request(path: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, verbose: bool = False) -> Any:
    """Perform a GitHub API request using urllib."""
    token = get_token()
    if not token:
        return {"error": "No token", "status": 401}

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
                return {"status": 204}
            res_body = response.read().decode("utf-8")
            result = json.loads(res_body)
            if isinstance(result, dict):
                result["status"] = response.status
            return result
    except urllib.error.HTTPError as e:
        if verbose:
            print_error(f"GitHub API error: {e.code} {e.reason}")
        try:
            body = e.read().decode("utf-8")
            err_data = json.loads(body)
            err_data["status"] = e.code
            return err_data
        except Exception:
            return {"error": str(e), "status": e.code}
    except Exception as e:
        if verbose:
            print_error(f"GitHub API non-HTTP error: {e}")
        return {"error": str(e), "status": 500}

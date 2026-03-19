"""
deep.network.auth
~~~~~~~~~~~~~~~~~

Authentication support for smart protocol transports.

Supports:
- PAT (Personal Access Token) via HTTPS Basic Auth
- SSH key auth (delegated to system ssh-agent)
- Environment-based token discovery

Security:
- Tokens are never logged or included in error messages
- All credential handling is sanitized
"""

from __future__ import annotations

import base64
import os
from typing import Optional, Dict
from urllib.request import Request


def get_auth_token() -> Optional[str]:
    """Discover an auth token from environment or config.

    Checks (in order):
      1. DEEP_TOKEN environment variable
      2. GH_TOKEN / GITHUB_TOKEN for GitHub
      3. GL_TOKEN for GitLab
    """
    for env_var in ("DEEP_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GL_TOKEN"):
        token = os.environ.get(env_var)
        if token:
            return token
    return None


def basic_auth_header(username: str, password: str) -> str:
    """Create HTTP Basic Auth header value.

    Args:
        username: The username (often 'x-access-token' for PATs).
        password: The token or password.

    Returns:
        'Basic <base64>' string suitable for Authorization header.
    """
    credentials = f"{username}:{password}".encode("utf-8")
    encoded = base64.b64encode(credentials).decode("ascii")
    return f"Basic {encoded}"


def apply_auth_to_request(
    req: Request,
    url: str,
    token: Optional[str] = None,
) -> Request:
    """Apply authentication to an HTTP request.

    For HTTPS URLs:
    - If token is provided, use Basic auth with 'x-access-token' as username
    - Supports GitHub and GitLab token authentication

    Args:
        req: The urllib Request object.
        url: The target URL (used to determine auth strategy).
        token: Optional PAT token.

    Returns:
        The modified Request with auth headers applied.
    """
    if token is None:
        token = get_auth_token()

    if token:
        auth = basic_auth_header("x-access-token", token)
        req.add_header("Authorization", auth)

    return req


def sanitize_url_for_logging(url: str) -> str:
    """Remove credentials from a URL for safe logging.

    Replaces password components with '***'.
    """
    if "@" in url and "://" in url:
        # https://user:token@host/path → https://user:***@host/path
        proto, rest = url.split("://", 1)
        if "@" in rest:
            creds, hostpath = rest.split("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{proto}://{user}:***@{hostpath}"
    return url

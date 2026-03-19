"""
deep.network.transport
~~~~~~~~~~~~~~~~~~~~~~

Transport layer for Deep smart protocol.

Supports two transport mechanisms:
1. SSH — via system `ssh` subprocess (NOT external VCS CLI)
2. HTTPS — via urllib (stdlib, no external dependencies)

URL formats:
    SSH:   user@github.com:user/repo
           ssh://user@github.com/user/repo
    HTTPS: https://github.com/user/repo
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple, BinaryIO
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from deep.network.auth import (
    apply_auth_to_request,
    get_auth_token,
    sanitize_url_for_logging,
)


class TransportError(Exception):
    """Raised on transport-level errors."""
    pass


class AuthenticationError(TransportError):
    """Raised on authentication failures."""
    pass


# ── URL Parsing ────────────────────────────────────────────────────

def parse_git_url(url: str) -> Tuple[str, str, str, str]:
    """Parse a remote URL into (transport, host, port, path).

    Returns:
        (transport: "ssh" | "https" | "http",
         host: hostname,
         port: port string or "",
         path: repository path on server)
    """
    # ssh://user@host:port/path
    m = re.match(r'^ssh://([^@]+@)?([^:/]+)(?::(\d+))?(/.*)', url)
    if m:
        user = m.group(1) or "user@"
        return "ssh", f"{user}{m.group(2)}", m.group(3) or "", m.group(4)

    # file://path
    m = re.match(r'^file://(.*)', url)
    if m:
        return "file", "", "", m.group(1)

    # user@host:user/repo (SCP-style)
    m = re.match(r'^([^@]+@[^:]+):(.+)', url)
    if m:
        return "ssh", m.group(1), "", f"/{m.group(2)}"

    # https://host/path
    m = re.match(r'^(https?)://([^/:]+)(?::(\d+))?(/.*)$', url)
    if m:
        return m.group(1), m.group(2), m.group(3) or "", m.group(4)

    # Assume HTTPS if nothing matches
    if "/" in url and "." in url and not url.startswith("C:\\") and not url.startswith("/"):
        return "https", url.split("/")[0], "", "/" + "/".join(url.split("/")[1:])

    # If it's an absolute local path (Windows or Unix) or relative path to a local directory
    if os.path.exists(url) or url.startswith("C:\\") or url.startswith("/") or "\\" in url:
        return "file", "", "", url

    raise TransportError(f"Cannot parse remote URL: {url}")


def _normalize_repo_url(url: str) -> str:
    """Ensure repository URL has valid suffix."""
    if not url.endswith(".git"):
        url += ".git"
    return url


# ── SSH Transport ──────────────────────────────────────────────────

class SSHTransport:
    """Transport via SSH subprocess.

    Connects to a remote server using the system's `ssh` command.
    Does NOT use external VCS CLI — only ssh for the raw pipe.
    """

    def __init__(self, url: str):
        self.url = url
        transport, self.host, self.port, self.path = parse_git_url(url)
        if transport != "ssh":
            raise TransportError(f"Not an SSH URL: {url}")
        self._proc: Optional[subprocess.Popen] = None
        self.stdin: Optional[BinaryIO] = None
        self.stdout: Optional[BinaryIO] = None

    def connect_upload_pack(self) -> None:
        """Connect to upload-pack service on the remote."""
        self._connect("git-upload-pack")

    def connect_receive_pack(self) -> None:
        """Connect to receive-pack service on the remote."""
        self._connect("git-receive-pack")

    def _connect(self, service: str) -> None:
        """Spawn ssh process for the given remote service."""
        repo_path = self.path.lstrip("/")
        if not repo_path.endswith(".git"):
            repo_path += ".git"

        ssh_cmd = ["ssh"]

        # Add port if specified
        if self.port:
            ssh_cmd.extend(["-p", self.port])

        # Disable strict host key checking for non-interactive use
        # (user can override via SSH config)
        ssh_cmd.extend([
            "-o", "BatchMode=yes",
            self.host,
            f"{service} '{repo_path}'"
        ])

        if os.environ.get("DEEP_DEBUG"):
            safe_cmd = " ".join(ssh_cmd)
            print(f"[DEEP_DEBUG] SSH: {safe_cmd}", file=sys.stderr)

        try:
            self._proc = subprocess.Popen(
                ssh_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.stdin = self._proc.stdin
            self.stdout = self._proc.stdout
        except FileNotFoundError:
            raise TransportError(
                "SSH client not found. Ensure 'ssh' is in your PATH."
            )
        except Exception as e:
            raise TransportError(f"SSH connection failed: {e}")

    def close(self) -> None:
        """Close the SSH connection."""
        if self._proc:
            try:
                if self.stdin:
                    self.stdin.close()
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
            finally:
                self._proc = None
                self.stdin = None
                self.stdout = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ── HTTPS Transport ────────────────────────────────────────────────

class HTTPSTransport:
    """Transport via HTTPS using urllib.

    Uses the smart HTTP protocol:
    - GET /info/refs?service=<service> for ref discovery
    - POST /<service> for data exchange

    No external HTTP library needed — uses Python's stdlib.
    """

    def __init__(self, url: str, token: Optional[str] = None):
        self.url = _normalize_repo_url(url)
        self.token = token or get_auth_token()
        self._base_url = self._build_base_url()

    def _build_base_url(self) -> str:
        """Normalize the base URL for HTTP endpoints."""
        url = self.url
        # Ensure https:// prefix
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        # Remove trailing /
        return url.rstrip("/")

    def get_refs(self, service: str = "git-upload-pack") -> Tuple[bytes, str]:
        """Perform ref discovery via smart HTTP.

        GET /info/refs?service=<service>

        Returns:
            (response_body, content_type)
        """
        info_url = f"{self._base_url}/info/refs?service={service}"

        if os.environ.get("DEEP_DEBUG"):
            safe_url = sanitize_url_for_logging(info_url)
            print(f"[DEEP_DEBUG] HTTP GET {safe_url}", file=sys.stderr)

        req = Request(info_url)
        req.add_header("User-Agent", "deep-vcs/1.0")
        req.add_header("Git-Protocol", "version=2")
        req = apply_auth_to_request(req, self._base_url, self.token)

        try:
            resp = urlopen(req, timeout=30)
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
            return body, content_type
        except HTTPError as e:
            if e.code == 401:
                raise AuthenticationError(
                    "Authentication failed. Set DEEP_TOKEN, GH_TOKEN, or "
                    "GITHUB_TOKEN environment variable with a valid PAT."
                )
            elif e.code == 404:
                raise TransportError(
                    f"Repository not found: {sanitize_url_for_logging(self._base_url)}"
                )
            raise TransportError(
                f"HTTP error {e.code}: {e.reason}"
            )
        except URLError as e:
            raise TransportError(f"Network error: {e.reason}")

    def post_service(
        self,
        service: str,
        data: bytes,
    ) -> BinaryIO:
        """POST to a remote service endpoint.

        POST /<service>

        Args:
            service: 'git-upload-pack' or 'git-receive-pack'
            data: Request body bytes.

        Returns:
            File-like response body stream.
        """
        post_url = f"{self._base_url}/{service}"

        if os.environ.get("DEEP_DEBUG"):
            safe_url = sanitize_url_for_logging(post_url)
            print(f"[DEEP_DEBUG] HTTP POST {safe_url} ({len(data)} bytes)",
                  file=sys.stderr)

        req = Request(post_url, data=data, method="POST")
        req.add_header("Content-Type",
                        f"application/x-{service}-request")
        req.add_header("User-Agent", "deep-vcs/1.0")
        req.add_header("Git-Protocol", "version=2")
        req = apply_auth_to_request(req, self._base_url, self.token)

        try:
            resp = urlopen(req, timeout=300)
            return resp
        except HTTPError as e:
            if e.code == 401:
                raise AuthenticationError("Authentication failed for push/fetch.")
            body = e.read().decode("utf-8", errors="replace")[:200]
            raise TransportError(f"HTTP {e.code}: {body}")
        except URLError as e:
            raise TransportError(f"Network error: {e.reason}")


# ── Transport Factory ──────────────────────────────────────────────

def create_transport(url: str, token: Optional[str] = None):
    """Create the appropriate transport for a URL.

    Returns:
        SSHTransport or HTTPSTransport instance.
    """
    transport_type, _, _, _ = parse_git_url(url)

    if transport_type == "ssh":
        return SSHTransport(url)
    elif transport_type in ("https", "http"):
        return HTTPSTransport(url, token=token)
    else:
        raise TransportError(f"Unsupported transport: {transport_type}")

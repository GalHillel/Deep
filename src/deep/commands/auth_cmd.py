"""
deep.commands.auth_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep auth`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.user import UserManager
from deep.core.config import Config
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'auth' command parser."""
    p_auth = subparsers.add_parser(
        "auth",
        help="Manage authentication and user identity",
        description=format_description("Authenticate with the Deep platform and manage your local user identity. Authentication ensures that your commits are correctly attributed and that you have the necessary permissions to interact with remote repositories."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep auth login --token <token>", "Login to the Deep platform using an access token")}
{format_example("deep auth logout", "Clear local authentication credentials")}
{format_example("deep auth status", "Show current authentication status and user identity")}
{format_example("deep auth whoami", "Quickly check the currently authenticated username")}
""",
        formatter_class=DeepHelpFormatter,
    )
    asub = p_auth.add_subparsers(dest="auth_command", metavar="ACTION")
    p_login = asub.add_parser("login", help="Log in to the Deep platform")
    p_login.add_argument("--token", required=True, help="Your personal access token")

def run(args) -> None:
    """Execute the ``auth`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print("Deep: error: Not a Deep repository.", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    manager = UserManager(dg_dir)
    
    cmd = args.auth_command
    
    if cmd == "login":
        token = args.token
        user = manager.authenticate_token(token)
        if user:
            # Store auth token in local config
            config = Config(repo_root)
            config.set_local("user.name", user.username)
            config.set_local("user.email", user.email)
            config.set_local("auth.token", token)
            print(Color.wrap(Color.GREEN, f"Successfully logged in as {user.username}."))
        else:
            print(Color.wrap(Color.RED, "Invalid authentication token."), file=sys.stderr)
            raise DeepCLIException(1)

"""
deep.commands.auth_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep auth`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
import getpass
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.user import UserManager
from deep.core.config import Config
from deep.utils.ux import Color, print_success, print_error, print_info

def run(args) -> None:
    """Execute the ``auth`` command."""
    # Determine the platform context (server root)
    server_root = Path(".").resolve()
    repo_root = None
    try:
        repo_root = find_repo()
        server_root = repo_root
    except FileNotFoundError:
        # Not in a repo, but auth can still work if it points to a platform instance
        # For now, we assume the current directory is a potential platform server root if not in a repo
        pass

    dg_dir = server_root / DEEP_DIR
    manager = UserManager(dg_dir)
    config = Config(repo_root) if repo_root else Config()
    
    cmd = args.auth_command
    
    if cmd == "login":
        token = getattr(args, "token", None)
        if not token:
            # Interactive prompt if no token provided via CLI
            if sys.stdin.isatty():
                print(f"{Color.wrap(Color.BOLD, '⚓️ Deep Authentication')}")
                print("Please provide your personal access token to log in.")
                try:
                    token = getpass.getpass("Token: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nAborted.")
                    return
            else:
                print_error("No token provided and terminal is not interactive.")
                raise DeepCLIException(1)

        if not token:
            print_error("Authentication token cannot be empty.")
            raise DeepCLIException(1)

        user = manager.authenticate_token(token)
        if user:
            # Store auth token in global config so it works across repos
            config.set_global("user.name", user.username)
            config.set_global("user.email", user.email)
            config.set_global("auth.token", token)
            print_success(f"Logged in as {user.username}.")
        else:
            print_error("Invalid authentication token.")
            raise DeepCLIException(1)

    elif cmd == "logout":
        current_token = config.get("auth.token")
        if not current_token:
            print_info("You are not currently logged in.")
            return
            
        # Clear token from global config
        # config.remove_global("auth") # Config doesn't have remove_global yet
        # Let's use set_global with empty value or similar if remove is missing
        # Actually, let's see if Config has a remove method.
        # It has remove_local. I'll add remove_global if needed, or just set to empty.
        config.set_global("auth.token", "")
        print_success("Successfully logged out.")

    elif cmd == "status":
        token = config.get("auth.token")
        if not token:
            print("You are not logged in. Run 'deep auth login' to authenticate.")
            return
            
        user = manager.authenticate_token(token)
        if user:
            print(f"{Color.wrap(Color.BOLD, '⚓️ Deep Authentication Status')}")
            print(f"Logged in as: {Color.wrap(Color.CYAN, user.username)}")
            print(f"Email:         {user.email}")
            print(f"Token:         {'*' * 12}{token[-4:] if len(token) > 4 else ''}")
        else:
            print_error("The stored authentication token is invalid or expired.")
            print("Run 'deep auth login' to refresh your session.")

    elif cmd == "token":
        token = config.get("auth.token")
        if not token:
            print_error("No authentication token found. Please log in first.")
            raise DeepCLIException(1)
        print(token)

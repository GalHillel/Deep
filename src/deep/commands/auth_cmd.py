"""
deep.commands.auth_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep auth`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_DIR, find_repo
from deep.core.user import UserManager
from deep.core.config import Config
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``auth`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print("DeepGit: error: Not a DeepGit repository.", file=sys.stderr)
        sys.exit(1)

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
            sys.exit(1)

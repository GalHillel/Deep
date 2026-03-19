"""
deep.commands.user_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep user`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.user import UserManager
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``user`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        # Allow global user management if no repo found? 
        # For now, let's assume it's per-server (repo root).
        print("Deep: error: Not a Deep repository (or parent).", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    manager = UserManager(dg_dir)
    
    cmd = args.user_command
    
    if cmd == "add":
        try:
            user = manager.add_user(args.username, args.public_key, args.email)
            print(Color.wrap(Color.GREEN, f"User '{user.username}' added successfully."))
            print(f"Auth Token: {user.token} (Keep this secret!)")
        except ValueError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
            
    elif cmd == "remove":
        try:
            manager.remove_user(args.username)
            print(Color.wrap(Color.YELLOW, f"User '{args.username}' removed."))
        except ValueError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
            
    elif cmd == "list":
        users = manager.list_users()
        if not users:
            print("No users found.")
            return
            
        print(f"{'Username':<15} {'Email':<25} {'Public Key'}")
        print("-" * 60)
        for u in users:
            pub_short = u.public_key[:20] + "..." if len(u.public_key) > 20 else u.public_key
            print(f"{u.username:<15} {u.email:<25} {pub_short}")

"""
deep.commands.repo_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep repo`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException
from deep.utils.logger import shutdown_logging

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.platform.platform import PlatformManager
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``repo`` command."""
    try:
        server_root = Path(".").resolve()
        try:
            repo_root = find_repo()
            server_root = repo_root
        except FileNotFoundError:
            pass
            
        manager = PlatformManager(server_root)
        cmd = args.repo_command
        
        if cmd == "create":
            try:
                path = manager.create_repo(args.name)
                print(Color.wrap(Color.GREEN, f"Repository '{args.name}' created at {path}"))
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                raise DeepCLIException(1)
                
        elif cmd == "delete":
            try:
                # Ensure we release any file locks (like logs) before deleting
                shutdown_logging()
                manager.delete_repo(args.name)
                print(Color.wrap(Color.YELLOW, f"Repository '{args.name}' deleted."))
            except ValueError as e:
                print( Color.wrap(Color.RED, f"Error: {e}"), file=sys.stderr)
                raise DeepCLIException(1)
            except PermissionError as e:
                print(Color.wrap(Color.RED, f"Error (Permission denied): {e}. This often happens on Windows if a process is still holding a handle to deep.log."), file=sys.stderr)
                raise DeepCLIException(1)
                
        elif cmd == "list":
            repos = manager.list_repos()
            if not repos:
                print("No repositories found in 'repos/' directory.")
                return
            print(f"Repositories in {server_root / 'repos'}:")
            for r in repos:
                print(f"  - {r}")
                
        elif cmd == "clone":
            print(f"Cloning {args.url} into {args.name or 'repo'}...")
            from deep.commands.clone_cmd import run as clone_run
            from deep.core.config import Config
            config = Config(server_root)
            auth_token = config.get("auth.token")
            clone_args_instance = args
            setattr(clone_args_instance, "token", auth_token)
            clone_run(clone_args_instance)

        elif cmd == "permit":
            user = getattr(args, "user", None)
            role = getattr(args, "role", None)
            
            if not user or not role:
                print(Color.wrap(Color.RED, "Error: '--user' and '--role' are required for 'repo permit'."), file=sys.stderr)
                raise DeepCLIException(1)
            
            # Map CLI-friendly roles to core logic roles
            ROLE_MAP = {
                "admin": "owner",
                "maintainer": "maintainer",
                "write": "contributor",
                "contributor": "contributor",
                "read": "viewer",
                "viewer": "viewer"
            }
            
            target_role = ROLE_MAP.get(role.lower(), role)

            try:
                from deep.core.access import AccessManager
                target_repo_name = getattr(args, "name", None)
                if target_repo_name:
                    repo_path = server_root / "repos" / target_repo_name / DEEP_DIR
                else:
                    repo_path = server_root / DEEP_DIR
                
                if not repo_path.exists():
                    print(Color.wrap(Color.RED, f"Error: Repository metadata not found at {repo_path}"), file=sys.stderr)
                    raise DeepCLIException(1)
                    
                access = AccessManager(repo_path)
                access.set_permission(user, target_role)
                print(Color.wrap(Color.GREEN, f"Permission set: {user} is now a {target_role} for {repo_path.parent.name}."))
            except Exception as e:
                print(Color.wrap(Color.RED, f"Error setting permission: {e}"), file=sys.stderr)
                raise DeepCLIException(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise DeepCLIException(1)

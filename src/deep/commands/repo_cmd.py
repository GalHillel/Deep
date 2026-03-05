"""
deep.commands.repo_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep repo`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_GIT_DIR, find_repo
from deep.core.platform import PlatformManager
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``repo`` command."""
    # We find the server root (where the server is running or intended to run)
    try:
        server_root = Path(".").resolve() # Assume current dir is server root or we find it
        # Try to find a .deep_git dir to use as server metadata
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
                sys.exit(1)
                
        elif cmd == "delete":
            try:
                manager.delete_repo(args.name)
                print(Color.wrap(Color.YELLOW, f"Repository '{args.name}' deleted."))
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
                
        elif cmd == "list":
            repos = manager.list_repos()
            if not repos:
                print("No repositories found in 'repos/' directory.")
                return
            print(f"Repositories in {server_root / 'repos'}:")
            for r in repos:
                print(f"  - {r}")
                
        elif cmd == "clone":
            # Repo clone from server side - essentially a local clone/init
            print(f"Cloning {args.url} into {args.name or 'repo'}...")
            from deep.commands.clone_cmd import run as clone_run
            from deep.core.config import Config
            
            # Attempt to get auth token for remote operations
            config = Config(server_root)
            auth_token = config.get("auth.token")
            
            clone_args_instance = args # Reuse args
            setattr(clone_args_instance, "token", auth_token)
            clone_run(clone_args_instance)

        elif cmd == "permit":
            user = args.user
            role = args.role
            try:
                from deep.core.access import AccessManager
                # We need the dg_dir of the platform server (server_root)
                # No, we need it for the specific repo if repo-level? 
                # The prompt said "repository permissions". PlatformManager manages repos.
                # Usually permissions are per-repository.
                # Let's assume it's for the "current" repo if we are in one, 
                # or a specific one if specified?
                # The 'deep repo' command usually acts on the platform level.
                # Let's make it work on the repository specified by name if possible,
                # or the current repo.
                
                target_repo_name = getattr(args, "name", None)
                if target_repo_name:
                    repo_path = server_root / "repos" / target_repo_name / DEEP_GIT_DIR
                else:
                    repo_path = server_root / DEEP_GIT_DIR
                
                if not repo_path.exists():
                    print(Color.wrap(Color.RED, f"Error: Repository metadata not found at {repo_path}"), file=sys.stderr)
                    sys.exit(1)
                    
                access = AccessManager(repo_path)
                access.set_permission(user, role)
                print(Color.wrap(Color.GREEN, f"Permission set: {user} is now a {role} for {repo_path.parent.name}."))
            except Exception as e:
                print(Color.wrap(Color.RED, f"Error setting permission: {e}"), file=sys.stderr)
                sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

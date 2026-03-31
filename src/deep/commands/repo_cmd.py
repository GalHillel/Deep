"""
deep.commands.repo_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep repo`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.platform.platform import PlatformManager
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'repo' command parser."""
    p_repo = subparsers.add_parser(
        "repo",
        help="Manage repository metadata and platform links",
        description="Configure repository-level settings and links to the Deep platform.",
        epilog=f"""
Examples:
{format_example("deep repo list", "List all repositories in the current server instance")}
{format_example("deep repo create my-project", "Create a new repository on the server")}
""",
        formatter_class=DeepHelpFormatter,
    )
    rsub = p_repo.add_subparsers(dest="repo_command", metavar="ACTION")
    
    p_create = rsub.add_parser("create", help="Create a new repository")
    p_create.add_argument("name", help="The name for the new repository")
    
    rsub.add_parser("list", help="List all repositories")
    
    p_delete = rsub.add_parser("delete", help="Delete a repository")
    p_delete.add_argument("name", help="The name of the repository to delete")
    
    p_clone = rsub.add_parser("clone", help="Clone a repository")
    p_clone.add_argument("url", help="The URL to clone from")
    p_clone.add_argument("name", nargs="?", help="The local directory name for the clone")
    
    p_permit = rsub.add_parser("permit", help="Set user permissions for a repository")
    p_permit.add_argument("user", help="The username to grant permission to")
    p_permit.add_argument("role", choices=["owner", "admin", "writer", "reader"], help="The role to assign")
    p_permit.add_argument("--name", help="The repository name (optional, defaults to current)")

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
                manager.delete_repo(args.name)
                print(Color.wrap(Color.YELLOW, f"Repository '{args.name}' deleted."))
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
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
            user = args.user
            role = args.role
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
                access.set_permission(user, role)
                print(Color.wrap(Color.GREEN, f"Permission set: {user} is now a {role} for {repo_path.parent.name}."))
            except Exception as e:
                print(Color.wrap(Color.RED, f"Error setting permission: {e}"), file=sys.stderr)
                raise DeepCLIException(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise DeepCLIException(1)

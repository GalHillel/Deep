import argparse
import sys
from pathlib import Path

from deep.core.repository import find_repo
from deep.utils.utils import DeepError
from deep.core.errors import DeepCLIException
from deep.storage.transaction import TransactionManager
from deep.core.constants import DEEP_DIR


from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'checkout' command parser."""
    p_checkout = subparsers.add_parser(
        "checkout",
        help="Switch branches or restore files",
        description="""Switch to a different branch, restore files from a specific commit, or create and switch to a new branch.

This command updates your working directory to match the specified target state.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep checkout main\033[0m
     Switch to the 'main' branch
  \033[1;34m⚓️ deep checkout -b feature\033[0m
     Create and switch to a new 'feature' branch
  \033[1;34m⚓️ deep checkout abc1234\033[0m
     Detach HEAD and switch to a specific commit SHA
  \033[1;34m⚓️ deep checkout file.txt\033[0m
     Discard local changes and restore 'file.txt' from index
  \033[1;34m⚓️ deep checkout main -- file.txt\033[0m
     Restore 'file.txt' from the 'main' branch
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_checkout.add_argument("-f", "--force", action="store_true", help="Force branch switching even if there are uncommitted local changes")
    p_checkout.add_argument("-b", action="store_true", dest="branch", help="Create a new branch and switch to it")
    p_checkout.add_argument("target", help="The branch name, commit SHA, or file path to switch/restore")
    p_checkout.add_argument("paths", nargs="*", help="Optional specific paths to restore from the target")


def run(args: argparse.Namespace) -> None:
    """Execute the ``checkout`` command."""
    try:
        repo_root = find_repo()
        from deep.utils.logger import setup_repo_logging
        setup_repo_logging(repo_root)
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    # 2. Identify if we are restoring files or switching branches
    paths = getattr(args, "paths", [])
    target = args.target
    force = getattr(args, "force", False)
    create_branch = getattr(args, "branch", False)

    dg_dir = repo_root / DEEP_DIR

    with TransactionManager(dg_dir) as tm:
        if paths:
            tm.begin("checkout_paths")
            # File-level restore
            from deep.core.refs import resolve_revision
            from deep.storage.objects import read_object, Commit, Tree
            
            objects_dir = dg_dir / "objects"
            
            target_sha = resolve_revision(dg_dir, target)
            if not target_sha:
                print(f"Deep: error: '{target}' is not a valid revision.", file=sys.stderr)
                raise DeepCLIException(1)
                
            commit = read_object(objects_dir, target_sha)
            if not isinstance(commit, Commit):
                print(f"Deep: error: '{target}' is not a commit.", file=sys.stderr)
                raise DeepCLIException(1)
                
            from deep.core.repository import _get_tree_files
            all_files = _get_tree_files(objects_dir, commit.tree_sha)
            
            for p in paths:
                # Normalize path
                rel_p = Path(p).resolve().relative_to(repo_root).as_posix()
                if rel_p not in all_files:
                    print(f"Deep: error: path '{rel_p}' not found in {target}.", file=sys.stderr)
                    continue
                    
                sha = all_files[rel_p]
                blob = read_object(objects_dir, sha)
                
                dest = repo_root / rel_p
                dest.parent.mkdir(parents=True, exist_ok=True)
                if hasattr(blob, "data"):
                    dest.write_bytes(blob.data)
                else:
                    dest.write_bytes(blob.serialize_content())
                print(f"Updated 1 path from {target_sha[:7]}")
            tm.commit()
            return

        # 3. Branch/Commit switching
        tm.begin("checkout_branch")
        try:
            from deep.core.repository import checkout
            from deep.core.state import validate_repo_state
            checkout(repo_root, target, create_branch=create_branch, force=force)
            validate_repo_state(repo_root)
            
            if create_branch:
                print(f"Deep: switched to a new branch '{target}'")
            elif target and len(target) == 40:
                print(f"Deep: HEAD is now at {target[:7]}")
            else:
                print(f"Deep: switched to branch '{target}'")
            tm.commit()

        except DeepError as exc:
            print(f"Deep: error: {exc}", file=sys.stderr)
            raise DeepCLIException(1)

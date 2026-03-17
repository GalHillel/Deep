import argparse
import sys

from deep.core.repository import find_repo
from deep.utils.utils import DeepError


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the 'checkout' command parser."""
    p_checkout = subparsers.add_parser(
        "checkout",
        help="Switch branches or restore files",
        description="Switch to a different branch or restore files from a specific commit to the working tree.",
        epilog="""
Examples:
  deep checkout main         # Switch to the 'main' branch
  deep checkout -b feature   # Create a new 'feature' branch and switch to it immediately
  deep checkout abc1234      # Detach HEAD and switch to a specific commit
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_checkout.add_argument("-f", "--force", action="store_true", help="Force branch switching even if there are uncommitted local changes")
    p_checkout.add_argument("-b", "--branch", action="store_true", help="Create a new branch")
    p_checkout.add_argument("target", help="The branch name or commit SHA to switch to")


def run(args: argparse.Namespace) -> None:
    """Execute the ``checkout`` command."""
    try:
        repo_root = find_repo()
        
        target = args.target
        create_branch = getattr(args, "branch", False)
        force = getattr(args, "force", False)
        
        from deep.core.repository import checkout
        checkout(repo_root, target, create_branch=create_branch, force=force)
        
        if create_branch:
            print(f"Deep: switched to a new branch '{target}'")
        elif target and len(target) == 40:
            print(f"Deep: HEAD is now at {target[:7]}")
        else:
            print(f"Deep: switched to branch '{target}'")

    except DeepError as exc:
        print(f"DeepError: {exc}", file=sys.stderr)
        sys.exit(1)

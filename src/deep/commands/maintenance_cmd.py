"""
deep.commands.maintenance_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep maintenance`` command implementation.
"""

from __future__ import annotations
import sys
import argparse
from pathlib import Path

from deep.core.errors import DeepCLIException
from deep.core.maintenance import run_maintenance
from deep.core.repository import find_repo

def get_description() -> str:
    return "Optimize the repository by repacking objects, updating indices, and pruning unreachable data."

def get_epilog() -> str:
    return """\033[1mEXAMPLES:\033[0m

  \033[1;34m⚓️ deep maintenance\033[0m
     Run scheduled maintenance tasks.

  \033[1;34m⚓️ deep maintenance --force\033[0m
     Force run all maintenance tasks immediately.
"""

def setup_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "maintenance",
        help="Run repository maintenance tasks",
        description=get_description(),
        epilog=get_epilog(),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--force", action="store_true", help="Force run maintenance even if recently completed")
    return p

def run(args: argparse.Namespace) -> None:
    """Execute the ``maintenance`` command."""
    try:
        repo_root = find_repo()
        run_maintenance(repo_root, force=getattr(args, "force", False))
    except FileNotFoundError:
        print("Deep: error: not a repository", file=sys.stderr)
        raise DeepCLIException(1)
    except Exception as e:
        print(f"Deep: maintenance error: {e}", file=sys.stderr)
        raise DeepCLIException(1)

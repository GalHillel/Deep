from __future__ import annotations
import argparse
import sys
import os
import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from deep.core.errors import DeepError, DeepCLIException
from deep.utils.ux import (
    Color, DeepHelpFormatter, print_deep_logo, 
    format_header, format_command, format_example, print_error, suggest_command
)

VERSION = "1.1.0"

# Logical command groupings for the main help menu
COMMAND_GROUPS = {
    "🌱 Starting a working area": ["init", "clone"],
    "📦 Work on the current change": ["add", "rm", "mv", "reset", "stash"],
    "🌿 Examine the history and state": ["status", "log", "diff", "show", "ls-tree", "graph"],
    "🔄 Grow, mark and tweak your common history": ["commit", "branch", "checkout", "merge", "rebase", "tag"],
    "🌐 Collaborate (P2P & Remote)": ["push", "pull", "fetch", "remote", "p2p", "sync", "ls-remote", "mirror", "daemon"],
    "🧠 AI & Platform": ["ai", "pr", "issue", "pipeline", "studio", "repo", "user", "auth", "server"],
    "🛠️ Maintenance & Diagnostics": [
        "doctor", "fsck", "gc", "maintenance", "verify", "repack", 
        "benchmark", "audit", "ultra", "batch", "sandbox", "rollback"
    ],
}

def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser with categorized subcommands."""
    parser = argparse.ArgumentParser(
        prog="deep",
        description="\033[1;34m⚓️ DeepGit\033[0m v1.1.0 - Next-generation Distributed VCS",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
\033[1;32m🌱 STARTING A WORKING AREA\033[0m
    \033[1;36minit, clone\033[0m

\033[1;33m📦 WORK ON THE CURRENT CHANGE\033[0m
    \033[1;36madd, rm, mv, reset, stash\033[0m

\033[1;32m🌿 EXAMINE THE HISTORY AND STATE\033[0m
    \033[1;36mstatus, log, diff, show, ls-tree, graph\033[0m

\033[1;35m🔄 GROW, MARK AND TWEAK YOUR COMMON HISTORY\033[0m
    \033[1;36mcommit, branch, checkout, merge, rebase, tag\033[0m

\033[1;34m🌐 COLLABORATE (P2P & REMOTE)\033[0m
    \033[1;36mpush, pull, fetch, remote, p2p, sync, ls-remote, mirror, daemon\033[0m

\033[1;35m🧠 AI & PLATFORM\033[0m
    \033[1;36mai, pr, issue, pipeline, studio, repo, user, auth, server\033[0m

\033[1;31m🛠️ MAINTENANCE & DIAGNOSTICS\033[0m
    \033[1;36mdoctor, fsck, gc, verify, repack, benchmark, audit, ultra, batch, sandbox, rollback\033[0m

\033[1;33m💡 UNIVERSAL SHORTCUTS\033[0m
    \033[1;36mdeep <command> --help\033[0m    # Detailed help for any command
    \033[1;36mdeep version\033[0m             # Show version and logo
"""
    )
    
    parser.add_argument("-v", "--version", action="store_true", help=argparse.SUPPRESS)
    
    sub_parser_container = parser.add_subparsers(dest="command", metavar="")

    # Dynamically load and register all commands from deep.commands
    commands_dir = Path(__file__).parent.parent / "commands"
    cmd_map = {}
    for file in commands_dir.glob("*_cmd.py"):
        base_name = file.name[:-7]
        cmd_name = base_name.replace("_", "-")
        cmd_map[cmd_name] = f"deep.commands.{file.name[:-3]}"

    for cmd_name, module_path in sorted(cmd_map.items()):
        try:
            module = importlib.import_module(module_path)
            if hasattr(module, "setup_parser"):
                module.setup_parser(sub_parser_container)
            else:
                sub_parser_container.add_parser(cmd_name, help=f"Run {cmd_name} command")
        except Exception as e:
            if os.environ.get("DEEP_DEBUG"):
                print(f"Deep: warning: failed to load command {cmd_name}: {e}", file=sys.stderr)

    return parser

def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the DeepGit CLI."""
    parser = build_parser()
    
    # Standardize argv
    if argv is None:
        argv = sys.argv[1:]

    # Handle 'help' alias and no-args
    if not argv:
        parser.print_help()
        return 0

    if argv[0] == "help":
        if len(argv) > 1:
            # deep help commit -> deep commit --help
            cmd = argv[1]
            argv = [cmd, "--help"]
        else:
            parser.print_help()
            return 0

    try:
        args, unknown = parser.parse_known_args(argv)
    except SystemExit:
        return 0 # Argparse handles it

    if args.version or getattr(args, "command", None) == "version":
        from deep.utils.ux import DEEP_LOGO
        print(DEEP_LOGO)
        return 0

    if not getattr(args, "command", None) or getattr(args, "help", False):
        parser.print_help()
        return 0

    # Dispatch Command
    cmd_name = args.command
    module_name = cmd_name.replace("-", "_") + "_cmd"
    
    try:
        module = importlib.import_module(f"deep.commands.{module_name}")
        
        # Pre-execution environment checks
        if args.command not in ("init", "clone"):
            from deep.core.repository import find_repo, DEEP_DIR
            try:
                repo_root = find_repo()
                dg_dir = repo_root / DEEP_DIR
                
                # Crash recovery for sensitive commands
                if args.command in ("commit", "merge", "push", "pull", "rollback", "checkout", "status"):
                    from deep.storage.txlog import TransactionLog
                    txlog = TransactionLog(dg_dir)
                    if txlog.log_path.exists() and txlog.needs_recovery():
                        print(Color.wrap(Color.YELLOW, "Deep: Repository state is inconsistent. Running crash recovery..."), file=sys.stderr)
                        txlog.recover()
            except FileNotFoundError:
                pass

        # Parse args again properly with the full module parser if parse_known_args was used
        # Actually parse_known_args is fine here as we've already registered the parsers.
        args = parser.parse_args()

        # Run logic
        module.run(args)
        
        # Post-execution Auto-Maintenance
        if args.command in ("commit", "push", "pull", "merge", "add", "rm", "mv"):
            try:
                from deep.core.maintenance import run_maintenance
                repo_root = find_repo()
                run_maintenance(repo_root, force=False)
            except Exception:
                pass

    except ImportError:
        # Not a command, try suggestions
        all_cmds = []
        commands_dir = Path(__file__).parent.parent / "commands"
        for file in commands_dir.glob("*_cmd.py"):
            all_cmds.append(file.name[:-7].replace("_", "-"))
            
        suggestion = suggest_command(cmd_name, all_cmds)
        print_error(f"'{cmd_name}' is not a Deep command.")
        if suggestion:
            print(f"Did you mean? {format_command(suggestion)}")
        sys.exit(1)
    except DeepError as e:
        print_error(str(e))
        sys.exit(1)
    except DeepCLIException as e:
        sys.exit(e.code)
    except Exception as e:
        if os.environ.get("DEEP_DEBUG"):
            raise
        print_error(f"Internal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

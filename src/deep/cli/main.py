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
        description="Deep — Next-generation Distributed Version Control System",
        formatter_class=DeepHelpFormatter,
        add_help=False, 
    )
    
    parser.add_argument("-h", "--help", action="store_true", help="Show this help message and exit")
    parser.add_argument("-v", "--version", action="store_true", help="Show version information and exit")
    
    sub_parser_container = parser.add_subparsers(dest="command", metavar="COMMAND")

    # Dynamically load and register all commands from deep.commands
    commands_dir = Path(__file__).parent.parent / "commands"
    # Map command names to modules. Hyphens in command names map to underscores in filenames
    cmd_map = {}
    for file in commands_dir.glob("*_cmd.py"):
        base_name = file.name[:-7] # remove _cmd.py
        cmd_name = base_name.replace("_", "-")
        cmd_map[cmd_name] = f"deep.commands.{file.name[:-3]}"

    # Sort items for consistent registration
    for cmd_name, module_path in sorted(cmd_map.items()):
        try:
            module = importlib.import_module(module_path)
            if hasattr(module, "setup_parser"):
                module.setup_parser(sub_parser_container)
            else:
                # If no parser setup yet, add a placeholder
                sub_parser_container.add_parser(cmd_name, help=f"Run {cmd_name} command")
        except Exception as e:
            if os.environ.get("DEEP_DEBUG"):
                print(f"Deep: warning: failed to load command {cmd_name}: {e}", file=sys.stderr)

    # Categorize commands in the epilog
    epilog_parts = ["\n"]
    for group_header, group_cmds in COMMAND_GROUPS.items():
        epilog_parts.append(format_header(group_header))
        # Only include commands that were actually found/registered
        available_in_group = [c for c in group_cmds if c in cmd_map]
        if available_in_group:
            cmd_line = ", ".join(format_command(c) for c in available_in_group)
            epilog_parts.append(f"  {cmd_line}\n")
    
    epilog_parts.append(format_header("Universal Shortcuts"))
    epilog_parts.append(f"  deep <command> --help    {Color.wrap(Color.DIM, '# Detailed help for any command')}")
    epilog_parts.append(f"  deep version             {Color.wrap(Color.DIM, '# Show version and logo')}\n")
    
    parser.epilog = "\n".join(epilog_parts)
    return parser

def main():
    parser = build_parser()
    
    # Handle 'help' alias and no-args
    if len(sys.argv) == 1:
        print_deep_logo(VERSION)
        parser.print_help()
        return

    if sys.argv[1] == "help":
        if len(sys.argv) > 2:
            # deep help commit -> deep commit --help
            cmd = sys.argv[2]
            sys.argv = [sys.argv[0], cmd, "--help"]
        else:
            print_deep_logo(VERSION)
            parser.print_help()
            return

    # Special handling for -h / --help to show logo first
    if "-h" in sys.argv or "--help" in sys.argv:
        # If it's just 'deep -h', show logo. 
        # If it's 'deep status -h', logo is shown by sub-parser? No, argparse doesn't do that.
        # We only show logo for the main help.
        if len(sys.argv) == 2:
            print_deep_logo(VERSION)

    try:
        args, unknown = parser.parse_known_args()
    except SystemExit:
        return # Argparse handles it

    if args.version or (args.command == "version"):
        print_deep_logo(VERSION)
        return

    if not args.command or args.help:
        print_deep_logo(VERSION)
        parser.print_help()
        return

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

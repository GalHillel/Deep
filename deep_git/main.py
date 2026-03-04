"""
deep_git.main
~~~~~~~~~~~~~~
CLI entry point for Deep Git.

Usage::

    deepgit init [path]
    deepgit add <file> [file ...]
    deepgit commit -m <message>
    deepgit log
    deepgit branch [name]
    deepgit status
    deepgit diff
    deepgit checkout <target>
    deepgit merge <branch>
    deepgit rm <file>
    deepgit reset [--hard] <commit>
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="deepgit",
        description="Deep Git — a robust, concurrency-safe, Git-like VCS.",
    )
    sub = parser.add_subparsers(dest="command")

    # ── init ─────────────────────────────────────────────────────────
    p_init = sub.add_parser("init", help="Initialize a new repository")
    p_init.add_argument("path", nargs="?", default=None, help="Target directory (default: cwd)")

    # ── add ──────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Stage file(s) for the next commit")
    p_add.add_argument("files", nargs="+", help="File(s) to add")

    # ── commit ───────────────────────────────────────────────────────
    p_commit = sub.add_parser("commit", help="Record changes to the repository")
    p_commit.add_argument("-m", "--message", required=True, help="Commit message")

    # ── log ──────────────────────────────────────────────────────────
    sub.add_parser("log", help="Show commit history")

    # ── branch ───────────────────────────────────────────────────────
    p_branch = sub.add_parser("branch", help="List or create branches")
    p_branch.add_argument("name", nargs="?", default=None, help="New branch name")

    # ── status ───────────────────────────────────────────────────────
    sub.add_parser("status", help="Show the working tree status")

    # ── diff ─────────────────────────────────────────────────────────
    sub.add_parser("diff", help="Show unstaged changes")

    # ── checkout ─────────────────────────────────────────────────────
    p_checkout = sub.add_parser("checkout", help="Switch branches or restore files")
    p_checkout.add_argument("target", help="Branch name or commit SHA")

    # ── merge ───────────────────────────────────────────────────────
    p_merge = sub.add_parser("merge", help="Merge a branch into the current branch")
    p_merge.add_argument("branch", help="Branch to merge")

    # ── rm ──────────────────────────────────────────────────────────
    p_rm = sub.add_parser("rm", help="Remove files from the working tree and index")
    p_rm.add_argument("files", nargs="+", help="File(s) to remove")

    # ── reset ───────────────────────────────────────────────────────
    p_reset = sub.add_parser("reset", help="Reset current HEAD to the specified state")
    p_reset.add_argument("--hard", action="store_true", help="Reset the working tree and index")
    p_reset.add_argument("commit", help="Commit SHA to reset to")

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Dynamic import to keep startup fast.
    if args.command == "init":
        from deep_git.commands.init_cmd import run
    elif args.command == "add":
        from deep_git.commands.add_cmd import run
    elif args.command == "commit":
        from deep_git.commands.commit_cmd import run
    elif args.command == "log":
        from deep_git.commands.log_cmd import run
    elif args.command == "branch":
        from deep_git.commands.branch_cmd import run
    elif args.command == "status":
        from deep_git.commands.status_cmd import run
    elif args.command == "diff":
        from deep_git.commands.diff_cmd import run
    elif args.command == "checkout":
        from deep_git.commands.checkout_cmd import run
    elif args.command == "merge":
        from deep_git.commands.merge_cmd import run
    elif args.command == "rm":
        from deep_git.commands.rm_cmd import run
    elif args.command == "reset":
        from deep_git.commands.reset_cmd import run
    else:
        parser.print_help()
        sys.exit(1)

    run(args)


if __name__ == "__main__":
    main()

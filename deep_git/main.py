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
    p_commit.add_argument("-S", "--sign", action="store_true", help="GPG-sign the commit")

    # ── log ──────────────────────────────────────────────────────────
    p_log = sub.add_parser("log", help="Show commit history")
    p_log.add_argument("--oneline", action="store_true", help="Print each commit on a single line")
    p_log.add_argument("-n", "--max-count", type=int, help="Limit the number of commits to output")
    p_log.add_argument("--graph", action="store_true", help="Draw a text-based graphical representation of the commit history")

    # ── branch ───────────────────────────────────────────────────────
    p_branch = sub.add_parser("branch", help="List or create branches")
    p_branch.add_argument("name", nargs="?", default=None, help="New branch name")
    p_branch.add_argument("start_point", nargs="?", default="HEAD", help="Start point (HEAD, SHA, etc.)")

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

    # ── rebase ──────────────────────────────────────────────────────
    p_rebase = sub.add_parser("rebase", help="Rebase the current branch on top of another branch")
    p_rebase.add_argument("branch", help="Branch to rebase onto")

    # ── doctor ──────────────────────────────────────────────────────
    sub.add_parser("doctor", help="Check repository integrity (objects, refs, index)")

    # ── gc ──────────────────────────────────────────────────────────
    p_gc = sub.add_parser("gc", help="Collect garbage unreachable objects")
    p_gc.add_argument("--dry-run", action="store_true", help="Only show what would be removed")
    p_gc.add_argument("--verbose", action="store_true", help="Show detailed work")

    # ── benchmark ───────────────────────────────────────────────────
    p_bench = sub.add_parser("benchmark", help="Run performance benchmarks")
    p_bench.add_argument("--verbose", action="store_true", help="Show detailed results")

    # ── daemon ──────────────────────────────────────────────────────
    p_daemon = sub.add_parser("daemon", help="Start a distributed DeepGit server")
    p_daemon.add_argument("--host", default="127.0.0.1", help="Host to listen on")
    p_daemon.add_argument("--port", type=int, default=8888, help="Port to listen on")

    # ── clone ───────────────────────────────────────────────────────
    p_clone = sub.add_parser("clone", help="Clone a repository into a new directory")
    p_clone.add_argument("url", help="URL (host:port)")
    p_clone.add_argument("dir", nargs="?", help="Optional target directory")

    # ── push ────────────────────────────────────────────────────────
    p_push = sub.add_parser("push", help="Update remote refs along with associated objects")
    p_push.add_argument("url", help="URL (host:port)")
    p_push.add_argument("branch", help="Branch to push")

    # ── fetch ───────────────────────────────────────────────────────
    p_fetch = sub.add_parser("fetch", help="Download objects and refs from another repository")
    p_fetch.add_argument("url", help="URL (host:port)")
    p_fetch.add_argument("sha", help="SHA to fetch")

    # ── web ─────────────────────────────────────────────────────────
    p_web = sub.add_parser("web", help="Launch the Web Dashboard")
    p_web.add_argument("--port", type=int, default=9000, help="Port for dashboard")

    # ── ai ──────────────────────────────────────────────────────────
    p_ai = sub.add_parser("ai", help="AI Assistant")
    p_ai.add_argument("ai_command", nargs="?", default="suggest",
                      choices=["suggest", "analyze", "branch-name", "review", "predict-merge", "predict-push", "cross-repo", "refactor", "cleanup"],
                      help="AI sub-command")
    p_ai.add_argument("--description", default="", help="Description for branch name")
    p_ai.add_argument("--branch", help="Branch for merge prediction")
    p_ai.add_argument("--target", default="main", help="Target branch for prediction")

    # ── batch ───────────────────────────────────────────────────────
    p_batch = sub.add_parser("batch", help="Execute batch operations from a script")
    p_batch.add_argument("script", help="Path to .dgit script file")
    p_batch.add_argument("--fail-fast", action="store_true", dest="fail_fast",
                         help="Stop on first error")


    # ── rm ──────────────────────────────────────────────────────────
    p_rm = sub.add_parser("rm", help="Remove files from the working tree and index")
    p_rm.add_argument("files", nargs="+", help="File(s) to remove")

    # ── reset ───────────────────────────────────────────────────────
    p_reset = sub.add_parser("reset", help="Reset current HEAD to the specified state")
    p_reset.add_argument("--hard", action="store_true", help="Reset the working tree and index")
    p_reset.add_argument("commit", help="Commit SHA to reset to")

    # ── config ──────────────────────────────────────────────────────
    p_config = sub.add_parser("config", help="Get and set repository or global options")
    p_config.add_argument("--global", action="store_true", dest="global_", help="Use global config file")
    p_config.add_argument("key", help="Config key (e.g. user.name)")
    p_config.add_argument("value", nargs="?", help="Value to set")

    # ── p2p ─────────────────────────────────────────────────────────
    p_p2p = sub.add_parser("p2p", help="Distributed P2P operations")
    p_p2p.add_argument("p2p_command", nargs="?", default="list",
                       choices=["start", "list", "sync"],
                       help="P2P sub-command")
    p_p2p.add_argument("--port", type=int, default=9001, help="Port for P2P listener")

    # ── search ──────────────────────────────────────────────────────
    p_search = sub.add_parser("search", help="Search history for pattern")
    p_search.add_argument("pattern", help="Regex pattern to search for")

    # ── audit ───────────────────────────────────────────────────────
    p_audit = sub.add_parser("audit", help="Show the audit log")

    # ── ultra ───────────────────────────────────────────────────────
    p_ultra = sub.add_parser("ultra", help="The ultimate status summary")

    # ── pipeline ────────────────────────────────────────────────────
    p_pipe = sub.add_parser("pipeline", help="CI/CD Pipeline tools")
    p_pipe_sub = p_pipe.add_subparsers(dest="pipeline_command")
    
    p_pipe_run = p_pipe_sub.add_parser("run", help="Run a pipeline")
    p_pipe_run.add_argument("--commit", help="Commit SHA to run pipeline for")
    
    p_pipe_status = p_pipe_sub.add_parser("status", help="Check run status")
    p_pipe_status.add_argument("run_id", help="ID of the pipeline run")
    
    p_pipe_list = p_pipe_sub.add_parser("list", help="List recent runs")

    # ── tag ─────────────────────────────────────────────────────────
    p_tag = sub.add_parser("tag", help="Create, list, or delete a tag object")
    p_tag.add_argument("name", nargs="?", help="Tag name")
    p_tag.add_argument("-a", "--annotate", action="store_true", help="Make an unsigned, annotated tag object")
    p_tag.add_argument("-m", "--message", help="Tag message")

    # ── stash ───────────────────────────────────────────────────────
    p_stash = sub.add_parser("stash", help="Stash the changes in a dirty working directory away")
    p_stash.add_argument("action", nargs="?", choices=["save", "pop", "list"], default="save", help="Stash action to perform")

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
    elif args.command == "config":
        from deep_git.commands.config_cmd import run
    elif args.command == "tag":
        from deep_git.commands.tag_cmd import run
    elif args.command == "stash":
        from deep_git.commands.stash_cmd import run
    elif args.command == "rebase":
        from deep_git.commands.rebase_cmd import run
    elif args.command == "doctor":
        from deep_git.commands.doctor_cmd import run
    elif args.command == "gc":
        from deep_git.commands.gc_cmd import run
    elif args.command == "benchmark":
        from deep_git.commands.benchmark_cmd import run
    elif args.command == "daemon":
        from deep_git.commands.daemon_cmd import run
    elif args.command == "clone":
        from deep_git.commands.clone_cmd import run
    elif args.command == "push":
        from deep_git.commands.push_cmd import run
    elif args.command == "fetch":
        from deep_git.commands.fetch_cmd import run
    elif args.command == "web":
        from deep_git.commands.web_cmd import run
    elif args.command == "ai":
        from deep_git.commands.ai_cmd import run
    elif args.command == "p2p":
        from deep_git.commands.p2p_cmd import run
    elif args.command == "pipeline":
        from deep_git.commands.pipeline_cmd import run
    elif args.command == "search":
        from deep_git.commands.search_cmd import run
    elif args.command == "audit":
        from deep_git.commands.audit_cmd import run
    elif args.command == "ultra":
        from deep_git.commands.ultra_cmd import run
    elif args.command == "batch":
        from deep_git.commands.batch_cmd import run
    else:
        parser.print_help()
        sys.exit(1)

    from deep_git.core.repository import find_repo, DEEP_GIT_DIR
    try:
        # Don't check for init or clone as they create new repos
        if args.command not in ("init", "clone"):
            repo_root = find_repo()
            dg_dir = repo_root / DEEP_GIT_DIR
            
            # 1. Recover incomplete transactions
            from deep_git.core.txlog import TransactionLog
            txlog = TransactionLog(dg_dir)
            if txlog.needs_recovery():
                print("Running crash recovery...", file=sys.stderr)
                txlog.recover()

            # 2. Basic corruption detection for HEAD and branch pointers
            from deep_git.core.refs import resolve_head, list_branches, get_branch
            from deep_git.core.objects import read_object_safe
            
            objects_dir = dg_dir / "objects"
            
            head_sha = resolve_head(dg_dir)
            if head_sha:
                try:
                    read_object_safe(objects_dir, head_sha)
                except (FileNotFoundError, ValueError) as e:
                    print(f"FATAL: Repository corrupted. HEAD points to invalid object {head_sha}. ({e})", file=sys.stderr)
                    sys.exit(1)
                    
            for branch in list_branches(dg_dir):
                branch_sha = get_branch(dg_dir, branch)
                if branch_sha:
                    try:
                        read_object_safe(objects_dir, branch_sha)
                    except (FileNotFoundError, ValueError) as e:
                        print(f"FATAL: Repository corrupted. Branch '{branch}' points to invalid object {branch_sha}. ({e})", file=sys.stderr)
                        sys.exit(1)
                        
    except FileNotFoundError:
        pass # find_repo fails gracefully, commands handle it

    run(args)


if __name__ == "__main__":
    main()

"""
deep.cli.main
~~~~~~~~~~~~~

The primary entry point for the Deep VCS Command Line Interface.

This module orchestrates the entire CLI experience, including:
- High-level command registration and dispatching.
- Beautifully formatted help screens and documentation discovery.
- Global version management and initialization.

All commands are implemented in separate modules under `src/deep/commands/` 
and registered here for a cohesive distribution.
"""

from __future__ import annotations

import argparse
import sys


VERSION = "1.0.0"


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="deep",
        description="DEEP — Next-generation Distributed Version Control System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Core Commands:
  init, add, commit, status, log, diff, branch, checkout, merge, rebase, reset, rm, mv, tag, stash

Remote & Distributed:
  clone, push, pull, fetch, remote, mirror, daemon, p2p, sync

Platform & Server:
  server, repo, user, auth, pr, issue, pipeline

Diagnostics & Dev Tools:
  doctor, benchmark, graph, audit, verify, sandbox, rollback, ultra, batch, search, gc, version

Help:
  deep <command> --help
  deep help
""",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # Group: Core Commands
    # ── init ─────────────────────────────────────────────────────────
    p_init = sub.add_parser(
        "init",
        help="Initialize a new empty Deep repository",
        description="Create an empty Deep repository or reinitialize an existing one.",
        epilog="""
Examples:
  deep init                  # Initialize in current directory
  deep init my-project       # Create 'my-project' and initialize there
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_init.add_argument("path", nargs="?", default=None, help="Target directory (default: current directory)")

    # ── add ──────────────────────────────────────────────────────────
    p_add = sub.add_parser(
        "add",
        help="Add file contents to the staging index",
        description="Add file contents to the staging area (index) to be included in the next commit.",
        epilog="""
Examples:
  deep add file.txt          # Add a specific file
  deep add .                 # Add all changes in the current directory
  deep add src/*.py          # Add specific files using glob patterns
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_add.add_argument("files", nargs="+", help="One or more files to stage")

    # ── commit ───────────────────────────────────────────────────────
    p_commit = sub.add_parser(
        "commit",
        help="Record changes to the repository history",
        description="Create a new commit containing the current contents of the index with a descriptive message.",
        epilog="""
Examples:
  deep commit -m "Fix bug"   # Commit with a manual message
  deep commit --ai           # Use AI to generate a smart commit message
  deep commit -S -m "Signed" # Create a GPG-signed commit for security
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_commit.add_argument("-m", "--message", help="Commit message")
    p_commit.add_argument("--ai", action="store_true", help="Generate message using AI")
    p_commit.add_argument("-S", "--sign", action="store_true", help="Digitally sign the commit")

    # ── status ───────────────────────────────────────────────────────
    p_status = sub.add_parser(
        "status",
        help="Show the working tree and index status",
        description="Displays the state of the working directory and the staging area (index).",
        epilog="""
Examples:
  deep status                # Human-friendly status overview
  deep status --porcelain    # Stable, machine-readable output format
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_status.add_argument("--porcelain", action="store_true", help="Produce machine-readable output")

    # ── log ──────────────────────────────────────────────────────────
    p_log = sub.add_parser(
        "log",
        help="Display commit history logs",
        description="Browse through the commit history of the current branch or specified range.",
        epilog="""
Examples:
  deep log                   # Show full detailed logs
  deep log --oneline         # Concise summary (SHA and message)
  deep log -n 10             # Limit output to the last 10 commits
  deep log --graph           # Visualize history with a text-based graph
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_log.add_argument("--oneline", action="store_true", help="Display each commit on one line")
    p_log.add_argument("-n", "--max-count", type=int, help="Maximum number of commits to show")
    p_log.add_argument("--graph", action="store_true", help="Draw a text-based representation of the commit graph")

    # ── diff ─────────────────────────────────────────────────────────
    p_diff = sub.add_parser(
        "diff",
        help="Show changes between commits or working tree",
        description="Show changes between the working tree and the index, or between two arbitrary commits.",
        epilog="""
Examples:
  deep diff                  # Compare working tree with staging index
  deep diff HEAD             # Compare working tree with the latest commit
  deep diff abc1234 def5678  # Compare two specific commits
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── branch ───────────────────────────────────────────────────────
    p_branch = sub.add_parser(
        "branch",
        help="Manage repository branches",
        description="List, create, or delete branches in the current repository.",
        epilog="""
Examples:
  deep branch                # List all local branches
  deep branch feature        # Create a new branch named 'feature'
  deep branch -d feature     # Delete the 'feature' branch
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_branch.add_argument("name", nargs="?", default=None, help="Name of the branch to create")
    p_branch.add_argument("-d", "--delete", action="store_true", help="Delete the specified branch")
    p_branch.add_argument("start_point", nargs="?", default="HEAD", help="Commit or branch to start from (default: HEAD)")

    # ── checkout ─────────────────────────────────────────────────────
    p_checkout = sub.add_parser(
        "checkout",
        help="Switch branches or restore files",
        description="Switch to a different branch or restore files from a specific commit.",
        epilog="""
Examples:
  deep checkout main         # Switch to the 'main' branch
  deep checkout -b feature   # Create and switch to a new branch 'feature'
  deep checkout abc1234      # Detach HEAD and switch to commit abc1234
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_checkout.add_argument("-f", "--force", action="store_true", help="Force switching even with local changes")
    p_checkout.add_argument("-b", "--branch", help="Create and switch to a new branch")
    p_checkout.add_argument("target", help="Branch name or commit SHA to switch to")

    # ── merge ───────────────────────────────────────────────────────
    p_merge = sub.add_parser(
        "merge",
        help="Merge branches or histories",
        description="Integrate changes from another branch into the current branch.",
        epilog="""
Examples:
  deep merge feature         # Merge 'feature' branch into current branch
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_merge.add_argument("branch", help="Branch name to merge from")

    # ── rm ──────────────────────────────────────────────────────────
    p_rm = sub.add_parser(
        "rm", 
        help="Remove files from working tree and index",
        description="Remove files from the working directory and the staging area.",
        epilog="""
Examples:
  deep rm file.txt           # Delete file and unstage it
  deep rm --cached file.txt  # Keep file locally but remove from index
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rm.add_argument("files", nargs="+", help="Files to remove")
    p_rm.add_argument("--cached", action="store_true", help="Remove from index only")

    # ── mv ──────────────────────────────────────────────────────────
    p_mv = sub.add_parser(
        "mv", 
        help="Move or rename a file or directory",
        description="Move or rename a file, directory, or symlink and update the index.",
        epilog="""
Examples:
  deep mv old.txt new.txt    # Rename a file
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_mv.add_argument("source", help="Source path")
    p_mv.add_argument("destination", help="Destination path")

    # ── reset ───────────────────────────────────────────────────────
    p_reset = sub.add_parser(
        "reset", 
        help="Reset HEAD to a specific state",
        description="Reset the current HEAD to a specified commit, optionally updating index/working tree.",
        epilog="""
Examples:
  deep reset HEAD~1          # Undo the last commit, keeping changes staged
  deep reset --hard HEAD     # Discard all local changes and reset to HEAD
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_reset.add_argument("commit", nargs="?", default="HEAD", help="Commit to reset to (default: HEAD)")
    p_reset.add_argument("--hard", action="store_true", help="Reset index and working tree (discard local changes)")
    p_reset.add_argument("--soft", action="store_true", help="Keep index and working tree (preserve changes)")

    # ── rebase ──────────────────────────────────────────────────────
    p_rebase = sub.add_parser(
        "rebase", 
        help="Reapply commits on top of another base",
        description="Forward-port local commits to the tip of another branch.",
        epilog="""
Examples:
  deep rebase main           # Rebase current branch onto 'main'
  deep rebase --continue     # Continue rebase after resolving conflicts
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rebase.add_argument("branch", nargs="?", help="Branch to rebase onto")
    p_rebase.add_argument("--continue", action="store_true", dest="continue_rebase", help="Continue rebase process")
    p_rebase.add_argument("--abort", action="store_true", help="Abort the rebase operation")

    # ── tag ─────────────────────────────────────────────────────────
    p_tag = sub.add_parser(
        "tag", 
        help="Create or manage release tags",
        description="Create, list, or delete tag objects for marking specific points in history.",
        epilog="""
Examples:
  deep tag v1.0.0            # Create a lightweight tag
  deep tag -a v1.1.0 -m "Rel" # Create an annotated release tag
  deep tag -d v1.0.0         # Delete a tag
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_tag.add_argument("name", nargs="?", help="Tag name")
    p_tag.add_argument("-a", "--annotate", action="store_true", help="Annotate the tag")
    p_tag.add_argument("-m", "--message", help="Tag message")
    p_tag.add_argument("-d", "--delete", action="store_true", help="Delete a tag")

    # ── stash ───────────────────────────────────────────────────────
    p_stash = sub.add_parser(
        "stash", 
        help="Stash local changes temporarily",
        description="Save local changes in a temporary area to work on something else.",
        epilog="""
Examples:
  deep stash save "Work"     # Save current changes to stash
  deep stash pop             # Apply and remove the latest stash
  deep stash list            # View all stashed changes
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_stash.add_argument("action", choices=["push", "save", "pop", "list", "drop", "clear"], nargs="?", default="save", help="Stash operation")

    # ── config ──────────────────────────────────────────────────────
    p_config = sub.add_parser(
        "config", 
        help="Manage repository configuration",
        description="Get and set configuration options for the local repository or globally.",
        epilog="""
Examples:
  deep config user.name "Alice"      # Set local user name
  deep config --global user.email ... # Set global user email
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_config.add_argument("--global", action="store_true", dest="global_", help="Target global config instead of local")
    p_config.add_argument("key", help="Configuration key (e.g., user.name)")
    p_config.add_argument("value", nargs="?", help="Value to set")

    # ── Group: Remote & Distributed
    # ── clone ───────────────────────────────────────────────────────
    p_clone = sub.add_parser(
        "clone",
        help="Clone a repository into a new directory",
        description="Create a local copy of a remote Deep repository.",
        epilog="""
Examples:
  deep clone http://git.io/repo      # Clone from a URL
  deep clone /path/to/local/repo     # Clone from a local path
  deep clone repo --depth 1           # Create a shallow clone
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_clone.add_argument("url", help="Repository URL or local path")
    p_clone.add_argument("dir", nargs="?", help="Optional target directory name")
    p_clone.add_argument("--depth", type=int, help="Truncate history to N commits")
    p_clone.add_argument("--filter", help="Object filtering for partial clones")
    p_clone.add_argument("--shallow-since", help="Shallow clone after a specific date")

    # ── push ────────────────────────────────────────────────────────
    p_push = sub.add_parser(
        "push",
        help="Upload local changes to a remote",
        description="Update remote refs along with associated objects from your local history.",
        epilog="""
Examples:
  deep push origin main      # Push local 'main' to 'origin' remote
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_push.add_argument("url", help="Remote name or URL")
    p_push.add_argument("branch", help="Branch name to push")

    # ── pull ────────────────────────────────────────────────────────
    p_pull = sub.add_parser(
        "pull",
        help="Fetch and merge from a remote",
        description="Fetch from and integrate with another repository or a local branch.",
        epilog="""
Examples:
  deep pull origin main      # Pul 'main' changes from 'origin'
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pull.add_argument("url", help="Remote name or URL")
    p_pull.add_argument("branch", help="Branch name to pull")

    # ── fetch ────────────────────────────────────────────────────────
    p_fetch = sub.add_parser(
        "fetch",
        help="Download objects from a remote",
        description="Download objects and references from another repository without merging.",
        epilog="""
Examples:
  deep fetch origin          # Fetch all branches from 'origin'
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_fetch.add_argument("url", help="Remote name or URL")
    p_fetch.add_argument("sha", nargs="?", help="Specific commit SHA to fetch")

    # ── remote ───────────────────────────────────────────────────────
    p_remote = sub.add_parser(
        "remote",
        help="Manage tracked remote repositories",
        description="Manage the set of 'remotes' whose branches you track.",
        epilog="""
Examples:
  deep remote add origin <url> # Add a new remote
  deep remote list             # Show all registered remotes
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_remote.add_argument("remote_command", choices=["add", "remove", "list"], help="Remote action")
    p_remote.add_argument("name", nargs="?", help="Remote short name")
    p_remote.add_argument("url", nargs="?", help="Remote URL")

    # ── mirror ───────────────────────────────────────────────────────
    p_mirror = sub.add_parser(
        "mirror",
        help="Create a full mirror of a repository",
        description="Create a 1:1 mirror of a repository, including all refs and metadata.",
        epilog="""
Examples:
  deep mirror <url> <path>   # Create a mirror in the specified path
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_mirror.add_argument("url", help="Source repository URL")
    p_mirror.add_argument("path", help="Local directory for the mirror")

    # ── daemon ───────────────────────────────────────────────────────
    p_daemon = sub.add_parser(
        "daemon",
        help="Start the Deep Git network daemon",
        description="Launches a daemon to serve the current repository over the network.",
        epilog="""
Examples:
  deep daemon --port 9090    # Start serving on port 9090
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_daemon.add_argument("--port", type=int, default=9090, help="Listen on this port")

    # ── p2p ─────────────────────────────────────────────────────────
    p_p2p = sub.add_parser(
        "p2p",
        help="P2P discovery and sync",
        description="Discover peers and synchronize data over a decentralized P2P network.",
        epilog="""
Examples:
  deep p2p discover          # Look for peers on local network
  deep p2p sync <peer-id>    # Direct sync with a known peer
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_p2p.add_argument("p2p_command", choices=["discover", "list", "start", "sync", "status"], help="P2P operation")
    p_p2p.add_argument("target", nargs="?", help="Identifier of target peer")
    p_p2p.add_argument("--peer", help="Manual peer address (host:port)")
    p_p2p.add_argument("--port", type=int, help="Port for the P2P listener")

    # ── sync ────────────────────────────────────────────────────────
    p_sync = sub.add_parser(
        "sync",
        help="Smart repository synchronization",
        description="High-level command to synchronize the current branch with its upstream.",
        epilog="""
Examples:
  deep sync                  # Fetch and integrate upstream changes
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── server ───────────────────────────────────────────────────────
    p_server = sub.add_parser(
        "server",
        help="Manage the Deep Git platform server",
        description="Control the lifecycle of the Deep Git platform server process.",
        epilog="""
Examples:
  deep server start          # Start the background server
  deep server stop           # Terminate the server process
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_server.add_argument("server_command", choices=["start", "stop", "status", "restart"], help="Lifecycle command")

    # ── repo ─────────────────────────────────────────────────────────
    p_repo = sub.add_parser(
        "repo",
        help="Manage platform-hosted repositories",
        description="Interface with repositories hosted on the Deep Git platform.",
        epilog="""
Examples:
  deep repo create my-app    # Create a new repo on the platform
  deep repo list             # List all your platform repos
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_repo.add_argument("repo_command", choices=["create", "delete", "list", "clone", "permit"], help="Repo operation")
    p_repo.add_argument("name", nargs="?", help="Repository name")
    p_repo.add_argument("url", nargs="?", help="Optional URL for cloning")
    p_repo.add_argument("--user", help="User to grant permissions to")
    p_repo.add_argument("--role", help="Role (admin/write/read) to assign")

    # ── user ─────────────────────────────────────────────────────────
    p_user = sub.add_parser(
        "user",
        help="Manage platform user accounts",
        description="Manage user profiles and accounts on the Deep Git platform.",
        epilog="""
Examples:
  deep user create bob       # Create a new user profile
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_user.add_argument("user_command", choices=["create", "delete", "list", "info"], help="User operation")
    p_user.add_argument("name", nargs="?", help="Account username")

    # ── auth ─────────────────────────────────────────────────────────
    p_auth = sub.add_parser(
        "auth",
        help="Platform authentication management",
        description="Manage session tokens and login status for the Deep Git platform.",
        epilog="""
Examples:
  deep auth login            # Authenticate with the platform
  deep auth status           # Show current login info
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_auth.add_argument("auth_command", choices=["login", "logout", "status", "token"], help="Auth action")

    # ── pr ───────────────────────────────────────────────────────────
    p_pr = sub.add_parser(
        "pr",
        help="Manage platform Pull Requests",
        description="Create and interact with Pull Requests on the Deep Git platform.",
        epilog="""
Examples:
  deep pr create             # Open a new PR for current branch
  deep pr list               # View open PRs in this repo
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pr.add_argument("pr_command", choices=["create", "list", "show", "merge", "close"], help="PR action")
    p_pr.add_argument("id", nargs="?", help="Pull Request ID")

    # ── issue ────────────────────────────────~~~~~~~~~~~~~~~~~~~~~~~~
    p_issue = sub.add_parser(
        "issue",
        help="Manage platform Issues",
        description="Track bugs and tasks using platform-integrated issues.",
        epilog="""
Examples:
  deep issue create          # Open a new issue
  deep issue list            # List all open issues
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_issue.add_argument("issue_command", choices=["create", "list", "show", "close", "reopen"], help="Issue action")
    p_issue.add_argument("id", nargs="?", help="Issue ID")

    # ── pipeline ────────────────────────────────────────────────────
    p_pipeline = sub.add_parser(
        "pipeline",
        help="Interact with CI/CD Pipelines",
        description="Run, monitor, and manage automated CI/CD pipelines.",
        epilog="""
Examples:
  deep pipeline run          # Execute pipeline for local changes
  deep pipeline status       # Show status of latest runs
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pipeline.add_argument("pipe_command", choices=["run", "list", "status", "log"], help="Pipeline action")
    p_pipeline.add_argument("run_id", nargs="?", help="Specific Run ID") 
    p_pipeline.add_argument("--commit", help="Commit SHA to target")

    # ── web ──────────────────────────────────────────────────────────
    p_web = sub.add_parser(
        "web",
        help="Open the visual dashboard",
        description="Launch an interactive web dashboard for visual repository management.",
        epilog="""
Examples:
  deep web                   # Open dashboard on default port
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_web.add_argument("--port", type=int, default=9000, help="Listen on this port")

    # ── Group: Diagnostics & Dev Tools
    # ── doctor ───────────────────────────────────────────────────────
    p_doctor = sub.add_parser(
        "doctor",
        help="Run repository health checks",
        description="Audit repository health and optionally fix common corruption issues.",
        epilog="""
Examples:
  deep doctor                # Run all diagnostic checks
  deep doctor --fix          # Attempt to resolve found issues
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_doctor.add_argument("--fix", action="store_true", help="Try to fix detected problems")

    # ── benchmark ────────────────────────────────────────────────────
    p_benchmark = sub.add_parser(
        "benchmark",
        help="Performance benchmarking suite",
        description="Measure and analyze the performance of core VCS operations.",
        epilog="""
Examples:
  deep benchmark             # Run default benchmark suite
  deep benchmark --compare-git # Compare performance with native Git
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_benchmark.add_argument("--compare-git", action="store_true", help="Include Git comparison in report")
    p_benchmark.add_argument("--report", action="store_true", help="Export results to JSON")

    # ── graph ────────────────────────────────────────────────────────
    p_graph = sub.add_parser(
        "graph",
        help="Visualize the commit graph",
        description="Renders a text-based visualization of the commit history graph.",
        epilog="""
Examples:
  deep graph                 # Visualize current branch history
  deep graph --all           # Include all branches and tags in graph
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_graph.add_argument("--all", action="store_true", help="Show all references")
    p_graph.add_argument("-n", "--max-count", type=int, default=100, help="Max number of commits")

    # ── audit ────────────────────────────────────────────────────────
    p_audit = sub.add_parser(
        "audit",
        help="Show security audit logs",
        description="Access logs detailing security-relevant actions within the repository.",
        epilog="""
Examples:
  deep audit                 # Show recent security events
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_audit.add_argument("audit_command", choices=["show", "report"], nargs="?", default="show", help="Audit action")

    # ── verify ───────────────────────────────────────────────────────
    p_verify = sub.add_parser(
        "verify",
        help="Verify repository integrity",
        description="Cryptographically verify the integrity of all stored objects.",
        epilog="""
Examples:
  deep verify                # Run full integrity check
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_verify.add_argument("--all", action="store_true", help="Verify all objects")
    p_verify.add_argument("--verbose", action="store_true", help="Detailed check progress")

    # ── sandbox ──────────────────────────────────────────────────────
    p_sandbox = sub.add_parser(
        "sandbox",
        help="Secure command execution",
        description="Execute commands within an isolated, restricted sandbox environment.",
        epilog="""
Examples:
  deep sandbox run "ls"      # Execute 'ls' inside the sandbox
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sandbox.add_argument("sandbox_command", choices=["run", "init"], help="Sandbox action")
    p_sandbox.add_argument("cmd", nargs="?", help="Shell command to execute")

    # ── rollback ─────────────────────────────────────────────────────
    p_rollback = sub.add_parser(
        "rollback",
        help="Undo the last transaction",
        description="Roll back the repository state to before the last transaction via WAL.",
        epilog="""
Examples:
  deep rollback              # Revert the most recent change
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rollback.add_argument("--verify", action="store_true", help="Verify WAL state before rollback")

    # ── ai ──────────────────────────────────────────────────────────
    p_ai = sub.add_parser(
        "ai", 
        help="DeepGit AI assistant tools",
        description="Harness AI power for commit messages, code reviews, and predictions.",
        epilog="""
Examples:
  deep ai suggest            # Suggest a commit message based on changes
  deep ai explain            # Explain changes in plain English
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ai_choices = [
        "suggest", "analyze", "branch-name", "review", 
        "predict-merge", "predict-push", "cross-repo", 
        "refactor", "cleanup", "interactive", "assistant"
    ]
    p_ai.add_argument("ai_command", choices=ai_choices, nargs="?", default="suggest", help="AI tool to use")
    p_ai.add_argument("target", nargs="?", help="Target file/branch/commit")
    p_ai.add_argument("--description", help="Prompt or description for the AI")
    p_ai.add_argument("--source", help="Source branch for prediction")
    p_ai.add_argument("--branch", help="Target branch for prediction")

    # ── ultra ────────────────────────────────────────────────────────
    p_ultra = sub.add_parser(
        "ultra",
        help="Advanced AI refactoring tools",
        description="Deep VCS 'Ultra' AI tools for advanced code optimization and refactoring.",
        epilog="""
Examples:
  deep ultra optimize        # Apply AI-powered code optimizations
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_ultra.add_argument("ultra_command", help="Ultra-command to execute")

    # ── batch ────────────────────────────────────────────────────────
    p_batch = sub.add_parser(
        "batch",
        help="Run atomic batch operations",
        description="Execute a series of VCS operations as a single atomic unit.",
        epilog="""
Examples:
  deep batch script.deep     # Execute commands from a script file
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_batch.add_argument("script", help="Path to the batch script")

    # ── search ───────────────────────────────────────────────────────
    p_search = sub.add_parser(
        "search",
        help="Search in repository history",
        description="Search for text patterns across the entire commit history.",
        epilog="""
Examples:
  deep search "TODO"        # Search for fixed strings
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_search.add_argument("query", help="Text or regex to search for")

    # ── gc ───────────────────────────────────────────────────────────
    p_gc = sub.add_parser(
        "gc",
        help="Run garbage collection",
        description="Cleanup unreachable objects and optimize the internal database.",
        epilog="""
Examples:
  deep gc                    # Clean up and optimize storage
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_gc.add_argument("--dry-run", action="store_true", help="Show what would be removed")
    p_gc.add_argument("-v", "--verbose", action="store_true", help="Show detailed optimization info")

    sub.add_parser("version", help="Show DeepGit version information")

    # ── help ──────────────────────────────────────────────────────────
    sub.add_parser("help", help="Show this help message and exit")

    # ── Plugins ─────────────────────────────────────────────────────
    try:
        from deep.core.repository import find_repo, DEEP_GIT_DIR
        repo_root = find_repo()
        dg_dir = repo_root / DEEP_GIT_DIR
        
        from deep.plugins.plugin import PluginManager
        pm = PluginManager(dg_dir)
        pm.discover()
        
        for cmd_name, handler in pm.commands.items():
            p_plugin = sub.add_parser(cmd_name, help=f"Plugin command: {cmd_name}")
            p_plugin.add_argument("args", nargs=argparse.REMAINDER)
            
        parser.plugin_manager = pm
    except Exception:
        parser.plugin_manager = None

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console()
            console.print(Panel("[bold cyan]DEEP VCS[/bold cyan] — Next-generation Distributed VCS", expand=False))
            parser.print_help()
        except ImportError:
            parser.print_help()
        sys.exit(0)

    # Dynamic import to keep startup fast.
    if args.command == "init":
        from deep.commands.init_cmd import run
    elif args.command == "add":
        from deep.commands.add_cmd import run
    elif args.command == "commit":
        from deep.commands.commit_cmd import run
    elif args.command == "log":
        from deep.commands.log_cmd import run
    elif args.command == "branch":
        from deep.commands.branch_cmd import run
    elif args.command == "status":
        from deep.commands.status_cmd import run
    elif args.command == "graph":
        from deep.commands.graph_cmd import run
    elif args.command == "diff":
        from deep.commands.diff_cmd import run
    elif args.command == "checkout":
        from deep.commands.checkout_cmd import run
    elif args.command == "merge":
        from deep.commands.merge_cmd import run
    elif args.command == "rm":
        from deep.commands.rm_cmd import run
    elif args.command == "mv":
        from deep.commands.mv_cmd import run
    elif args.command == "reset":
        from deep.commands.reset_cmd import run
    elif args.command == "config":
        from deep.commands.config_cmd import run
    elif args.command == "tag":
        from deep.commands.tag_cmd import run
    elif args.command == "stash":
        from deep.commands.stash_cmd import run
    elif args.command == "rebase":
        from deep.commands.rebase_cmd import run
    elif args.command == "doctor":
        from deep.commands.doctor_cmd import run
    elif args.command == "gc":
        from deep.commands.gc_cmd import run
    elif args.command == "benchmark":
        from deep.commands.benchmark_cmd import run
    elif args.command == "daemon":
        from deep.commands.daemon_cmd import run
    elif args.command == "clone":
        from deep.commands.clone_cmd import run
    elif args.command == "push":
        from deep.commands.push_cmd import run
    elif args.command == "fetch":
        from deep.commands.fetch_cmd import run
    elif args.command == "pull":
        from deep.commands.pull_cmd import run
    elif args.command == "remote":
        from deep.commands.remote_cmd import run
    elif args.command == "web":
        from deep.commands.web_cmd import run
    elif args.command == "server":
        from deep.commands.server_cmd import run
    elif args.command == "user":
        from deep.commands.user_cmd import run
    elif args.command == "auth":
        from deep.commands.auth_cmd import run
    elif args.command == "repo":
        from deep.commands.repo_cmd import run
    elif args.command == "pr":
        from deep.commands.pr_cmd import run
    elif args.command == "issue":
        from deep.commands.issue_cmd import run
    elif args.command == "ai":
        from deep.commands.ai_cmd import run
    elif args.command == "p2p":
        from deep.commands.p2p_cmd import run
    elif args.command == "pipeline":
        from deep.commands.pipeline_cmd import run
    elif args.command == "search":
        from deep.commands.search_cmd import run
    elif args.command == "audit":
        from deep.commands.audit_cmd import run
    elif args.command == "ultra":
        from deep.commands.ultra_cmd import run
    elif args.command == "batch":
        from deep.commands.batch_cmd import run
    elif args.command == "verify":
        from deep.commands.verify_cmd import run
    elif args.command == "sandbox":
        from deep.commands.sandbox_cmd import run
    elif args.command == "rollback":
        from deep.commands.rollback_cmd import run
    elif args.command == "version":
        from deep.cli.main import VERSION
        try:
            from rich.console import Console
            Console().print(f"[bold green]Deep VCS[/bold green] version [cyan]{VERSION}[/cyan]")
        except ImportError:
            print(f"Deep VCS version {VERSION}")
        return
    elif args.command == "help":
        try:
            from rich.console import Console
            from rich.panel import Panel
            Console().print(Panel("[bold cyan]DEEP help[/bold cyan]", expand=False))
            parser.print_help()
        except ImportError:
            parser.print_help()
        return
    else:
        # Plugin command check
        pm = getattr(parser, "plugin_manager", None)
        if pm and args.command in pm.commands:
            # Found a plugin command, skip built-in dispatch
            pass
        else:
            parser.print_help()
            sys.exit(1)

    from deep.core.repository import find_repo, DEEP_GIT_DIR
    try:
        if args.command not in ("init", "clone", "version"):
            repo_root = find_repo()
            dg_dir = repo_root / DEEP_GIT_DIR
            
            # Only recover if txlog actually exists and we're not doing a read-only command
            if args.command in ("commit", "merge", "push", "pull", "rollback"):
                from deep.storage.txlog import TransactionLog
                txlog = TransactionLog(dg_dir)
                if txlog.log_path.exists() and txlog.needs_recovery():
                    print("Running crash recovery...", file=sys.stderr)
                    txlog.recover()

            # Corruption detection for doctor and other integrity-sensitive commands
            if args.command in ("doctor",):
                from deep.core.refs import resolve_head, list_branches, get_branch
                from deep.storage.objects import read_object_safe
                
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
        pass 

    # Run plugin command if registered
    pm = getattr(parser, "plugin_manager", None)
    if pm and args.command in pm.commands:
        handler = pm.commands[args.command]
        plugin_args = getattr(args, "args", [])
        handler(plugin_args)
        return

    run(args)


if __name__ == "__main__":
    main()

def legacy_main(argv: list[str] | None = None) -> None:
    print("This command has been renamed to 'deep'. Please use `deep`.", file=sys.stderr)
    sys.exit(1)

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
from deep.core.errors import DeepCLIException

import argparse
import sys
import os
from deep.core.errors import DeepError


VERSION = "1.0.0"


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="deep",
        description="Deep — Next-generation Distributed Version Control System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Core Commands:
  init, add, commit, status, log, diff, branch, checkout, merge, rebase, reset, rm, mv, tag, stash, migrate

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
        description="Create an empty Deep repository or reinitialize an existing one. This sets up the internal .deep structures.",
        epilog="""
Examples:
  deep init                  # Initialize in the current directory
  deep init my-project       # Create 'my-project' directory and initialize there
  deep init /path/to/repo    # Initialize at a specific absolute path
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_init.add_argument("path", nargs="?", default=None, help="The target directory for the repository (default: current directory)")
    p_init.add_argument("--bare", action="store_true", help="Create a bare repository (without a working tree)")

    # ── add ──────────────────────────────────────────────────────────
    p_add = sub.add_parser(
        "add",
        help="Add file contents to the staging index",
        description="Add file contents to the staging area (index) to be included in the next commit. This prepares changes for recording.",
        epilog="""
Examples:
  deep add file.txt          # Add a specific file to the index
  deep add .                 # Add all changed and new files in the current directory
  deep add src/*.py          # Add specific files using glob patterns
  deep add -u                # Add only updated files (not new ones)
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_add.add_argument("files", nargs="+", help="One or more files or directory paths to stage for commit")

    # ── commit ───────────────────────────────────────────────────────
    p_commit = sub.add_parser(
        "commit",
        help="Record changes to the repository history",
        description="Create a new commit containing the current contents of the index with a descriptive message and metadata. Using -a will automatically stage tracked file changes before committing.",
        epilog="""
Examples:
  deep commit -m "Fix bug"          # Create a commit with a manual message
  deep commit -a -m "Commit all"    # Auto-stage tracked changes and commit
  deep commit --ai -a              # AI-generated message with auto-stage
  deep commit -S -m "Signed"        # Create a cryptographically signed commit
  deep commit --allow-empty         # Create a commit even if no changes are staged
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_commit.add_argument("-m", "--message", help="The commit message describing the changes")
    p_commit.add_argument("-a", "--all", action="store_true", help="Automatically stage modified and deleted tracked files before committing (auto-stage). Does NOT include untracked files.")
    p_commit.add_argument("--ai", action="store_true", help="Automatically generate a commit message using Deep AI")
    p_commit.add_argument("-S", "--sign", action="store_true", help="Digitally sign the commit using your identity key")
    p_commit.add_argument("--amend", action="store_true", help="Amend the last commit")
    p_commit.add_argument("--allow-empty", action="store_true", help="Create a commit even if no changes are staged")

    # ── status ───────────────────────────────────────────────────────
    p_status = sub.add_parser(
        "status",
        help="Show the working tree and index status",
        description="Displays the current state of the working directory and the staging area (index).",
        epilog="""
Examples:
  deep status                # Display a human-friendly status overview
  deep status --porcelain    # Generate stable, machine-readable output for scripts
  deep status --verbose      # Show more detailed information about tracked files
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_status.add_argument("--porcelain", action="store_true", help="Produce machine-readable output format")

    # ── log ──────────────────────────────────────────────────────────
    p_log = sub.add_parser(
        "log",
        help="Display commit history logs",
        description="Browse through the commit history of the current branch or a specified commit range.",
        epilog="""
Examples:
  deep log                   # Show full detailed logs for the current branch
  deep log --oneline         # Show a concise summary (short SHA and first line of message)
  deep log -n 10             # Limit output to the most recent 10 commits
  deep log --graph           # Visualize history with an ASCII-based commit graph
  deep log master..feature   # Show commits reachable from 'feature' but not 'master'
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_log.add_argument("--oneline", action="store_true", help="Display each commit entry on a single concise line")
    p_log.add_argument("-n", "--max-count", type=int, help="Limit the number of commits to display")
    p_log.add_argument("--graph", action="store_true", help="Render a text-based representation of the commit graph")

    # ── diff ─────────────────────────────────────────────────────────
    p_diff = sub.add_parser(
        "diff",
        help="Show changes between commits or the working tree",
        description="Show changes between the working tree and the index, or between two arbitrary commit objects.",
        epilog="""
Examples:
  deep diff                  # Compare the working tree with the staging index
  deep diff HEAD             # Compare the working tree with the latest commit
  deep diff abc1234 def5678  # Compare two specific commits by their SHAs
  deep diff --cached         # Show changes currently in the staging area
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_diff.add_argument("--cached", "--staged", action="store_true", help="Show changes currently in the staging area")
    p_diff.add_argument("--stat", action="store_true", help="Show a summary of changes instead of the full diff")
    p_diff.add_argument("revisions", nargs="*", help="Revisions to compare (e.g. HEAD, or commit1 commit2)")

    # ── branch ───────────────────────────────────────────────────────
    p_branch = sub.add_parser(
        "branch",
        help="Manage repository branches",
        description="List, create, or delete branches in the current Deep repository.",
        epilog="""
Examples:
  deep branch                # List all local branches
  deep branch feature        # Create a new local branch named 'feature'
  deep branch -d feature     # Delete the local 'feature' branch
  deep branch -a             # List both local and tracked remote branches
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_branch.add_argument("name", nargs="?", default=None, help="The name of the branch to create")
    p_branch.add_argument("-d", "--delete", action="store_true", help="Delete the specified branch name")
    p_branch.add_argument("-a", "--all", action="store_true", help="List both local and tracked remote branches")
    p_branch.add_argument("-v", "--verbose", action="count", default=0, help="Show more detail (SHA and tracking info)")
    p_branch.add_argument("-vv", action="store_true", help="Show extremely detailed tracking info")
    p_branch.add_argument("start_point", nargs="?", default="HEAD", help="The commit or branch name to start the new branch from (default: HEAD)")

    p_checkout = sub.add_parser(
        "checkout",
        help="Switch branches or restore files",
        description="Switch to a different branch or restore files from a specific commit to the working tree.",
        epilog="""
Examples:
  deep checkout main         # Switch to the 'main' branch
  deep checkout -b feature   # Create a new 'feature' branch and switch to it immediately
  deep checkout abc1234      # Detach HEAD and switch to a specific commit
  deep checkout -- file.txt  # Restore a specific file from the index
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_checkout.add_argument("-f", "--force", action="store_true", help="Force branch switching even if there are uncommitted local changes")
    p_checkout.add_argument("-b", "--branch", action="store_true", help="Create a new branch")
    p_checkout.add_argument("target", help="The branch name or commit SHA to switch to")

    # ── merge ───────────────────────────────────────────────────────
    p_merge = sub.add_parser(
        "merge",
        help="Merge branches or histories",
        description="Integrate changes from another branch into the current checked-out branch.",
        epilog="""
Examples:
  deep merge feature         # Merge the 'feature' branch into the current branch
  deep merge --no-ff dev     # Merge 'dev' and always create a merge commit (no fast-forward)
  deep merge --abort         # Cancel a merge in progress that has conflicts
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_merge.add_argument("branch", nargs="?", default=None, help="The name of the branch to merge into the current one")
    p_merge.add_argument("--abort", action="store_true", help="Abort the current merge operation")

    # ── rm ──────────────────────────────────────────────────────────
    p_rm = sub.add_parser(
        "rm", 
        help="Remove files from the working tree and the index",
        description="Remove files from the working directory and the staging area. This stops tracking the specified files.",
        epilog="""
Examples:
  deep rm file.txt           # Permanently delete file and remove it from the index
  deep rm -r folder/         # Recursively remove a directory and its contents
  deep rm --cached file.txt  # Keep the file in the working tree but remove it from the index
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rm.add_argument("files", nargs="+", help="One or more files or directory paths to remove")
    p_rm.add_argument("--cached", action="store_true", help="Remove from the index only, keeping the file in the working tree")

    # ── mv ──────────────────────────────────────────────────────────
    p_mv = sub.add_parser(
        "mv", 
        help="Move or rename a file or directory",
        description="Move or rename a file, directory, or symlink and update the Deep index accordingly.",
        epilog="""
Examples:
  deep mv old.txt new.txt    # Rename a file and stage the change
  deep mv file.txt docs/      # Move a file to a new directory
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_mv.add_argument("source", help="The source file or directory path")
    p_mv.add_argument("destination", help="The destination file or directory path")

    # ── reset ───────────────────────────────────────────────────────
    p_reset = sub.add_parser(
        "reset", 
        help="Reset HEAD to a specific state",
        description="Reset the current HEAD to a specified commit, optionally updating the index and working tree to match.",
        epilog="""
Examples:
  deep reset HEAD~1          # Undo the last commit, leaving your changes staged in the index
  deep reset --hard HEAD     # Discard all local changes (staged and unstaged) and reset to current HEAD
  deep reset --soft HEAD~2   # Move HEAD back two commits, keeping all changes in the index
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_reset.add_argument("commit", nargs="?", default="HEAD", help="The commit identifier to reset to (default: HEAD)")
    p_reset.add_argument("--hard", action="store_true", help="Reset index and working tree (all local changes will be lost)")
    p_reset.add_argument("--soft", action="store_true", help="Keep index and working tree (all changes are preserved as staged)")

    # ── rebase ──────────────────────────────────────────────────────
    p_rebase = sub.add_parser(
        "rebase", 
        help="Reapply commits on top of another base",
        description="Forward-port local commits to the tip of another branch, maintaining a clean linear history.",
        epilog="""
Examples:
  deep rebase main           # Rebase the current branch onto 'main'
  deep rebase --continue     # Resume the rebase process after resolving conflicts
  deep rebase --abort        # Cancel the rebase and return to the original state
  deep rebase -i HEAD~3      # Start an interactive rebase for the last 3 commits
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rebase.add_argument("branch", nargs="?", help="The branch or commit identifier to rebase onto")
    p_rebase.add_argument("--continue", action="store_true", dest="continue_rebase", help="Continue the rebase process after resolving conflicts")
    p_rebase.add_argument("--abort", action="store_true", help="Abort the rebase operation and restore the original branch state")

    # ── inspect-tree ──────────────────────────────────────────────
    p_inspect_tree = sub.add_parser(
        "inspect-tree",
        help="Internal: Inspect raw tree entries (debug)",
        description="Forensic tool to verify raw tree entry modes and object types in the database.",
    )
    p_inspect_tree.add_argument("sha", help="The SHA-1 hash of the tree object to inspect")

    # ── tag ─────────────────────────────────────────────────────────
    p_tag = sub.add_parser(
        "tag", 
        help="Create or manage release tags",
        description="Create, list, or delete tag objects for marking specific points in history as significant (e.g., releases).",
        epilog="""
Examples:
  deep tag v1.0.0            # Create a lightweight tag at current HEAD
  deep tag -a v1.1.0 -m "Rel" # Create an annotated tag with a message
  deep tag -d v1.0.0         # Delete the specified tag
  deep tag                   # List all existing tags in the repository
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_tag.add_argument("name", nargs="?", help="The name of the tag")
    p_tag.add_argument("-a", "--annotate", action="store_true", help="Create an annotated tag object with metadata")
    p_tag.add_argument("-m", "--message", help="The message accompanying the annotated tag")
    p_tag.add_argument("-d", "--delete", action="store_true", help="Delete the specified tag")

    # ── stash ───────────────────────────────────────────────────────
    p_stash = sub.add_parser(
        "stash", 
        help="Stash temporary changes",
        description="Save local changes in a temporary stack (stash) to clean your working tree for other tasks.",
        epilog="""
Examples:
  deep stash save "Work"     # Save currently staged/unstaged changes to the stash
  deep stash pop             # Apply the latest stash and remove it from the stack
  deep stash list            # View all stashed changes in the current repository
  deep stash apply           # Apply the latest stash without removing it
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_stash.add_argument("action", choices=["push", "save", "pop", "list", "drop", "clear", "apply"], nargs="?", default="save", help="The stash operation to perform (default: save)")

    # ── migrate ─────────────────────────────────────────────────────
    p_migrate = sub.add_parser(
        "migrate",
        help="Upgrade repository to native Deep v2 format",
        description="Repacks history and converts metadata to the high-performance Deep v2 format.",
    )

    # ── config ──────────────────────────────────────────────────────
    p_config = sub.add_parser(
        "config", 
        help="Manage repository configuration",
        description="Get and set configuration options for the local repository or the global user environment.",
        epilog="""
Examples:
  deep config user.name "Alice"      # Set the local user name for this repository
  deep config --global user.email ... # Set the global user email for all repositories
  deep config core.editor vim       # Set the preferred text editor
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_config.add_argument("--global", action="store_true", dest="global_", help="Target the global configuration instead of local")
    p_config.add_argument("key", help="The configuration key (e.g., user.name)")
    p_config.add_argument("value", nargs="?", help="The value to assign to the key")

    # ── Group: Remote & Distributed
    # ── clone ───────────────────────────────────────────────────────
    p_clone = sub.add_parser(
        "clone",
        help="Clone a repository into a new directory",
        description="Create a local copy of a remote Deep repository, including all history and metadata.",
        epilog="""
Examples:
  deep clone https://deep-vcs.dev/user/project  # Clone from a remote URL
  deep clone /path/to/local/repo                  # Clone from a local directory path
  deep clone repo --depth 1                       # Create a shallow clone with truncated history
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_clone.add_argument("url", help="The repository URL or local path to clone from")
    p_clone.add_argument("dir", nargs="?", help="The name of the new directory to clone into")
    p_clone.add_argument("--depth", type=int, help="Limit the history to the specified number of commits")
    p_clone.add_argument("--filter", help="Specify object filtering for a partial clone")
    p_clone.add_argument("--shallow-since", help="Create a shallow clone containing history after a specific date")
    p_clone.add_argument("--mirror", action="store_true", help="Clone as a bare repository with 1:1 ref mapping")

    # ── push ────────────────────────────────────────────────────────
    p_push = sub.add_parser(
        "push",
        help="Upload local changes to a remote",
        description="Update remote references and associated objects in the target repository from your local history.",
        epilog="""
Examples:
  deep push origin main      # Push the local 'main' branch to the 'origin' remote
  deep push --tags origin    # Push all local tags to the remote
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_push.add_argument("url", nargs="?", help="The remote name (e.g., 'origin') or a direct URL")
    p_push.add_argument("branch", nargs="?", help="The name of the branch to push")
    p_push.add_argument("-u", "--set-upstream", action="store_true", help="Set upstream tracking for the branch")
    p_push.add_argument("--force", action="store_true", help="Force the push even if it's non-fast-forward")

    # ── pull ────────────────────────────────────────────────────────
    p_pull = sub.add_parser(
        "pull",
        help="Fetch and merge changes from a remote",
        description="Fetch changes from another repository or local branch and integrate them into the current branch.",
        epilog="""
Examples:
  deep pull origin main      # Pull changes from the 'main' branch of the 'origin' remote
  deep pull --rebase origin  # Fetch and rebase local changes onto the remote branch
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pull.add_argument("url", nargs="?", help="The remote name or URL to pull from")
    p_pull.add_argument("branch", nargs="?", help="The name of the branch to integrate")

    # ── fetch ────────────────────────────────────────────────────────
    p_fetch = sub.add_parser(
        "fetch",
        help="Download objects and references from another repository",
        description="Download objects, branches, and tags from a remote repository without integrating them into your current local branches.",
        epilog="""
Examples:
  deep fetch origin          # Fetch all branches and objects from the 'origin' remote
  deep fetch --all           # Fetch updates from all registered remotes
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_fetch.add_argument("url", help="The remote name or URL to fetch from")
    p_fetch.add_argument("sha", nargs="?", help="A specific commit SHA to fetch (optional)")

    # ── ls-remote ────────────────────────────────────────────────────
    p_ls_remote = sub.add_parser(
        "ls-remote",
        help="List references in a remote repository",
        description="Connect to a remote repository and output its available references (branches, tags) and their target SHAs.",
    )
    p_ls_remote.add_argument("url", help="The remote name or URL")

    # ── remote ───────────────────────────────────────────────────────
    p_remote = sub.add_parser(
        "remote",
        help="Manage tracked remote repositories",
        description="Manage the list of remote repositories ('remotes') that you track for synchronization.",
        epilog="""
Examples:
  deep remote add origin <url> # Track a new remote repository named 'origin'
  deep remote remove origin    # Stop tracking the 'origin' remote
  deep remote list             # Display all currently registered remotes
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_remote.add_argument("remote_command", choices=["add", "remove", "list"], help="The remote management action to perform")
    p_remote.add_argument("name", nargs="?", help="The short name for the remote")
    p_remote.add_argument("url", nargs="?", help="The URL of the remote repository")

    # ── mirror ───────────────────────────────────────────────────────
    p_mirror = sub.add_parser(
        "mirror",
        help="Create a full 1:1 mirror of a repository",
        description="Create a complete mirror of a Deep repository, including all references, branches, and internal metadata.",
        epilog="""
Examples:
  deep mirror https://deep-vcs.dev/repo /local/mirror # Create a mirror at the specified path
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_mirror.add_argument("url", help="The URL of the source repository to mirror")
    p_mirror.add_argument("path", help="The local directory path to store the mirrored repository")

    # ── daemon ───────────────────────────────────────────────────────
    p_daemon = sub.add_parser(
        "daemon",
        help="Start the Deep network daemon",
        description="Launch a background daemon process to serve the current repository over the network to other Deep clients.",
        epilog="""
Examples:
  deep daemon --port 9090    # Start the daemon listening on port 9090
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_daemon.add_argument("--port", type=int, default=9090, help="The network port to listen on (default: 9090)")

    # ── p2p ─────────────────────────────────────────────────────────
    p_p2p = sub.add_parser(
        "p2p",
        help="P2P discovery and direct synchronization",
        description="Discover nearby peers and synchronize repository data over a decentralized Peer-to-Peer network.",
        epilog="""
Examples:
  deep p2p discover          # Scan the local network for Deep peers
  deep p2p sync <peer-id>    # Initiate a direct synchronization with a specific peer
  deep p2p start             # Start the P2P listener for decentralized discovery
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_p2p.add_argument("p2p_command", choices=["discover", "list", "start", "sync", "status"], help="The P2P operation to execute")
    p_p2p.add_argument("target", nargs="?", help="The identifier of the target peer for operations like 'sync'")
    p_p2p.add_argument("--peer", help="Manually specify a peer address in 'host:port' format")
    p_p2p.add_argument("--port", type=int, help="The port to use for the P2P listener")

    # ── sync ────────────────────────────────────────────────────────
    p_sync = sub.add_parser(
        "sync",
        help="Smart repository synchronization",
        description="High-level orchestration command to automatically synchronize the current branch with its upstream counterpart.",
        epilog="""
Examples:
  deep sync                  # Perform a smart fetch and integration of upstream changes
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sync.add_argument("--peer", type=str, help="Manually specify a peer address or path for synchronization")

    # ── show ────────────────────────────────────────────────────────
    p_show = sub.add_parser(
        "show",
        help="Show various types of objects",
        description="Show one or more objects (commits, tags, trees) with their content and metadata.",
        epilog="""
Examples:
  deep show HEAD             # Show the last commit and its diff
  deep show abc1234          # Show a specific commit or object
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_show.add_argument("object", nargs="?", default="HEAD", help="The object identifier to show (default: HEAD)")

    # ── ls-tree ─────────────────────────────────────────────────────
    p_ls_tree = sub.add_parser(
        "ls-tree",
        help="List the contents of a tree object",
        description="Displays the contents of a tree object, similar to `ls -l` but for the Deep database.",
        epilog="""
Examples:
  deep ls-tree HEAD          # List files in the current commit
  deep ls-tree abc1234       # List contents of a specific tree or commit
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_ls_tree.add_argument("treeish", help="The tree or commit identifier to list")
    p_ls_tree.add_argument("-r", "--recursive", action="store_true", help="Recurse into sub-trees")

    # ── server ───────────────────────────────────────────────────────
    p_server = sub.add_parser(
        "server",
        help="Manage the Deep platform server",
        description="Control the lifecycle of the Deep platform server process (start, stop, restart, status).",
        epilog="""
Examples:
  deep server start          # Launch the Deep background server
  deep server stop           # Gracefully terminate the server process
  deep server status         # Check if the server is currently running
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_server.add_argument("server_command", choices=["start", "stop", "status", "restart"], help="The lifecycle command to execute")

    # ── repo ─────────────────────────────────────────────────────────
    p_repo = sub.add_parser(
        "repo",
        help="Manage platform-hosted repositories",
        description="Interface with and manage repositories hosted on the Deep platform.",
        epilog="""
Examples:
  deep repo create my-app    # Create a new repository on the Deep platform
  deep repo list             # List all repositories you have access to on the platform
  deep repo permit --user bob --role write # Grant 'write' access to user 'bob'
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_repo.add_argument("repo_command", choices=["create", "delete", "list", "clone", "permit"], help="The repository operation to perform")
    p_repo.add_argument("name", nargs="?", help="The name of the repository")
    p_repo.add_argument("url", nargs="?", help="The platform URL for cloning (optional)")
    p_repo.add_argument("--user", help="The platform username to target for permissions")
    p_repo.add_argument("--role", help="The access role (admin/write/read) to assign to the user")

    # ── user ─────────────────────────────────────────────────────────
    p_user = sub.add_parser(
        "user",
        help="Manage platform user accounts",
        description="Manage user profiles, settings, and accounts on the Deep platform.",
        epilog="""
Examples:
  deep user create bob       # Create a new user profile named 'bob'
  deep user info alice       # Display detailed information for user 'alice'
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_user.add_argument("user_command", choices=["add", "remove", "list", "info", "show"], help="The user account operation to perform")
    p_user.add_argument("username", nargs="?", help="The username of the account")
    p_user.add_argument("public_key", nargs="?", help="The public SSH key for authentication")
    p_user.add_argument("email", nargs="?", help="The email address associated with the account")
    p_user.add_argument("--username", dest="username_flag", help="The username (alternative to positional)")
    p_user.add_argument("--public-key", dest="public_key_flag", help="The public key (alternative to positional)")
    p_user.add_argument("--email", dest="email_flag", help="The email (alternative to positional)")

    # ── auth ─────────────────────────────────────────────────────────
    p_auth = sub.add_parser(
        "auth",
        help="Platform authentication management",
        description="Manage session tokens, credentials, and login status for the Deep platform.",
        epilog="""
Examples:
  deep auth login            # Interactively authenticate with the Deep platform
  deep auth status           # Display the current authentication status and active user
  deep auth logout           # Clear local session tokens and logout
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_auth.add_argument("auth_command", choices=["login", "logout", "status", "token"], help="The authentication action to perform")

    # ── pr ───────────────────────────────────────────────────────────
    from deep.commands import pr_cmd
    p_pr = sub.add_parser(
        "pr",
        help="Manage platform Pull Requests",
        description=pr_cmd.get_description(),
        epilog=pr_cmd.get_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pr.add_argument("pr_command", choices=["create", "list", "show", "merge", "close", "reopen", "sync", "comment", "reply", "resolve", "review"], help="The Pull Request action to perform")
    p_pr.add_argument("id", nargs="?", help="The numerical ID of the Pull Request")
    p_pr.add_argument("thread", nargs="?", help="The numerical ID of the Thread (for reply/resolve)")
    p_pr.add_argument("--verbose", action="store_true", help="Enable verbose output for API requests")
    p_pr.add_argument("-t", "-m", "--title", "--message", dest="title", help="PR title (for create)")
    p_pr.add_argument("-d", "--description", help="PR description (for create)")
    p_pr.add_argument("--head", help="Source branch (for create)")
    p_pr.add_argument("--base", help="Target branch (for create)")

    # ── issue ────────────────────────────────~~~~~~~~~~~~~~~~~~~~~~~~
    from deep.commands import issue_cmd
    p_issue = sub.add_parser(
        "issue",
        help="Manage platform Issues",
        description=issue_cmd.get_description(),
        epilog=issue_cmd.get_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_issue.add_argument("issue_command", choices=["create", "list", "show", "close", "reopen", "sync"], help="The issue tracking action to perform")
    p_issue.add_argument("id", nargs="?", help="The numerical ID of the issue")
    p_issue.add_argument("--verbose", action="store_true", help="Enable verbose output for API requests")
    p_issue.add_argument("-t", "-m", "--title", "--message", dest="title", help="Issue title (for create)")
    p_issue.add_argument("-d", "--description", help="Issue description (for create)")
    p_issue.add_argument("--type", help="Issue type (e.g. bug, feature)")
    p_issue.add_argument("--priority", help="Issue priority (e.g. high, low)")

    # ── pipeline ────────────────────────────────────────────────────
    from deep.commands import pipeline_cmd
    p_pipeline = sub.add_parser(
        "pipeline",
        help="Interact with CI/CD Pipelines",
        description=pipeline_cmd.get_description(),
        epilog=pipeline_cmd.get_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_pipeline.add_argument("pipe_command", choices=["run", "trigger", "list", "status", "sync"], help="The CI/CD pipeline action to perform")
    p_pipeline.add_argument("id", nargs="?", help="The specific Pipeline Run ID") 
    p_pipeline.add_argument("--commit", help="Target a specific commit SHA for the pipeline run")
    p_pipeline.add_argument("--verbose", action="store_true", help="Enable verbose output for API requests")

    # ── studio ──────────────────────────────────────────────────────────
    p_studio = sub.add_parser(
        "studio",
        help="Open the visual Deep Studio dashboard",
        description="Launch an interactive, browser-based platform for visual repository management and history browsing.",
        epilog="""
Examples:
  deep studio                   # Open the Deep Studio dashboard on the default port (9000)
  deep studio --port 8080       # Start the dashboard on port 8080
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_studio.add_argument("--port", type=int, default=9000, help="The network port to listen on (default: 9000)")

    # ── commit-graph ──────────────────────────────────────────────────
    p_cg = sub.add_parser(
        "commit-graph",
        help="Manage the commit graph index",
        description="Manage the binary commit graph index for accelerated history traversal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_cg.add_argument("cg_command", choices=["write", "verify", "clear"], help="The commit-graph operation to perform")

    p_doctor = sub.add_parser(
        "doctor",
        help="Run repository health checks",
        description="Audit the health of the local Deep repository and optionally fix common corruption or configuration issues.",
        epilog="""
Examples:
  deep doctor                # Run a comprehensive suite of diagnostic checks
  deep doctor --fix          # Attempt to automatically resolve any detected issues
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_doctor.add_argument("--fix", action="store_true", help="Attempt to automatically repair detected repository problems")

    # ── benchmark ────────────────────────────────────────────────────
    p_benchmark = sub.add_parser(
        "benchmark",
        help="Performance benchmarking suite",
        description="Measure and analyze the performance of core Deep VCS operations.",
        epilog="""
Examples:
  deep benchmark                 # Run the default performance benchmark suite
  deep benchmark --compare-legacy # Compare performance with legacy VCS (Deep)
  deep benchmark --report        # Export the benchmark results to a JSON file
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_benchmark.add_argument("--compare-legacy", "--compare-deep", dest="compare_git", action="store_true", help="Include legacy VCS comparison (Deep) for performance baseline")
    p_benchmark.add_argument("--report", action="store_true", help="Generate and export a detailed JSON performance report")

    # ── graph ────────────────────────────────────────────────────────
    p_graph = sub.add_parser(
        "graph",
        help="Visualize the commit graph",
        description="Renders a text-based ASCII visualization of the commit history graph, showing branch relationships and merge points.",
        epilog="""
Examples:
  deep graph                 # Visualize history for the current branch
  deep graph --all           # Include all branches and tags in the visualization
  deep graph -n 20           # Limit the graph to the most recent 20 commits
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_graph.add_argument("--all", action="store_true", help="Include all references (branches and tags) in the graph")
    p_graph.add_argument("-n", "--max-count", type=int, default=100, help="Maximum number of commits to display in the graph (default: 100)")

    # ── audit ────────────────────────────────────────────────────────
    p_audit = sub.add_parser(
        "audit",
        help="Show security and action audit logs",
        description="Access detailed logs recording security-sensitive actions and administrative changes within the repository.",
        epilog="""
Examples:
  deep audit show            # Display recent security events in the terminal
  deep audit report          # Generate a comprehensive security audit report
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_audit.add_argument("audit_command", choices=["show", "report", "scan"], nargs="?", default="show", help="The audit action to perform (default: show)")

    # ── verify ───────────────────────────────────────────────────────
    p_verify = sub.add_parser(
        "verify",
        help="Verify repository object integrity",
        description="Cryptographically verify the integrity of all stored objects (commits, trees, blobs) using their SHA-1 hashes.",
        epilog="""
Examples:
  deep verify                # Run a full integrity check on all reachable objects
  deep verify --all          # Verify every object in the database, including unreachable ones
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_verify.add_argument("--all", action="store_true", help="Verify all objects in the database, not justreachable ones")
    p_verify.add_argument("--verbose", action="store_true", help="Display detailed progress during the verification process")

    # ── fsck ─────────────────────────────────────────────────────────
    p_fsck = sub.add_parser(
        "fsck",
        help="Verify object connectivity and validity",
        description="Check the internal consistency and connectivity of the commit graph, tree structures, and data blobs.",
        epilog="""
Examples:
  deep fsck                  # Perform a comprehensive repository consistency check
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── repack ───────────────────────────────────────────────────────
    p_repack = sub.add_parser(
        "repack",
        help="Consolidate objects into packfiles and generate bitmaps",
        description="Optimize the object database by packing loose objects into efficient packfiles and generating reachability bitmaps.",
        epilog="""
Examples:
  deep repack                # Consolidate objects and generate bitmaps
  deep repack --no-bitmaps   # Repack without generating bitmaps
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_repack.add_argument("--no-bitmaps", action="store_false", dest="bitmaps", default=True, help="Disable bitmap generation")

    # ── sandbox ──────────────────────────────────────────────────────
    p_sandbox = sub.add_parser(
        "sandbox",
        help="Execute commands in a secure environment",
        description="Execute potentially unsafe commands within an isolated and restricted sandbox environment for safety.",
        epilog="""
Examples:
  deep sandbox run "ls -R"   # Execute the 'ls -R' command inside the secure sandbox
  deep sandbox init          # Initialize the sandbox environment for the first time
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_sandbox.add_argument("sandbox_command", choices=["run", "init"], help="The sandbox action to perform")
    p_sandbox.add_argument("cmd", nargs="?", help="The shell command string to execute within the sandbox")

    # ── rollback ─────────────────────────────────────────────────────
    p_rollback = sub.add_parser(
        "rollback",
        help="Undo the most recent transaction",
        description="Roll back the repository state to its condition prior to the last transaction using the Write-Ahead Log (WAL).",
        epilog="""
Examples:
  deep rollback              # Restore the repository to its state before the last successful operation
  deep rollback --verify     # Verify the WAL integrity before performing the rollback
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_rollback.add_argument("commit", nargs="?", default=None, help="The commit to rollback to (default: parent of current HEAD)")
    p_rollback.add_argument("--verify", action="store_true", help="Perform a verification check on the WAL state before rolling back")

    # ── ai ──────────────────────────────────────────────────────────
    p_ai = sub.add_parser(
        "ai", 
        help="Deep AI assistant tools",
        description="Harness the power of AI for generating commit messages, performing code reviews, and predicting merge outcomes.",
        epilog="""
Examples:
  deep ai suggest            # Generate a suggested commit message based on staged changes
  deep ai explain            # Provide a natural language explanation of the recent changes
  deep ai review             # Perform an automated AI code review of current changes
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ai_choices = [
        "suggest", "generate", "analyze", "branch-name", "review", 
        "predict-merge", "predict-push", "cross-repo", 
        "refactor", "cleanup", "interactive", "assistant"
    ]
    p_ai.add_argument("ai_command", choices=ai_choices, nargs="?", default="suggest", help="The Deep AI tool to invoke (default: suggest)")
    p_ai.add_argument("target", nargs="?", help="The target file, branch, or commit SHA for the AI tool")
    p_ai.add_argument("--description", help="Provide an additional prompt or description to guide the AI")
    p_ai.add_argument("--source", help="The source branch for predictive merge analysis")
    p_ai.add_argument("--branch", help="The target branch for predictive merge analysis")

    # ── ultra ────────────────────────────────────────────────────────
    p_ultra = sub.add_parser(
        "ultra",
        help="Advanced system optimization tools",
        description="Access 'Ultra' level tools to run aggressive garbage collection, object repacking, and commit graph rebuilding in a single optimized pass.",
        epilog="""
Examples:
  deep ultra                 # Run the full Deep optimization suite
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── batch ────────────────────────────────────────────────────────
    p_batch = sub.add_parser(
        "batch",
        help="Execute atomic batch VCS operations",
        description="Run a sequence of Deep operations defined in a script as a single atomic transaction.",
        epilog="""
Examples:
  deep batch script.deep     # Execute the sequence of commands defined in 'script.deep'
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_batch.add_argument("script", help="The filesystem path to the batch operation script file")

    # ── search ───────────────────────────────────────────────────────
    p_search = sub.add_parser(
        "search",
        help="Search through repository history",
        description="Locate text patterns or regular expressions across the entire commit history and all tree objects.",
        epilog="""
Examples:
  deep search "TODO"        # Search for the literal string "TODO" in all historical versions
  deep search "^fixed:"     # Search using a regular expression
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_search.add_argument("query", help="The text string or regular expression to search for")

    # ── gc ───────────────────────────────────────────────────────────
    p_gc = sub.add_parser(
        "gc",
        help="Run repository garbage collection",
        description="Clean up unreachable objects and optimize the internal object database to reclaim storage space.",
        epilog="""
Examples:
  deep gc                    # Execute garbage collection and database optimization
  deep gc --dry-run          # List objects that would be removed without deleting them
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_gc.add_argument("--dry-run", action="store_true", help="Display what would be cleaned up without making changes")
    p_gc.add_argument("-v", "--verbose", action="store_true", help="Display detailed information during the optimization process")
    p_gc.add_argument("--prune", type=int, default=3600, help="Only prune unreachable objects older than this (seconds). Default 1h.")
    
    # ── maintenance ──────────────────────────────────────────────────
    p_maint = sub.add_parser(
        "maintenance",
        help="Run repository maintenance tasks",
        description="Optimize the repository by repacking objects, updating indices, and pruning unreachable data.",
        epilog="""
Examples:
  deep maintenance           # Run scheduled maintenance tasks
  deep maintenance --force   # Force run all maintenance tasks immediately
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_maint.add_argument("--force", action="store_true", help="Force run maintenance even if recently completed")

    sub.add_parser("version", help="Show Deep version information")

    # ── debug-tree (Diagnostics) ────────────────────────────────────
    p_debug = sub.add_parser(
        "debug-tree",
        help="Inspect tree contents with hidden character visibility",
        description="Forensic tool to inspect Deep tree objects. Uses repr() to reveal hidden characters for debugging purposes.",
        epilog="""
Examples:
  deep debug-tree <sha>      # Reveal hidden characters in the specified tree or commit object
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_debug.add_argument("sha", nargs="?", help="The SHA-1 hash of the tree or commit object to inspect")

    # ── help ──────────────────────────────────────────────────────────
    p_help = sub.add_parser("help", help="Show this help message and exit")
    p_help.add_argument("subcommand", nargs="?", help="The command to show help for")

    # ── Plugins ─────────────────────────────────────────────────────
    try:
        from deep.core.repository import find_repo, DEEP_DIR # type: ignore[import]
        repo_root = find_repo()
        dg_dir = repo_root / DEEP_DIR
        from deep.plugins.plugin import PluginManager  # type: ignore[import]
        pm = PluginManager(dg_dir)
        if pm:
            pm.discover()
            for cmd_name, _ in pm.commands.items():
                p_plugin = sub.add_parser(cmd_name, help=f"Plugin command: {cmd_name}")
                p_plugin.add_argument("args", nargs=argparse.REMAINDER)
                
            setattr(parser, "plugin_manager", pm)
        else:
            setattr(parser, "plugin_manager", None)
    except Exception:
        setattr(parser, "plugin_manager", None)

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        try:
            from rich.console import Console # type: ignore[import]
            from rich.panel import Panel # type: ignore[import]
            from deep.core.repository import find_repo # type: ignore[import]
            console = Console()
            console.print(Panel("[bold cyan]Deep[/bold cyan] — Next-generation Distributed VCS", expand=False))
            parser.print_help()
        except ImportError:
            parser.print_help()
        return 0

    # Dynamic import to keep startup fast.
    if args.command == "init":
        from deep.commands.init_cmd import run # type: ignore[import]
    elif args.command == "ls-remote":
        from deep.commands.ls_remote_cmd import run # type: ignore[import]
    elif args.command == "clone":
        from deep.commands.clone_cmd import run # type: ignore[import]
    elif args.command == "fetch":
        from deep.commands.fetch_cmd import run # type: ignore[import]
    elif args.command == "push":
        from deep.commands.push_cmd import run # type: ignore[import]
    elif args.command == "pull":
        from deep.commands.pull_cmd import run # type: ignore[import]
    elif args.command == "remote":
        from deep.commands.remote_cmd import run # type: ignore[import]
    elif args.command == "migrate":
        from deep.commands.migrate_cmd import migrate_cmd as run # type: ignore[import]
    elif args.command == "add":
        from deep.commands.add_cmd import run # type: ignore[import]
    elif args.command == "commit":
        from deep.commands.commit_cmd import run # type: ignore[import]
    elif args.command == "log":
        from deep.commands.log_cmd import run # type: ignore[import]
    elif args.command == "branch":
        from deep.commands.branch_cmd import run # type: ignore[import]
    elif args.command == "status":
        from deep.commands.status_cmd import run # type: ignore[import]
    elif args.command == "graph":
        from deep.commands.graph_cmd import run # type: ignore[import]
    elif args.command == "diff":
        from deep.commands.diff_cmd import run # type: ignore[import]
    elif args.command == "checkout":
        from deep.commands.checkout_cmd import run # type: ignore[import]
    elif args.command == "merge":
        from deep.commands.merge_cmd import run # type: ignore[import]
    elif args.command == "inspect-tree":
        from deep.commands.inspect_tree_cmd import run # type: ignore[import]
    elif args.command == "commit-graph":
        from deep.commands.commit_graph_cmd import run # type: ignore[import]
    elif args.command == "fsck":
        from deep.commands.fsck_cmd import run # type: ignore[import]
    elif args.command == "rm":
        from deep.commands.rm_cmd import run # type: ignore[import]
    elif args.command == "mv":
        from deep.commands.mv_cmd import run # type: ignore[import]
    elif args.command == "reset":
        from deep.commands.reset_cmd import run # type: ignore[import]
    elif args.command == "config":
        from deep.commands.config_cmd import run # type: ignore[import]
    elif args.command == "tag":
        from deep.commands.tag_cmd import run # type: ignore[import]
    elif args.command == "stash":
        from deep.commands.stash_cmd import run # type: ignore[import]
    elif args.command == "rebase":
        from deep.commands.rebase_cmd import run # type: ignore[import]
    elif args.command == "repack":
        from deep.commands.repack_cmd import run # type: ignore[import]
    elif args.command == "doctor":
        from deep.commands.doctor_cmd import run # type: ignore[import]
    elif args.command == "gc":
        from deep.commands.gc_cmd import run # type: ignore[import]
    elif args.command == "benchmark":
        from deep.commands.benchmark_cmd import run # type: ignore[import]
    elif args.command == "daemon":
        from deep.commands.daemon_cmd import run # type: ignore[import]
    elif args.command == "studio":
        from deep.commands.studio_cmd import run # type: ignore[import]
    elif args.command == "issue":
        from deep.commands.issue_cmd import run
    elif args.command == "pr":
        from deep.commands.pr_cmd import run
    elif args.command == "pipeline":
        from deep.commands.pipeline_cmd import run
    elif args.command == "p2p":
        from deep.commands.p2p_cmd import run
    elif args.command == "user":
        from deep.commands.user_cmd import run
    elif args.command == "auth":
        from deep.commands.auth_cmd import run
    elif args.command == "repo":
        from deep.commands.repo_cmd import run
    elif args.command == "sync":
        from deep.commands.sync_cmd import run
    elif args.command == "show":
        from deep.commands.show_cmd import run
    elif args.command == "ls-tree":
        from deep.commands.ls_tree_cmd import run
    elif args.command == "search":
        from deep.commands.search_cmd import run
    elif args.command == "server":
        from deep.commands.server_cmd import run
    elif args.command == "daemon":
        from deep.commands.daemon_cmd import run
    elif args.command == "mirror":
        from deep.commands.mirror_cmd import run
    elif args.command == "audit":
        from deep.commands.audit_cmd import run # type: ignore[import]
    elif args.command == "ultra":
        from deep.commands.ultra_cmd import run # type: ignore[import]
    elif args.command == "batch":
        from deep.commands.batch_cmd import run # type: ignore[import]
    elif args.command == "verify":
        from deep.commands.verify_cmd import run # type: ignore[import]
    elif args.command == "sandbox":
        from deep.commands.sandbox_cmd import run # type: ignore[import]
    elif args.command == "ai":
        from deep.commands.ai_cmd import run # type: ignore[import]
    elif args.command == "rollback":
        from deep.commands.rollback_cmd import run # type: ignore[import]
    elif args.command == "debug-tree":
        from deep.commands.debug_cmd import run_debug_tree as run # type: ignore[import]
    elif args.command == "version":
        ver_str = VERSION
        try:
            from rich.console import Console # type: ignore[import]
            Console().print(f"[bold green]Deep[/bold green] version [cyan]{ver_str}[/cyan]")
        except ImportError:
            print(f"Deep version {ver_str}")
        return
    elif args.command == "maintenance":
        from deep.core.maintenance import run_maintenance # type: ignore[import]
        from deep.core.repository import find_repo # type: ignore[import]
        try:
            repo_root = find_repo()
            run_maintenance(repo_root, force=getattr(args, "force", False))
        except FileNotFoundError:
            print("Deep: error: not a repository", file=sys.stderr)
            raise DeepCLIException(1)
        return
    elif args.command == "help":
        if args.subcommand:
            # We must find the subparser for this command
            # Since build_parser is a bit monolithic, we can just call build_parser() 
            # and search in its actions.
            found = False
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    if args.subcommand in action.choices:
                        action.choices[args.subcommand].print_help()
                        found = True
                        break
            if not found:
                print(f"Deep: error: unknown command '{args.subcommand}'", file=sys.stderr)
                parser.print_help()
        else:
            try:
                from rich.console import Console # type: ignore[import]
                from rich.panel import Panel # type: ignore[import]
                Console().print(Panel("[bold cyan]Deep Help[/bold cyan]", expand=False))
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
            raise DeepCLIException(1)

    from deep.core.repository import find_repo, DEEP_DIR # type: ignore[import]
    try:
        if args.command not in ("init", "clone", "version"):
            repo_root = find_repo()
            dg_dir = repo_root / DEEP_DIR
            
            # Only recover if txlog actually exists and we're not doing a read-only command
            if args.command in ("commit", "merge", "push", "pull", "rollback", "checkout", "status"):
                from deep.storage.txlog import TransactionLog # type: ignore[import]
                txlog = TransactionLog(dg_dir)
                if txlog.log_path.exists() and txlog.needs_recovery():
                    print("Running crash recovery...", file=sys.stderr)
                    txlog.recover()

            # Corruption detection for doctor and other integrity-sensitive commands
            if args.command in ("doctor",):
                from deep.core.refs import resolve_head, list_branches, get_branch # type: ignore[import]
                from deep.storage.objects import read_object_safe # type: ignore[import]
                
                objects_dir = dg_dir / "objects"
                
                head_sha = resolve_head(dg_dir)
                if head_sha:
                    try:
                        read_object_safe(objects_dir, head_sha)
                    except (FileNotFoundError, ValueError) as e:
                        print(f"FATAL: Repository corrupted. HEAD points to invalid object {head_sha}. ({e})", file=sys.stderr)
                        raise DeepCLIException(1)
                        
                for branch in list_branches(dg_dir):
                    branch_sha = get_branch(dg_dir, branch)
                    if branch_sha:
                        try:
                            read_object_safe(objects_dir, branch_sha)
                        except (FileNotFoundError, ValueError) as e:
                            print(f"FATAL: Repository corrupted. Branch '{branch}' points to invalid object {branch_sha}. ({e})", file=sys.stderr)
                            raise DeepCLIException(1)
    except FileNotFoundError:
        pass 

    # Run plugin command if registered
    pm = getattr(parser, "plugin_manager", None)
    if pm and args.command in pm.commands:
        handler = pm.commands[args.command]
        plugin_args = getattr(args, "args", [])
        handler(plugin_args)
        return


    try:
        run(args)
    except DeepError as e:
        print(f"Deep: error: {e}", file=sys.stderr)
        raise DeepCLIException(1)
    except DeepCLIException:
        raise
    except Exception as e:
        # Don't silence unexpected exceptions in dev mode if requested,
        # but for CLI users, show a clean internal error.
        if os.environ.get("DEEP_DEBUG"):
            raise
        print(f"Deep: internal error: {e}", file=sys.stderr)
        raise DeepCLIException(1)
        
    # Phase 6: State Consistency Guarantee
    if args.command in ("merge", "rollback", "checkout"):
        from deep.core.status import compute_status # type: ignore[import]
        status = compute_status(repo_root)
        if status.staged_new or status.staged_modified or status.staged_deleted or status.modified or status.deleted:
            print("Deep: error: State consistency validation failed: HEAD, INDEX, and WORKING TREE do not match.", file=sys.stderr)
            raise DeepCLIException(1)
    
    # --- Background Auto-Maintenance Hook ---
    # Triggered after some commands if enough time has passed.
    # Commands that frequently modify the repo are good candidates.
    if args.command in ("commit", "push", "pull", "merge", "add"):
        try:
            from deep.core.repository import find_repo # type: ignore[import]
            from deep.core.maintenance import run_maintenance # type: ignore[import]
            repo_root = find_repo()
            # Run in a background thread or process could be better,
            # but for now we'll do it synchronously if needed.
            run_maintenance(repo_root, force=False)
        except Exception:
            pass # Never let maintenance failure crash a successful command


if __name__ == "__main__":
    main()

def legacy_main(argv: list[str] | None = None) -> None:
    print("This command has been renamed to 'deep' (Deep). Please use `deep`.", file=sys.stderr)
    raise DeepCLIException(1)

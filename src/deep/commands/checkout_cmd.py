import argparse
import sys
from pathlib import Path

from deep.core.repository import find_repo
from deep.utils.utils import DeepError
from deep.core.errors import DeepCLIException
from deep.storage.transaction import TransactionManager
from deep.core.constants import DEEP_DIR


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the 'checkout' command parser."""
    p_checkout = subparsers.add_parser(
        "checkout",
        help="Switch branches or restore files",
        description="Switch to a different branch or restore files from a specific commit to the working tree.",
        epilog="""
\033[1mEXAMPLES:\033[0m

  \033[1;34m⚓️ deep checkout main\033[0m
     Switch to the 'main' branch.

  \033[1;34m⚓️ deep checkout -b feature\033[0m
     Create a new 'feature' branch and switch to it immediately.

  \033[1;34m⚓️ deep checkout abc1234\033[0m
     Detach HEAD and switch to a specific commit.
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_checkout.add_argument("-f", "--force", action="store_true", help="Force branch switching even if there are uncommitted local changes")
    p_checkout.add_argument("-b", "--branch", action="store_true", help="Create a new branch")
    p_checkout.add_argument("target", help="The branch name or commit SHA to switch to")
    p_checkout.add_argument("paths", nargs="*", help="Optional paths to restore from the target")


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
        import sys
        # Identify if explicitly used '--' (argparse consumes it)
        try:
            co_idx = sys.argv.index("checkout")
            has_sep = "--" in sys.argv[co_idx:]
        except ValueError:
            has_sep = False

        # If paths are provided via argparse 'paths' or if target is not a revision,
        # we treat this as a file-restoration command.
        is_restore = bool(paths) or (has_sep)
        
        # If no paths but target looks like a path (and not a branch), treat as restore from index
        if not is_restore and target and target != "--":
            from deep.core.refs import resolve_revision
            if not resolve_revision(dg_dir, target):
                from deep.storage.index import read_index
                index = read_index(dg_dir)
                if target in index.entries:
                    is_restore = True

        if is_restore:
            tm.begin("checkout_paths")
            objects_dir = dg_dir / "objects"
            
            # Determine source and paths
            # If target is a real revision, use it. Otherwise use index.
            from deep.core.refs import resolve_revision
            target_sha = resolve_revision(dg_dir, target) if target and target != "--" else None
            
            if target == "--" or (has_sep and target_sha is None) or (not target_sha and not paths):
                # Restore from Index
                from deep.storage.index import read_index
                index = read_index(dg_dir)
                source_files = {path: entry.content_hash for path, entry in index.entries.items()}
                source_desc = "index"
                # The target itself might be a path if no -- was used, or after --
                actual_paths = list(paths)
                if target and target != "--" and target_sha is None:
                    actual_paths.insert(0, target)
            else:
                # Restore from Commit (target_sha)
                from deep.storage.objects import read_object, Commit
                commit = read_object(objects_dir, target_sha)
                if not isinstance(commit, Commit):
                    print(f"Deep: error: '{target}' is not a commit.", file=sys.stderr)
                    raise DeepCLIException(1)
                from deep.core.repository import _get_tree_files
                source_files = _get_tree_files(objects_dir, commit.tree_sha)
                source_desc = target_sha[:7]
                actual_paths = list(paths)

            if not actual_paths:
                print("Deep: error: nothing specified. Please provide paths or a branch name.", file=sys.stderr)
                raise DeepCLIException(2)

            # Perform restoration
            from deep.storage.objects import read_object
            for p in actual_paths:
                try:
                    # Robust path resolution relative to repo root
                    abs_p = Path(p).resolve()
                    rel_p = abs_p.relative_to(repo_root.resolve()).as_posix()
                except ValueError:
                    print(f"Deep: error: path '{p}' is outside repository.", file=sys.stderr)
                    continue

                if rel_p not in source_files:
                    print(f"Deep: error: path '{rel_p}' not found in {source_desc}.", file=sys.stderr)
                    continue
                    
                sha = source_files[rel_p]
                blob_obj = read_object(objects_dir, sha)
                dest_file = repo_root / rel_p
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                
                content = blob_obj.data if hasattr(blob_obj, "data") else blob_obj.serialize_content()
                dest_file.write_bytes(content)
                print(f"Updated 1 path from {source_desc}")
            
            tm.commit()
            return

        # 3. Branch/Commit switching
        if not target:
            print("Deep: error: branch name or commit SHA required.", file=sys.stderr)
            raise DeepCLIException(2)
            
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

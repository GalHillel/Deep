"""
deep.commands.push_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep push`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import resolve_head, get_branch
from deep.core.config import Config
from deep.network.client import get_remote_client
from deep.utils.ux import Color
from deep.core.hooks import run_hook


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``push`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)
    
    branch = args.branch
    local_sha = get_branch(repo_root / DEEP_DIR, branch)
    if not local_sha:
        print(f"Deep: error: Branch '{branch}' not found locally", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)
    auth_token = config.get("auth.token")
    client = get_remote_client(url, auth_token=auth_token)

    from deep.storage.txlog import TransactionLog
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog
    from deep.core.reconcile import logical_rebase
    from deep.core.refs import get_current_branch, update_branch, update_head
    from deep.storage.index import read_index, write_index, DeepIndex
    from deep.commands.rebase_cmd import _restore_tree_to_workdir
    from deep.storage.objects import read_object, Commit, Tree

    txlog = TransactionLog(dg_dir)
    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    tx_id = txlog.begin("push", f"{branch} -> {url}")
    temp_bridge_dir = None
    try:
        run_hook(dg_dir, "pre-push", args=[url, branch])
        with Timer(telemetry, "push"):
            client.connect()
            
            # 1. Fetch remote HEAD to check for divergence
            print(f"Checking remote {branch} state...")
            refs = client.ls_refs()
            remote_ref = f"refs/heads/{branch}"
            remote_sha = refs.get(remote_ref)
            
            if remote_sha and remote_sha != "0"*40:
                # Fetch remote objects first to allow LCA calculation and rebase
                print(f"Fetching remote commits...")
                client.fetch(dg_dir / "objects", remote_sha)
                
                # Check if we are already a fast-forward of remote
                from deep.core.merge import find_lca
                lca = find_lca(dg_dir / "objects", local_sha, remote_sha)
                
                if lca != remote_sha:
                    print(Color.wrap(Color.YELLOW, "Divergence detected. Automatically reconciling local branch via rebase..."))
                    
                    # Perform logical rebase with Windows sanitization
                    try:
                        new_local_sha, renamed_log = logical_rebase(repo_root, dg_dir / "objects", local_sha, remote_sha, sanitize_windows=True)
                        
                        if renamed_log:
                            print(Color.wrap(Color.CYAN, "\nWindows Path Sanitization Summary:"))
                            for old_n, new_n in renamed_log.items():
                                print(f"  - {old_n} -> {new_n}")
                            print()
                            
                        # Update local branch pointer
                        curr_branch = get_current_branch(dg_dir)
                        if curr_branch == branch:
                            update_branch(dg_dir, curr_branch, new_local_sha)
                            
                            # Restore working directory to match the rebased state
                            target_commit = read_object(dg_dir / "objects", new_local_sha)
                            assert isinstance(target_commit, Commit)
                            tree = read_object(dg_dir / "objects", target_commit.tree_sha)
                            assert isinstance(tree, Tree)
                            
                            # Clear current index/workdir state for restored files
                            old_index = read_index(dg_dir)
                            for rel_path in old_index.entries:
                                full = repo_root / rel_path
                                if full.exists() and full.is_file():
                                    try:
                                        full.unlink()
                                    except OSError:
                                        pass
                            
                            new_index = DeepIndex()
                            _restore_tree_to_workdir(repo_root, dg_dir / "objects", tree, new_index)
                            write_index(dg_dir, new_index)
                            
                        else:
                            # If we're pushing a branch we're NOT on, just update its ref
                            update_branch(dg_dir, branch, new_local_sha)
                        
                        local_sha = new_local_sha
                        print(f"Rebased and sanitized successfully!")
                    except RuntimeError as e:
                        print(f"Automatic reconciliation failed: {e}", file=sys.stderr)
                        print("Please resolve conflicts manually using 'deep pull'.", file=sys.stderr)
                        sys.exit(1)

            print(f"Pushing {branch} to {url}...")
            # If using DeepBridge, it may leave temp dirs. We should handle them if possible,
            # but DeepBridge.push uses tempfile.TemporaryDirectory already.
            # We add a generic cleanup for any .deep/tmp or similar if they existed.
            resp = client.push(dg_dir / "objects", f"refs/heads/{branch}", remote_sha or "0"*40, local_sha)
            print(resp)
            
        tx_id_commit = tx_id
        txlog.commit(tx_id_commit)
        audit.record("local", "push", ref=branch, sha=local_sha, client=url)
    except Exception as e:
        txlog.rollback(tx_id, str(e))
        print(f"Deep: error: push failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        # Cleanup any Deep temp dirs
        tmp_dirs = list(dg_dir.glob("temp_deep_*")) + list(repo_root.glob("temp_deep_*"))
        for d in tmp_dirs:
            if d.is_dir():
                import shutil
                shutil.rmtree(d, ignore_errors=True)

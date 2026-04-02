"""
deep.commands.push_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep push`` command implementation.

Native smart protocol push:
1. Discover remote refs
2. Compute missing objects via DAG walk
3. Build v2 packfile
4. Send via receive-pack protocol
5. Parse status response

No external VCS CLI dependency.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import resolve_head, get_branch
from deep.core.config import Config
from deep.utils.ux import Color, print_success
from deep.core.hooks import run_hook


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``push`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    config = Config(repo_root)
    from deep.core.refs import get_current_branch

    # Resolving Remote URL
    url_or_name = args.url or "origin"
    url = config.get(f"remote.{url_or_name}.url", url_or_name)

    # Resolving Branch (optional if --tags is provided)
    branch = args.branch or get_current_branch(dg_dir)
    
    from deep.storage.transaction import TransactionManager
    from deep.core.telemetry import TelemetryCollector, Timer
    from deep.core.audit import AuditLog
    from deep.core.refs import get_current_branch, update_branch, update_remote_ref, list_tags, get_tag

    telemetry = TelemetryCollector(dg_dir)
    audit = AuditLog(dg_dir)

    with TransactionManager(dg_dir) as tm:
        tm.begin("push")
        try:
            # 1. Prepare push operations
            push_ops = [] # list of (ref, local_sha)
            
            if branch:
                local_sha = get_branch(dg_dir, branch)
                if local_sha:
                    push_ops.append((f"refs/heads/{branch}", local_sha))
                elif not getattr(args, "tags", False):
                    print(f"Deep: error: Branch '{branch}' not found locally", file=sys.stderr)
                    raise DeepCLIException(1)
            
            if getattr(args, "tags", False):
                tags = list_tags(dg_dir)
                for t in tags:
                    t_sha = get_tag(dg_dir, t)
                    if t_sha:
                        push_ops.append((f"refs/tags/{t}", t_sha))

            if not push_ops:
                print("Deep: error: nothing to push (no branch determined and no tags found).", file=sys.stderr)
                raise DeepCLIException(1)

            # 2. Execute push operations
            run_hook(dg_dir, "pre-push", args=[url, branch or ""])
            with Timer(telemetry, "push"):
                # Use native smart protocol
                from deep.network.client import get_remote_client
                from deep.network.auth import get_auth_token

                auth_token = config.get("auth.token") or get_auth_token()
                client = get_remote_client(url, auth_token=auth_token)
                
                if hasattr(client, 'connect'):
                    client.connect()

                # Discover remote refs
                print(f"Checking remote state for {url}...")
                remote_refs = client.ls_remote()
                objects_dir = dg_dir / "objects"

                any_pushed = False
                for ref, local_sha in push_ops:
                    remote_sha = remote_refs.get(ref, "0" * 40)

                    # Update local tracking info even if up-to-date
                    if ref.startswith("refs/heads/"):
                        b_name = ref[len("refs/heads/"):]
                        if getattr(args, "set_upstream", False) and b_name == branch:
                            config.set_local(f"branch.{b_name}.remote", url_or_name)
                            config.set_local(f"branch.{b_name}.merge", f"refs/heads/{b_name}")
                            print(f"Branch '{b_name}' set up to track remote branch '{b_name}' from '{url_or_name}'.")

                    if remote_sha == local_sha:
                        # Still update remote ref mapping for local tracking
                        if ref.startswith("refs/heads/"):
                            b_name = ref[len("refs/heads/"):]
                            update_remote_ref(dg_dir, url_or_name, b_name, local_sha)
                        continue
                    
                    any_pushed = True

                    # Fast-forward check for branches
                    if ref.startswith("refs/heads/") and remote_sha != "0" * 40:
                        from deep.core.refs import is_ancestor
                        # Ensure remote objects exist for FF check
                        from deep.objects.hash_object import object_exists
                        if not object_exists(objects_dir, remote_sha):
                            try:
                                client.fetch(objects_dir, want_shas=[remote_sha], have_shas=[local_sha])
                            except Exception: pass

                        if not is_ancestor(objects_dir, remote_sha, local_sha):
                            if not getattr(args, 'force', False):
                                print(Color.wrap(Color.YELLOW,
                                      f"hint: Updates were rejected for '{ref}' because the remote contains work\n"
                                      "hint: that you do not have locally."), file=sys.stderr)
                                raise DeepCLIException(1)

                    print(f"Pushing {ref} to {url}...")
                    resp = client.push(objects_dir, ref, remote_sha, local_sha)
                    
                    if ref.startswith("refs/heads/"):
                        b_name = ref[len("refs/heads/"):]
                        update_remote_ref(dg_dir, url_or_name, b_name, local_sha)
                        if url_or_name != "origin":
                            update_remote_ref(dg_dir, "origin", b_name, local_sha)

                if not any_pushed:
                    print("Everything up-to-date.")

            tm.commit()
            if branch:
                audit.record("local", "push", ref=branch, sha=get_branch(dg_dir, branch), client=url)
            
            print_success("push successful")

        except Exception as e:
            if not isinstance(e, DeepCLIException):
                print(f"Deep: error: push failed: {e}", file=sys.stderr)
            raise e

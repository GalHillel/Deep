"""
deep.commands.fetch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep fetch`` command implementation.

Native Git protocol fetch:
1. Discover remote refs
2. Compare with local refs
3. Request missing objects via upload-pack
4. Update remote tracking branches

No git CLI dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import update_branch, update_head, update_remote_ref, get_remote_ref
from deep.core.config import Config


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``fetch`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        sys.exit(1)

    url_or_name = args.url
    config = Config(repo_root)
    url = config.get(f"remote.{url_or_name}.url", url_or_name)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    try:
        from deep.network.client import get_remote_client
        from deep.network.auth import get_auth_token

        auth_token = config.get("auth.token") or get_auth_token()
        client = get_remote_client(url, auth_token=auth_token)

        # Discover remote refs
        print(f"Deep: fetching from {url}...")
        remote_refs = client.ls_remote()

        if not remote_refs:
            print("Already up to date (empty remote).")
            return

        # Determine which SHAs we already have
        have_shas = []
        for ref_name, sha in remote_refs.items():
            if ref_name.startswith("refs/heads/"):
                branch = ref_name[len("refs/heads/"):]
                local_sha = get_remote_ref(dg_dir, url_or_name, branch)
                if local_sha:
                    have_shas.append(local_sha)

        # Also check if specific sha was requested
        sha = getattr(args, "sha", None)
        if sha:
            # Fetch a specific SHA
            from deep.objects.hash_object import object_exists
            if object_exists(objects_dir, sha):
                print("Already up to date.")
                return

            count = client.fetch(objects_dir, want_shas=[sha], have_shas=have_shas)
            print(f"Deep: fetched {count} objects.")
            return

        # Fetch all remote refs
        want_shas = list(set(remote_refs.values()) - set(have_shas))
        if not want_shas:
            print("Already up to date.")
            return

        count = client.fetch(objects_dir, want_shas=want_shas, have_shas=have_shas)
        print(f"Deep: fetched {count} objects.")

        # Update remote tracking branches
        for ref_name, sha in remote_refs.items():
            if ref_name.startswith("refs/heads/"):
                branch = ref_name[len("refs/heads/"):]
                update_remote_ref(dg_dir, url_or_name, branch, sha)
                # Also update for "origin" alias
                if url_or_name != "origin":
                    update_remote_ref(dg_dir, "origin", branch, sha)

    except Exception as e:
        print(f"Deep: error: fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

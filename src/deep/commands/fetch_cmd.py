"""
deep.commands.fetch_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep fetch`` command implementation.

Native smart protocol fetch:
1. Discover remote refs
2. Compare with local refs
3. Request missing objects via upload-pack
4. Update remote tracking branches

No external VCS CLI dependency.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.refs import update_branch, update_head, update_remote_ref, get_remote_ref
from deep.core.config import Config


def run(args) -> None:
    """Execute the ``fetch`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    config = Config(repo_root)

    if getattr(args, "all", False):
        remotes = []
        for section in config.parser.sections():
            if section.startswith("remote."):
                remotes.append(section[7:])
        
        if not remotes:
            print("No remotes configured.")
            return

        success = True
        for r in sorted(remotes):
            try:
                _fetch_remote(dg_dir, config, r, args.sha)
            except Exception as e:
                print(f"Deep: error: fetch from '{r}' failed: {e}", file=sys.stderr)
                success = False
        
        if not success:
            raise DeepCLIException(1)
    else:
        url_or_name = args.url or "origin"
        _fetch_remote(dg_dir, config, url_or_name, args.sha)

def _fetch_remote(dg_dir: Path, config: Config, url_or_name: str, requested_sha: str | None = None) -> None:
    """Internal helper to fetch from a single remote."""
    url = config.get(f"remote.{url_or_name}.url", url_or_name)
    objects_dir = dg_dir / "objects"

    from deep.storage.transaction import TransactionManager
    from deep.network.client import get_remote_client
    from deep.network.auth import get_auth_token
    from deep.objects.hash_object import object_exists
    from deep.core.refs import get_remote_ref

    with TransactionManager(dg_dir) as tm:
        tm.begin(f"fetch:{url_or_name}")
        try:
            auth_token = config.get("auth.token") or get_auth_token()
            client = get_remote_client(url, auth_token=auth_token)

            # Discover remote refs
            print(f"Deep: fetching from {url_or_name} ({url})...")
            remote_refs = client.ls_remote()

            if not remote_refs:
                print(f"Already up to date (empty remote '{url_or_name}').")
                tm.commit()
                return

            # Determine what we have locally
            have_shas = []
            for ref_name, sha in remote_refs.items():
                if ref_name.startswith("refs/heads/"):
                    branch = ref_name[len("refs/heads/"):]
                    local_sha = get_remote_ref(dg_dir, url_or_name, branch)
                    if local_sha and object_exists(objects_dir, local_sha):
                        have_shas.append(local_sha)

            # Fetch specific SHA or all missing refs
            if requested_sha:
                if object_exists(objects_dir, requested_sha):
                    print(f"Object {requested_sha[:7]} already exists.")
                else:
                    count = client.fetch(objects_dir, want_shas=[requested_sha], have_shas=have_shas)
                    print(f"Deep: fetched {count} objects.")
            else:
                remote_shas = set(remote_refs.values())
                want_shas = [sha for sha in remote_shas if sha != "0" * 40 and not object_exists(objects_dir, sha)]
                
                if not want_shas:
                    print(f"Remote '{url_or_name}' up to date.")
                else:
                    count = client.fetch(objects_dir, want_shas=want_shas, have_shas=have_shas)
                    print(f"Deep: fetched {count} objects.")

            # Update remote tracking branches
            for ref_name, sha in remote_refs.items():
                if ref_name.startswith("refs/heads/"):
                    branch = ref_name[len("refs/heads/"):]
                    update_remote_ref(dg_dir, url_or_name, branch, sha)
                    # Also update for "origin" alias if this is the primary remote
                    if url_or_name != "origin" and config.get("remote.origin.url") == url:
                        update_remote_ref(dg_dir, "origin", branch, sha)
            
            tm.commit()

        except Exception as e:
            # Re-raise to let the caller handle reporting/aborting
            raise e

"""
deep.commands.mirror_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep mirror`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.mirror import MirrorManager
from deep.core.config import Config
from deep.utils.ux import Color

def run(args) -> None:
    """Execute the ``mirror`` command."""
    url = args.url
    path = Path(args.path).resolve()

    if path.exists() and any(path.iterdir()):
        print(f"Deep: error: destination path '{path}' already exists and is not empty.", file=sys.stderr)
        raise DeepCLIException(1)

    # 1. Initialize new deep repo
    path.mkdir(parents=True, exist_ok=True)
    dg_dir = path / DEEP_DIR
    
    from deep.commands.init_cmd import run as init_run
    from argparse import Namespace
    init_run(Namespace(path=str(path)))

    print(Color.wrap(Color.CYAN, f"⚓ Mirroring {url} into {path}..."))

    # 2. Add remote origin
    from deep.core.config import Config
    config = Config(path)
    config.set_local("remote.origin.url", url)
    # Configure for mirroring: Fetch all refs
    config.set_local("remote.origin.fetch", "+refs/*:refs/*")
    config.set_local("core.mirror", "true")

    # 3. Synchronize all refs
    from deep.network.client import get_remote_client
    from deep.core.refs import update_branch, create_tag
    from deep.storage.transaction import TransactionManager
    
    client = get_remote_client(url)
    try:
        if hasattr(client, "connect"):
            client.connect()
        refs = client.ls_remote()
        if not refs:
            print(Color.wrap(Color.DIM, "Source repository is empty."))
            return

        with TransactionManager(dg_dir) as tm:
            tm.begin("mirror-create")
            for ref, sha in refs.items():
                print(f"  Fetching {ref} [{sha[:7]}]...")
                # Note: fetch expects a list of SHAs
                client.fetch(dg_dir / "objects", [sha])
                
                # Update local refs
                if ref.startswith("refs/heads/"):
                    branch = ref[len("refs/heads/"):]
                    update_branch(dg_dir, branch, sha)
                elif ref.startswith("refs/tags/"):
                    tag = ref[len("refs/tags/"):]
                    try:
                        create_tag(dg_dir, tag, sha)
                    except FileExistsError:
                        # In mirror mode, we can overwrite or just ignore if already exists
                        pass
                elif ref == "HEAD":
                    (dg_dir / "HEAD").write_text(sha)
            tm.commit()

        print(Color.wrap(Color.GREEN, "\nMirror complete."))

    except Exception as e:
        print(f"Deep: error: mirror failed: {e}", file=sys.stderr)
        raise DeepCLIException(1)
    finally:
        if hasattr(client, "disconnect"):
            client.disconnect()

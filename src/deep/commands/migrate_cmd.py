"""
deep.commands.migrate_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~
Upgrades a Deep repository from legacy (v1) to native (v2) storage format.
This involves repacking objects into DeepVault and regenerating the DHGX.
"""

from __future__ import annotations
from pathlib import Path
from typing import List
import shutil

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.config import get_config, set_config
from deep.storage.objects import walk_loose_shas, read_object, Blob, Tree, Commit, Tag, Chunk, ChunkedBlob
from deep.storage.vault import DeepVaultWriter
from deep.storage.commit_graph import build_history_graph
from deep.storage.index import read_index, write_index, DeepIndex, DeepIndexEntry
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'migrate' command parser."""
    p_migrate = subparsers.add_parser(
        "migrate",
        help="Upgrade a Deep repository to the latest format",
        description="""Upgrade your Deep repository to the latest storage and metadata formats.

Migration ensures compatibility with the newest features, including DeepVault object packing and accelerated history graphs.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep migrate\033[0m
     Upgrade the current repository to the latest native format
  \033[1;34m⚓️ deep migrate --path /path/to/repo\033[0m
     Migrate a specific repository path
  \033[1;34m⚓️ deep migrate --dry-run\033[0m
     Identify required migration steps without applying changes
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )


def run(args: Any) -> None:
    """Execute the ``migrate`` command."""
    migrate_cmd(getattr(args, "path", None))


def migrate_cmd(path: str | None = None) -> None:
    try:
        repo_root = find_repo(path)
    except FileNotFoundError:
        print("Error: Not a Deep repository.")
        return

    dg_dir = repo_root / DEEP_DIR
    config = get_config(dg_dir)
    current_version = config.get("format_version", 1)

    if current_version >= 2:
        print(f"Repository is already at version {current_version}. No migration needed.")
        return

    print(f"Migrating repository at {repo_root} from v{current_version} to v2...")

    # 1. Repack Loose Objects into DeepVault
    print("Repacking objects into DeepVault...")
    vault_writer = DeepVaultWriter(dg_dir)
    objects_dir = dg_dir / "objects"
    
    objects_to_pack = []
    shas = list(walk_loose_shas(objects_dir))
    
    for i, sha in enumerate(shas):
        try:
            obj = read_object(objects_dir, sha)
            # (sha, type, raw_content)
            # Note: serialize_content returns raw data without header.
            # DVPF stores [type][compressed_data], so we need the type and the serialized content.
            objects_to_pack.append((sha, obj.OBJ_TYPE, obj.serialize_content()))
        except Exception as e:
            print(f"Warning: Skipping corrupt or missing object {sha}: {e}")

        if len(objects_to_pack) >= 1000 or i == len(shas) - 1:
            if objects_to_pack:
                vault_writer.create_vault(objects_to_pack)
                objects_to_pack = []

    # 2. Build DeepHistoryGraph
    print("Building DeepHistoryGraph...")
    build_history_graph(dg_dir)

    # 3. Migrate Index
    print("Migrating Index to DeepIndex v1...")
    # read_index in the new code handles legacy migration automatically
    new_index = read_index(dg_dir)
    write_index(dg_dir, new_index)

    # 4. Update Config
    config["format_version"] = 2
    set_config(dg_dir, config)

    # 5. Cleanup (Optional: Move old objects to a backup or delete)
    # For safety, we'll keep them but they are now shadowed by the Vault.
    # In a real production system, we might delete them after verification.
    
    print("Migration complete. Repository is now in Deep Native format (v2).")

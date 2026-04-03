"""
deep.commands.migrate_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~
Upgrades a Deep repository from legacy (v1) to native (v2) storage format.
This involves repacking objects into DeepVault and regenerating the DHGX.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Any
import shutil

from deep.core.repository import find_repo, DEEP_DIR
from deep.core.config import get_config, set_config
from deep.storage.objects import walk_loose_shas, read_object
from deep.storage.vault import DeepVaultWriter
from deep.storage.commit_graph import build_history_graph
from deep.storage.index import read_index, write_index
from deep.utils.ux import Color


def run(args: Any) -> None:
    """Execute the ``migrate`` command."""
    try:
        # Extract path if provided by parser (though migrate currently defaults to CWD)
        path = getattr(args, "path", None)
        repo_root = find_repo(path)
    except FileNotFoundError:
        print(f"{Color.wrap(Color.RED, 'Error:')} Not a Deep repository.")
        return

    dg_dir = repo_root / DEEP_DIR
    config = get_config(dg_dir)
    current_version = config.get("format_version", 1)

    if int(current_version) >= 2:
        print(f"⚓️ Repository is already at version {current_version}. No migration needed.")
        return

    print(f"⚓️ {Color.wrap(Color.CYAN, f'Migrating repository at {repo_root} from v{current_version} to v2...')}")

    # 1. Repack Loose Objects into DeepVault
    print(f"⚓️ {Color.wrap(Color.YELLOW, 'Repacking objects into DeepVault...')}")
    vault_writer = DeepVaultWriter(dg_dir)
    objects_dir = dg_dir / "objects"
    
    objects_to_pack = []
    shas = list(walk_loose_shas(objects_dir))
    
    processed_count = 0
    for i, sha in enumerate(shas):
        try:
            obj = read_object(objects_dir, sha)
            # (sha, type, raw_content)
            # DVPF stores [type][compressed_data]
            objects_to_pack.append((sha, obj.OBJ_TYPE, obj.serialize_content()))
            processed_count += 1
        except Exception as e:
            print(f"⚓️ {Color.wrap(Color.RED, 'Warning:')} Skipping corrupt or missing object {sha}: {e}")

        # Batch write in 1000-object segments
        if len(objects_to_pack) >= 1000 or i == len(shas) - 1:
            if objects_to_pack:
                vault_writer.create_vault(objects_to_pack)
                objects_to_pack = []

    # 2. Build DeepHistoryGraph
    print(f"⚓️ {Color.wrap(Color.YELLOW, 'Building DeepHistoryGraph...')}")
    build_history_graph(dg_dir)

    # 3. Migrate Index
    print(f"⚓️ {Color.wrap(Color.YELLOW, 'Migrating Index to DeepIndex v2...')}")
    # read_index handles legacy migration automatically
    new_index = read_index(dg_dir)
    write_index(dg_dir, new_index)

    # 4. Update Config
    config["format_version"] = 2
    set_config(dg_dir, config)
    
    print()
    print(f"⚓️ {Color.wrap(Color.BOLD, 'Migration Summary:')}")
    print(f"  - Objects Repacked: {processed_count}")
    print(f"  - DHGX Generated:   SUCCESS")
    print(f"  - Index Version:    v2")
    print()
    print(f"⚓️ {Color.wrap(Color.SUCCESS, 'Migration complete. Repository is now in Deep Native format (v2).')}")

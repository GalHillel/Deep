"""
deep.core.mirror
~~~~~~~~~~~~~~~~~~~~
Repository mirroring system for Deep.
Allows keeping full repository copies in sync across multiple nodes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Optional

from deep.network.client import get_remote_client
from deep.core.refs import list_branches, get_branch, update_branch
from deep.core.constants import DEEP_DIR

class MirrorManager:
    """Manages repository mirrors and synchronization."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.mirror_path = dg_dir / "mirrors.json"
        self._mirrors: List[str] = [] # List of URLs
        self._load()

    def _load(self):
        if not self.mirror_path.exists():
            return
        try:
            self._mirrors = json.loads(self.mirror_path.read_text())
        except Exception:
            pass

    def _save(self):
        with open(self.mirror_path, "w") as f:
            json.dump(self._mirrors, f, indent=2)

    def add_mirror(self, url: str):
        if url not in self._mirrors:
            self._mirrors.append(url)
            self._save()

    def list_mirrors(self) -> List[str]:
        return self._mirrors

    def sync_mirror(self, url: str, auth_token: Optional[str] = None) -> Dict[str, str]:
        """Synchronize with a remote mirror (bidirectional)."""
        results = {}
        client = get_remote_client(url, auth_token=auth_token)
        try:
            client.connect()
            
            # 1. Fetch from remote (Pull Mirror)
            remote_refs = client.ls_refs()
            for ref, sha in remote_refs.items():
                if ref.startswith("refs/heads/"):
                    branch = ref[len("refs/heads/"):]
                    # Simple rule: if we don't have it or it's different, fetch it
                    local_sha = get_branch(self.dg_dir, branch)
                    if local_sha != sha:
                        client.fetch(self.dg_dir / "objects", sha)
                        update_branch(self.dg_dir, branch, sha)
                        results[f"pull_{branch}"] = "updated"
            
            # 2. Push to remote (Push Mirror)
            local_branches = list_branches(self.dg_dir)
            for branch in local_branches:
                local_sha = get_branch(self.dg_dir, branch)
                remote_sha = remote_refs.get(f"refs/heads/{branch}")
                if local_sha != remote_sha:
                    # Push branch
                    try:
                        client.push(self.dg_dir / "objects", f"refs/heads/{branch}", remote_sha or "0"*40, local_sha)
                        results[f"push_{branch}"] = "updated"
                    except Exception as e:
                        results[f"push_{branch}"] = f"failed: {e}"
                    
            return results
        finally:
            client.disconnect()

    def sync_all(self, auth_token: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        all_results = {}
        for url in self._mirrors:
            try:
                all_results[url] = self.sync_mirror(url, auth_token=auth_token)
            except Exception as e:
                all_results[url] = {"error": str(e)}
        return all_results

import json
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

class CacheManager:
    """Manages the .deep/cache directory for read-optimized data."""
    
    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.cache_dir = dg_dir / "cache"
        self.diff_cache_dir = self.cache_dir / "diffs"
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.diff_cache_dir.mkdir(parents=True, exist_ok=True)
        # Prevent cache from being tracked if .deep was somehow partially tracked
        gitignore = self.cache_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")

    def get_commit_graph(self) -> Optional[List[Dict[str, Any]]]:
        """Load the cached commit DAG."""
        path = self.cache_dir / "commit_graph.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def update_commit_graph(self, graph_data: List[Dict[str, Any]]):
        """Save the commit DAG to cache."""
        path = self.cache_dir / "commit_graph.json"
        path.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")

    def get_diff(self, sha1: str, sha2: str) -> Optional[str]:
        """Retrieve a cached diff between two commits."""
        name = f"{sha1}_{sha2}.diff"
        path = self.diff_cache_dir / name
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def set_diff(self, sha1: str, sha2: str, diff_text: str):
        """Cache a diff between two commits."""
        name = f"{sha1}_{sha2}.diff"
        path = self.diff_cache_dir / name
        path.write_text(diff_text, encoding="utf-8")

    def invalidate_diffs(self):
        """Clear all cached diffs."""
        if self.diff_cache_dir.exists():
            shutil.rmtree(self.diff_cache_dir)
            self.diff_cache_dir.mkdir(parents=True, exist_ok=True)

    def invalidate_all(self):
        """Wipe the entire cache."""
        if self.cache_dir.exists():
            for item in self.cache_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                elif item.name != ".gitignore":
                    item.unlink()
        self._ensure_dirs()

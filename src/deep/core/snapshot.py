import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from deep.core.refs import resolve_head
from deep.storage.objects import Commit, read_object

class RepositorySnapshot:
    """A point-in-time, read-optimized view of the repository.
    
    Used by the Web Dashboard to provide a consistent view without
    locking the main transaction manager for long periods.
    """
    
    def __init__(self, dg_dir: Path, target_sha: Optional[str] = None):
        # Allow dg_dir to be either the repo root or the .deep directory
        if (dg_dir / ".deep").exists():
            self.dg_dir = dg_dir / ".deep"
        else:
            self.dg_dir = dg_dir
            
        self.objects_dir = self.dg_dir / "objects"
        # If no SHA provided, snapshot the current HEAD
        self.snapshot_sha = target_sha or resolve_head(self.dg_dir)
        self._commit_cache: Dict[str, Commit] = {}
        self._lock = threading.Lock()

    def get_commit(self, sha: str) -> Optional[Commit]:
        """Thread-safe cached commit retrieval."""
        with self._lock:
            if sha in self._commit_cache:
                return self._commit_cache[sha]
            
            try:
                obj = read_object(self.objects_dir, sha)
                if isinstance(obj, Commit):
                    self._commit_cache[sha] = obj
                    return obj
            except Exception:
                pass
            return None

    def walk_history(self, limit: int = 100) -> List[Commit]:
        """Fast traversal of the snapshot's history."""
        history = []
        current_sha = self.snapshot_sha
        seen = set()
        
        queue = [current_sha] if current_sha else []
        while queue and len(history) < limit:
            sha = queue.pop(0)
            if sha in seen: continue
            seen.add(sha)
            
            commit = self.get_commit(sha)
            if commit:
                history.append(commit)
                for p in commit.parent_shas:
                    if p not in seen:
                        queue.append(p)
        
        # Sort by timestamp descending
        history.sort(key=lambda c: c.timestamp, reverse=True)
        return history[:limit]

    def get_status_summary(self) -> Dict[str, Any]:
        """Return a high-level summary for the dashboard."""
        commit = self.get_commit(self.snapshot_sha) if self.snapshot_sha else None
        return {
            "snapshot_sha": self.snapshot_sha,
            "head_message": commit.message.split("\n")[0] if commit else "Initial",
            "head_author": commit.author if commit else "N/A",
            "head_time": commit.timestamp if commit else 0,
            "is_dirty": False # Snapshots are by definition clean (committed state)
        }

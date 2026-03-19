"""
deep.core.pr
~~~~~~~~~~~~~~~~
Core logic for Pull Requests in Deep platform.
PRs are stored as JSON files in .deep/prs/<id>.json
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional

def asdict_deep(obj):
    if isinstance(obj, list):
        return [asdict_deep(i) for i in obj]
    if hasattr(obj, "__dict__"):
        return {k: asdict_deep(v) for k, v in obj.__dict__.items()}
    return obj

@dataclass
class PRComment:
    author: str
    text: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class PullRequest:
    id: int
    title: str
    author: str
    source_branch: str
    target_branch: str
    status: str = "open" # open, merged, closed
    description: str = ""
    comments: List[PRComment] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    github_id: Optional[int] = None

class PRManager:
    """Manages Pull Requests for a repository."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.prs_dir = dg_dir / "prs"
        self.prs_dir.mkdir(parents=True, exist_ok=True)

    def _get_next_id(self) -> int:
        existing = list(self.prs_dir.glob("*.json"))
        if not existing:
            return 1
        ids = [int(p.stem) for p in existing]
        return max(ids) + 1

    def create_pr(self, title: str, author: str, source: str, target: str, description: str = "") -> PullRequest:
        pr_id = self._get_next_id()
        pr = PullRequest(id=pr_id, title=title, author=author, source_branch=source, target_branch=target, description=description)
        self.save_pr(pr)
        return pr

    def save_pr(self, pr: PullRequest):
        path = self.prs_dir / f"{pr.id}.json"
        with open(path, "w") as f:
            json.dump(asdict_deep(pr), f, indent=2)

    def get_pr(self, pr_id: int) -> Optional[PullRequest]:
        path = self.prs_dir / f"{pr_id}.json"
        if not path.exists():
            return None
        with open(path, "r") as f:
            data = json.load(f)
            # Reconstruct PR
            comments = [PRComment(**c) for c in data.get("comments", [])]
            data["comments"] = comments
            return PullRequest(**data)

    def list_prs(self) -> List[PullRequest]:
        prs = []
        for p in self.prs_dir.glob("*.json"):
            try:
                prs.append(self.get_pr(int(p.stem)))
            except Exception:
                continue
        return sorted(prs, key=lambda x: x.id)

    def merge_pr(self, pr_id: int):
        pr = self.get_pr(pr_id)
        if not pr:
            raise ValueError(f"PR #{pr_id} not found.")
        if pr.status != "open":
            raise ValueError(f"PR #{pr_id} is already {pr.status}.")
        
        # In a real system, this would perform a 'deep merge'
        # For our platform simulation, we mark as merged.
        pr.status = "merged"
        pr.updated_at = time.time()
        self.save_pr(pr)
        return pr

    def close_pr(self, pr_id: int) -> PullRequest:
        pr = self.get_pr(pr_id)
        if not pr:
            raise ValueError(f"PR #{pr_id} not found.")
        pr.status = "closed"
        pr.updated_at = time.time()
        self.save_pr(pr)
        return pr

    def reopen_pr(self, pr_id: int) -> PullRequest:
        pr = self.get_pr(pr_id)
        if not pr:
            raise ValueError(f"PR #{pr_id} not found.")
        pr.status = "open"
        pr.updated_at = time.time()
        self.save_pr(pr)
        return pr

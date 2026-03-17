"""
deep.core.issue
~~~~~~~~~~~~~~~~~~~
Core logic for Issues in Deep platform.
Issues are stored as JSON files in .deep/issues/<id>.json
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class IssueComment:
    author: str
    text: str
    timestamp: float = field(default_factory=time.time)

@dataclass
class Issue:
    id: int
    title: str
    author: str
    status: str = "open" # open, closed
    assignee: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    description: str = ""
    comments: List[IssueComment] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

class IssueManager:
    """Manages Issues for a repository."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.issues_dir = dg_dir / "issues"
        self.issues_dir.mkdir(parents=True, exist_ok=True)

    def _get_next_id(self) -> int:
        existing = list(self.issues_dir.glob("*.json"))
        if not existing:
            return 1
        ids = [int(p.stem) for p in existing]
        return max(ids) + 1

    def create_issue(self, title: str, author: str, description: str = "", assignee: Optional[str] = None, labels: List[str] = None) -> Issue:
        issue_id = self._get_next_id()
        issue = Issue(id=issue_id, title=title, author=author, description=description, assignee=assignee, labels=labels or [])
        self.save_issue(issue)
        return issue

    def save_issue(self, issue: Issue):
        path = self.issues_dir / f"{issue.id}.json"
        with open(path, "w") as f:
            json.dump(asdict_deep(issue), f, indent=2)

    def get_issue(self, issue_id: int) -> Optional[Issue]:
        path = self.issues_dir / f"{issue_id}.json"
        if not path.exists():
            return None
        with open(path, "r") as f:
            data = json.load(f)
            # Reconstruct Issue
            comments = [IssueComment(**c) for c in data.get("comments", [])]
            data["comments"] = comments
            return Issue(**data)

    def list_issues(self) -> List[Issue]:
        issues = []
        for p in self.issues_dir.glob("*.json"):
            try:
                issues.append(self.get_issue(int(p.stem)))
            except Exception:
                continue
        return sorted(issues, key=lambda x: x.id)

    def close_issue(self, issue_id: int):
        issue = self.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue #{issue_id} not found.")
        issue.status = "closed"
        self.save_issue(issue)
        return issue

def asdict_deep(obj):
    if isinstance(obj, list):
        return [asdict_deep(i) for i in obj]
    if hasattr(obj, "__dict__"):
        return {k: asdict_deep(v) for k, v in obj.__dict__.items()}
    return obj

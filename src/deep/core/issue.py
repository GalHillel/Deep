"""
deep.core.issue
~~~~~~~~~~~~~~~~~~~
Core logic for Issues in Deep platform.
Issues are stored as JSON files in .deep/issues/<id>.json
"""

from __future__ import annotations

import json
import time
import datetime
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class Issue:
    id: int
    title: str
    description: str
    type: str  # bug, feature, task
    author: str
    status: str = "open"  # open, closed, in-progress
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    assignee: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    linked_prs: List[int] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)

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
        ids = []
        for p in existing:
            try:
                ids.append(int(p.stem))
            except ValueError:
                continue
        return max(ids) + 1 if ids else 1

    def create_issue(self, title: str, description: str, type: str, author: str, assignee: Optional[str] = None, labels: List[str] = None) -> Issue:
        issue_id = self._get_next_id()
        issue = Issue(
            id=issue_id,
            title=title,
            description=description,
            type=type,
            author=author,
            status="open",
            assignee=assignee,
            labels=labels or []
        )
        self.save_issue(issue)
        return issue

    def save_issue(self, issue: Issue):
        path = self.issues_dir / f"{issue.id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(issue), f, indent=2, ensure_ascii=False)

    def get_issue(self, issue_id: int) -> Optional[Issue]:
        path = self.issues_dir / f"{issue_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Issue(**data)

    def list_issues(self) -> List[Issue]:
        issues = []
        for p in self.issues_dir.glob("*.json"):
            try:
                issue = self.get_issue(int(p.stem))
                if issue:
                    issues.append(issue)
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
    
    def reopen_issue(self, issue_id: int):
        issue = self.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue #{issue_id} not found.")
        issue.status = "open"
        self.save_issue(issue)
        return issue

    def add_timeline_event(self, issue_id: int, event: str, **kwargs):
        """Add an event to the issue timeline."""
        issue = self.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue #{issue_id} not found.")
        
        entry = {
            "event": event,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        entry.update(kwargs)
        issue.timeline.append(entry)
        self.save_issue(issue)
        return issue

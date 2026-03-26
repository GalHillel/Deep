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
    priority: str = "Medium"  # Low, Medium, High
    status: str = "open"  # open, closed, in-progress
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    assignee: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    linked_prs: List[int] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)

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

    def create_issue(self, title: str, description: str, type: str, author: str, priority: str = "Medium", assignee: Optional[str] = None, labels: List[str] = None) -> Issue:
        issue_id = self._get_next_id()
        issue = Issue(
            id=issue_id,
            title=title,
            description=description,
            type=type,
            author=author,
            priority=priority,
            status="open",
            assignee=assignee,
            labels=labels or []
        )
        self.save_issue(issue)
        return issue

    def save_issue(self, issue: Issue):
        path = self.issues_dir / f"{issue.id}.json"
        from deep.utils.utils import AtomicWriter
        with AtomicWriter(path, mode="w") as aw:
            json.dump(asdict(issue), aw, indent=2, ensure_ascii=False)

    def get_issue(self, issue_id: int) -> Optional[Issue]:
        path = self.issues_dir / f"{issue_id}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Backward compatibility: migrate timeline to events
            if "timeline" in data and "events" not in data:
                data["events"] = data.pop("timeline")
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

    def link_pr(self, issue_id: int, pr_id: int):
        """Link a PR to the issue and record the event."""
        issue = self.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue #{issue_id} not found.")
        
        if pr_id not in issue.linked_prs:
            issue.linked_prs.append(pr_id)
            if issue.status == "open":
                issue.status = "in-progress"
            # Add event directly to this instance to avoid race conditions with nested saves
            self.add_event(issue_id, "system", "PR_LINKED", f"Linked to PR #{pr_id}", already_loaded_issue=issue)
            # The add_event call above now handles the save_issue call.

    def add_event(self, issue_id: int, actor: str, action: str, description: str, already_loaded_issue: Optional[Issue] = None, **kwargs):
        """Add an event to the issue timeline (event sourcing)."""
        if already_loaded_issue:
            issue = already_loaded_issue
        else:
            issue = self.get_issue(issue_id)
            if not issue:
                raise ValueError(f"Issue #{issue_id} not found.")
        
        entry = {
            "actor": actor,
            "action": action,
            "description": description,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        entry.update(kwargs)
        issue.events.append(entry)
        self.save_issue(issue)
        return issue

    # Backward compatibility for tests and older integrations
    def add_timeline_event(self, issue_id: int, event_type: str, **kwargs):
        desc = kwargs.pop("reason", "")
        if not desc and "sha" in kwargs:
            desc = f"Commit linked: {kwargs['sha'][:7]}"
        if not desc and "pr" in kwargs:
            desc = f"PR linked: {kwargs['pr']}"
        if not desc:
            desc = f"System event: {event_type}"
        return self.add_event(issue_id, actor="system", action=event_type, description=desc, **kwargs)

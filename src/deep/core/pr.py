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
class PRReply:
    author: str
    text: str
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

@dataclass
class PRThread:
    id: int
    author: str
    text: str
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    resolved: bool = False
    replies: List[PRReply] = field(default_factory=list)

@dataclass
class PullRequest:
    id: int
    title: str
    head: str  # Source branch
    base: str  # Target branch
    status: str = "open" # open, merged, closed
    body: str = ""
    author: str = "unknown"
    github_id: Optional[int] = None
    github_url: Optional[str] = None
    threads: List[PRThread] = field(default_factory=list)
    reviews: Dict[str, Dict[str, Any]] = field(default_factory=dict) # author -> {status, comment, timestamp}
    requested_reviewers: List[str] = field(default_factory=list)
    approvals_required: int = 1
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    linked_issue: Optional[int] = None
    commits: List[str] = field(default_factory=list)
    merged_at: Optional[str] = None

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

    def create_pr(self, title: str, author: str, head: str, base: str, body: str = "", 
                  linked_issue: Optional[int] = None, commits: List[str] = None,
                  requested_reviewers: List[str] = None) -> PullRequest:
        prs = self.list_prs()
        next_id = max([p.id for p in prs], default=0) + 1
        
        pr = PullRequest(
            id=next_id,
            title=title,
            author=author,
            head=head,
            base=base,
            body=body,
            status="open",
            linked_issue=linked_issue,
            commits=commits or [],
            requested_reviewers=requested_reviewers or []
        )
        self.save_issue_link(pr)
        self.save_pr(pr)
        return pr

    def save_issue_link(self, pr: PullRequest):
        """Link PR to issue if linked_issue is set."""
        if pr.linked_issue:
            import deep.core.issue as issue_core
            issue_manager = issue_core.IssueManager(self.dg_dir)
            issue = issue_manager.get_issue(pr.linked_issue)
            if issue:
                if pr.id not in issue.linked_prs:
                    issue.linked_prs.append(pr.id)
                    issue.status = "in-progress"
                    issue_manager.add_timeline_event(issue.id, "linked_pr", pr=pr.id)
                    issue_manager.save_issue(issue)

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
            # Reconstruct threads
            threads_data = data.pop("threads", [])
            threads = []
            for t in threads_data:
                replies_data = t.pop("replies", [])
                replies = [PRReply(**r) for r in replies_data]
                threads.append(PRThread(replies=replies, **t))
            
            data["threads"] = threads
            return PullRequest(**data)

    def list_prs(self) -> List[PullRequest]:
        prs = []
        for p in self.prs_dir.glob("*.json"):
            try:
                prs.append(self.get_pr(int(p.stem)))
            except Exception:
                continue
        return sorted(prs, key=lambda x: x.id)

    def merge_pr(self, pr_id: int) -> PullRequest:
        """Perform a local merge of head into base."""
        pr = self.get_pr(pr_id)
        if not pr:
            raise ValueError(f"PR #{pr_id} not found")
        if pr.status != "open":
            raise ValueError(f"PR #{pr_id} is already {pr.status}")

        from deep.core.refs import resolve_revision, update_branch, get_branch
        from deep.core.merge import recursive_merge
        
        head_sha = resolve_revision(self.dg_dir, pr.head)
        base_sha = resolve_revision(self.dg_dir, pr.base)
        
        if not head_sha or not base_sha:
            raise ValueError("Could not resolve branches to commits")
            
        # Recursive merge
        objects_dir = self.dg_dir / "objects"
        merged_tree, conflicts = recursive_merge(objects_dir, base_sha, head_sha)
        
        if conflicts:
            raise ValueError(f"Merge conflicts in: {', '.join(conflicts)}")
            
        # Create merge commit
        from deep.storage.objects import Commit
        merge_commit = Commit(
            tree_sha=merged_tree,
            parent_shas=[base_sha, head_sha],
            author=pr.author, # Use PR author as committer for simplicity? 
            message=f"Merge PR #{pr.id}: {pr.title}",
            timestamp=int(time.time())
        )
        merge_sha = merge_commit.write(objects_dir)
        
        # Update base branch
        update_branch(self.dg_dir, pr.base, merge_sha)
        
        pr.status = "merged"
        pr.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_pr(pr)
        return pr

    def close_pr(self, pr_id: int) -> PullRequest:
        pr = self.get_pr(pr_id)
        if not pr:
            raise ValueError(f"PR #{pr_id} not found.")
        pr.status = "closed"
        pr.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_pr(pr)
        return pr

    def reopen_pr(self, pr_id: int) -> PullRequest:
        pr = self.get_pr(pr_id)
        if not pr:
            raise ValueError(f"PR #{pr_id} not found.")
        pr.status = "open"
        pr.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_pr(pr)
        return pr
    def add_thread(self, pr_id: int, author: str, text: str) -> PRThread:
        pr = self.get_pr(pr_id)
        if not pr: raise ValueError(f"PR #{pr_id} not found")
        
        thread_id = len(pr.threads) + 1
        thread = PRThread(id=thread_id, author=author, text=text)
        pr.threads.append(thread)
        pr.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_pr(pr)
        
        # Timeline Sync (Issue)
        if pr.linked_issue:
            import deep.core.issue as issue_core
            im = issue_core.IssueManager(self.dg_dir)
            im.add_timeline_event(pr.linked_issue, "thread_created", pr=pr.id, thread=thread_id, author=author)
            
        return thread

    def add_reply(self, pr_id: int, thread_id: int, author: str, text: str) -> PRReply:
        pr = self.get_pr(pr_id)
        if not pr: raise ValueError(f"PR #{pr_id} not found")
        
        thread = next((t for t in pr.threads if t.id == thread_id), None)
        if not thread: raise ValueError(f"Thread #{thread_id} not found in PR #{pr_id}")
        
        reply = PRReply(author=author, text=text)
        thread.replies.append(reply)
        pr.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_pr(pr)
        
        # Timeline Sync (Issue)
        if pr.linked_issue:
            import deep.core.issue as issue_core
            im = issue_core.IssueManager(self.dg_dir)
            im.add_timeline_event(pr.linked_issue, "reply_added", pr=pr.id, thread=thread_id, author=author)
            
        return reply

    def resolve_thread(self, pr_id: int, thread_id: int):
        pr = self.get_pr(pr_id)
        if not pr: raise ValueError(f"PR #{pr_id} not found")
        
        thread = next((t for t in pr.threads if t.id == thread_id), None)
        if not thread: raise ValueError(f"Thread #{thread_id} not found in PR #{pr_id}")
        
        thread.resolved = True
        pr.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_pr(pr)
        
        # Timeline Sync (Issue)
        if pr.linked_issue:
            import deep.core.issue as issue_core
            im = issue_core.IssueManager(self.dg_dir)
            im.add_timeline_event(pr.linked_issue, "thread_resolved", pr=pr.id, thread=thread_id)

    def add_review(self, pr_id: int, author: str, status: str, comment: str = ""):
        pr = self.get_pr(pr_id)
        if not pr: raise ValueError(f"PR #{pr_id} not found")
        
        is_update = author in pr.reviews
        
        # Overwrite previous review by same author (Part 3)
        pr.reviews[author] = {
            "status": status,
            "comment": comment,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        pr.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save_pr(pr)
        
        # Timeline Sync (Issue)
        if pr.linked_issue:
            import deep.core.issue as issue_core
            im = issue_core.IssueManager(self.dg_dir)
            event = "review_updated" if is_update else "review_added"
            im.add_timeline_event(pr.linked_issue, event, pr=pr.id, author=author, status=status)

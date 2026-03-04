"""
deep_git.core.audit
~~~~~~~~~~~~~~~~~~~
Append-only audit log for enterprise operations.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class AuditEntry:
    timestamp: float
    user: str
    action: str
    ref: str = ""
    sha: str = ""
    client: str = "local"
    details: str = ""


class AuditLog:
    """Append-only audit log stored at .deep_git/audit.log."""

    def __init__(self, dg_dir: Path):
        self.log_path = dg_dir / "audit.log"

    def record(self, user: str, action: str, ref: str = "", sha: str = "",
               client: str = "local", details: str = ""):
        entry = AuditEntry(
            timestamp=time.time(),
            user=user,
            action=action,
            ref=ref,
            sha=sha,
            client=client,
            details=details,
        )
        from deep_git.core.utils import AtomicWriter
        with AtomicWriter(self.log_path, mode="a") as aw:
            aw.write(json.dumps(asdict(entry)) + "\n")

    def read_all(self) -> list[AuditEntry]:
        if not self.log_path.exists():
            return []
        entries = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    entries.append(AuditEntry(**json.loads(line)))
                except Exception:
                    pass
        return entries

    def read_by_user(self, user: str) -> list[AuditEntry]:
        return [e for e in self.read_all() if e.user == user]

    def read_by_action(self, action: str) -> list[AuditEntry]:
        return [e for e in self.read_all() if e.action == action]

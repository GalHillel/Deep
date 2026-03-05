"""
deep.network.sync
~~~~~~~~~~~~~~~~~~~~~
Real-time multi-user synchronisation engine.

Provides event broadcasting for ref updates, commit creation, and
conflict detection across connected clients.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from deep.storage.objects import read_object, Commit
from deep.core.refs import resolve_head, get_branch


@dataclass
class SyncEvent:
    """A synchronisation event."""
    event_type: str  # "ref_update", "new_commit", "conflict"
    ref: str = ""
    old_sha: str = ""
    new_sha: str = ""
    user: str = ""
    timestamp: float = field(default_factory=time.time)
    details: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "SyncEvent":
        return cls(**json.loads(data))


class SyncEngine:
    """Manages state synchronisation for multi-user environments."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.event_log: list[SyncEvent] = []
        self._listeners: list = []

    def register_listener(self, callback):
        """Register a callback for sync events."""
        self._listeners.append(callback)

    def broadcast(self, event: SyncEvent):
        """Broadcast an event to all listeners and log it."""
        self.event_log.append(event)
        for cb in self._listeners:
            try:
                cb(event)
            except Exception:
                pass

    def detect_conflict(self, ref: str, expected_old: str, new_sha: str) -> Optional[SyncEvent]:
        """Check for divergent push: is expected_old still the current ref?"""
        objects_dir = self.dg_dir / "objects"
        branch_name = ref.rsplit("/", 1)[-1] if "/" in ref else ref
        current = get_branch(self.dg_dir, branch_name)
        if current and current != expected_old:
            return SyncEvent(
                event_type="conflict",
                ref=ref,
                old_sha=expected_old,
                new_sha=new_sha,
                details=f"Divergent push: expected {expected_old[:8]}, current is {current[:8]}",
            )
        return None

    def record_ref_update(self, ref: str, old_sha: str, new_sha: str, user: str = ""):
        """Record and broadcast a ref update."""
        event = SyncEvent(
            event_type="ref_update",
            ref=ref,
            old_sha=old_sha,
            new_sha=new_sha,
            user=user,
        )
        self.broadcast(event)

    def get_events_since(self, since_ts: float) -> list[SyncEvent]:
        """Return events after a timestamp."""
        return [e for e in self.event_log if e.timestamp > since_ts]

    def get_all_events(self) -> list[dict]:
        """Return all events as dicts."""
        return [asdict(e) for e in self.event_log]

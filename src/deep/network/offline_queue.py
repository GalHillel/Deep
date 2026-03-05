"""
deep.network.offline_queue
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Offline operation queue for resilient distributed workflows.

Stores pending push/fetch operations when the network is unavailable
and automatically reconciles upon reconnection.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class QueuedOperation:
    operation: str  # "push" or "fetch"
    url: str
    ref: str
    sha: str
    timestamp: float
    status: str = "pending"  # pending, completed, failed
    error: str = ""


class OfflineQueue:
    """Persistent queue for offline operations."""

    def __init__(self, dg_dir: Path):
        self.queue_path = dg_dir / "offline_queue.json"
        self._ops: list[QueuedOperation] = []
        self._load()

    def _load(self):
        if self.queue_path.exists():
            try:
                data = json.loads(self.queue_path.read_text())
                self._ops = [QueuedOperation(**op) for op in data]
            except Exception:
                self._ops = []

    def _save(self):
        data = [asdict(op) for op in self._ops]
        self.queue_path.write_text(json.dumps(data, indent=2))

    def enqueue(self, operation: str, url: str, ref: str, sha: str):
        """Queue an operation for later execution."""
        self._ops.append(QueuedOperation(
            operation=operation, url=url, ref=ref, sha=sha,
            timestamp=time.time(),
        ))
        self._save()

    def get_pending(self) -> list[QueuedOperation]:
        return [op for op in self._ops if op.status == "pending"]

    def mark_completed(self, index: int):
        if 0 <= index < len(self._ops):
            self._ops[index].status = "completed"
            self._save()

    def mark_failed(self, index: int, error: str):
        if 0 <= index < len(self._ops):
            self._ops[index].status = "failed"
            self._ops[index].error = error
            self._save()

    def reconcile(self, push_fn=None, fetch_fn=None) -> dict:
        """Attempt to execute all pending operations. Returns summary."""
        results = {"completed": 0, "failed": 0}
        for i, op in enumerate(self._ops):
            if op.status != "pending":
                continue
            try:
                if op.operation == "push" and push_fn:
                    push_fn(op.url, op.ref, op.sha)
                elif op.operation == "fetch" and fetch_fn:
                    fetch_fn(op.url, op.sha)
                self.mark_completed(i)
                results["completed"] += 1
            except Exception as e:
                self.mark_failed(i, str(e))
                results["failed"] += 1
        return results

    def clear_completed(self):
        self._ops = [op for op in self._ops if op.status != "completed"]
        self._save()

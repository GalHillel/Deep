"""
deep.core.telemetry
~~~~~~~~~~~~~~~~~~~~~~~
Performance metrics collection and reporting.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class OperationMetric:
    operation: str
    duration_ms: float
    timestamp: float
    details: str = ""


class TelemetryCollector:
    """Collects and exports performance metrics."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.metrics_path = dg_dir / "metrics.json"
        self._operations: list[OperationMetric] = []
        self._counters: dict[str, int] = {}
        self._load()

    def _load(self):
        if self.metrics_path.exists():
            try:
                data = json.loads(self.metrics_path.read_text())
                self._counters = data.get("counters", {})
            except Exception:
                pass

    def record(self, operation: str, duration_ms: float, details: str = ""):
        """Record an operation metric."""
        m = OperationMetric(operation, duration_ms, time.time(), details)
        self._operations.append(m)
        self._counters[operation] = self._counters.get(operation, 0) + 1
        self._save()

    def _save(self):
        data = {
            "counters": self._counters,
            "last_operations": [asdict(m) for m in self._operations[-50:]],
            "summary": self.summary(),
        }
        from deep.utils.utils import AtomicWriter
        with AtomicWriter(self.metrics_path, mode="w") as aw:
            aw.write(json.dumps(data, indent=2, default=str))

    def summary(self) -> dict:
        """Aggregate summary stats."""
        if not self._operations:
            return {"total_ops": 0}
        by_op: dict[str, list[float]] = {}
        for m in self._operations:
            by_op.setdefault(m.operation, []).append(m.duration_ms)
        result = {"total_ops": len(self._operations)}
        for op, times in by_op.items():
            result[f"{op}_avg_ms"] = round(sum(times) / len(times), 2)
            result[f"{op}_count"] = len(times)
        return result

    def get_export(self) -> dict:
        """Get a dashboard-friendly export."""
        return {
            "counters": self._counters,
            "summary": self.summary(),
        }


class Timer:
    """Context manager for timing operations."""

    def __init__(self, collector: TelemetryCollector, operation: str, details: str = ""):
        self.collector = collector
        self.operation = operation
        self.details = details
        self._start: float = 0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed = (time.perf_counter() - self._start) * 1000
        self.collector.record(self.operation, elapsed, self.details)

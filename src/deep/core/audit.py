"""
deep.core.audit
~~~~~~~~~~~~~~~~~~~
Append-only audit log for enterprise operations.

GOD MODE: Merkle hash chain for tamper detection.
Each entry is hashed with SHA-256 linking to the previous entry's hash.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class AuditEntry:
    timestamp: float
    user: str
    action: str
    ref: str = ""
    sha: str = ""
    client: str = "local"
    details: str = ""
    entry_hash: str = ""
    prev_hash: str = ""


class AuditLog:
    """Append-only audit log stored at .deep/audit.log.

    GOD MODE: Each entry is hash-chained using SHA-256 for tamper detection.
    """

    def __init__(self, dg_dir: Path):
        self.log_path = dg_dir / "audit.log"

    def _get_last_hash(self) -> str:
        """Read the last entry's hash to chain from."""
        if not self.log_path.exists():
            return ""
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if line.strip():
                try:
                    data = json.loads(line)
                    return data.get("entry_hash", "")
                except Exception:
                    pass
        return ""

    @staticmethod
    def _compute_hash(entry_data: str, prev_hash: str) -> str:
        """Compute SHA-256 hash for Merkle chain."""
        payload = f"{prev_hash}|{entry_data}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record(self, user: str, action: str, ref: str = "", sha: str = "",
               client: str = "local", details: str = ""):
        prev_hash = self._get_last_hash()

        entry = AuditEntry(
            timestamp=time.time(),
            user=user,
            action=action,
            ref=ref,
            sha=sha,
            client=client,
            details=details,
        )

        # Compute hash over the entry data (without hash fields)
        data_dict = asdict(entry)
        # Remove hash fields for computation
        data_dict.pop("entry_hash", None)
        data_dict.pop("prev_hash", None)
        entry_data = json.dumps(data_dict, sort_keys=True)

        entry.prev_hash = prev_hash
        entry.entry_hash = self._compute_hash(entry_data, prev_hash)

        from deep.utils.utils import AtomicWriter
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

    def verify_chain(self) -> Tuple[bool, int]:
        """Verify the integrity of the Merkle chain.

        Returns:
            Tuple of (is_valid, first_invalid_index).
            If valid, returns (True, -1).
        """
        entries = self.read_all()
        prev_hash = ""

        for i, entry in enumerate(entries):
            if not entry.entry_hash:
                # Pre-hardening entry without hash — skip, update prev
                continue

            if entry.prev_hash != prev_hash:
                return False, i

            # Reconstruct entry data without hash fields
            data_dict = asdict(entry)
            data_dict.pop("entry_hash", None)
            data_dict.pop("prev_hash", None)
            entry_data = json.dumps(data_dict, sort_keys=True)

            computed = self._compute_hash(entry_data, prev_hash)
            if computed != entry.entry_hash:
                return False, i

            prev_hash = entry.entry_hash

        return True, -1

    def export_report(self) -> str:
        """Export a formatted audit report with integrity status."""
        entries = self.read_all()
        is_valid, invalid_idx = self.verify_chain()

        lines = []
        lines.append("=" * 70)
        lines.append("DEEPGIT AUDIT REPORT")
        lines.append("=" * 70)
        lines.append(f"Total entries: {len(entries)}")
        lines.append(f"Chain integrity: {'✅ VALID' if is_valid else f'❌ INVALID at entry {invalid_idx}'}")
        lines.append("")
        lines.append(f"{'#':<5} {'TIMESTAMP':<20} {'USER':<15} {'ACTION':<15} {'HASH':<12}")
        lines.append("-" * 70)

        for i, e in enumerate(entries):
            import datetime
            ts = datetime.datetime.fromtimestamp(e.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            short_hash = e.entry_hash[:10] + "…" if e.entry_hash else "n/a"
            lines.append(f"{i:<5} {ts:<20} {e.user:<15} {e.action:<15} {short_hash}")

        lines.append("-" * 70)
        lines.append(f"Integrity: {'✅ ALL ENTRIES VERIFIED' if is_valid else '❌ CHAIN BROKEN'}")
        lines.append("=" * 70)
        return "\n".join(lines)

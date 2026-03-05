"""
deep_git.core.txlog
~~~~~~~~~~~~~~~~~~~
Write-ahead transaction log for crash recovery.

GOD MODE: WAL entries can be cryptographically signed for integrity verification.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class TxRecord:
    tx_id: str
    operation: str  # "commit", "push", "merge", etc.
    status: str     # "BEGIN", "COMMIT", "ROLLBACK"
    timestamp: float
    details: str = ""
    target_object_id: str = ""
    branch_ref: str = ""
    previous_commit_sha: str = ""
    signature: str = ""  # GOD MODE: HMAC signature of the record
    signing_key_id: str = ""  # GOD MODE: Key ID used for signing


class TransactionLog:
    """Write-ahead log at .deep_git/txlog.

    GOD MODE: Supports signed WAL entries for tamper detection during recovery.
    """

    def __init__(self, dg_dir: Path):
        self.log_path = dg_dir / "txlog"
        self.dg_dir = dg_dir

    def begin(self, operation: str, details: str = "", target_object_id: str = "",
              branch_ref: str = "", previous_commit_sha: str = "",
              signing_key_id: Optional[str] = None) -> str:
        """Start a new transaction, return tx_id.

        If signing_key_id is provided, the WAL entry is signed.
        """
        tx_id = f"{operation}_{int(time.time() * 1000)}"
        record = TxRecord(
            tx_id=tx_id,
            operation=operation,
            status="BEGIN",
            timestamp=time.time(),
            details=details,
            target_object_id=target_object_id,
            branch_ref=branch_ref,
            previous_commit_sha=previous_commit_sha,
        )

        if signing_key_id:
            record = self._sign_record(record, signing_key_id)

        self._write(record)
        return tx_id

    def commit(self, tx_id: str):
        """Mark a transaction as committed."""
        self._write(TxRecord(tx_id, "", "COMMIT", time.time()))

    def rollback(self, tx_id: str, reason: str = ""):
        """Mark a transaction as rolled back."""
        self._write(TxRecord(tx_id, "", "ROLLBACK", time.time(), reason))

    def _sign_record(self, record: TxRecord, key_id: str) -> TxRecord:
        """Sign a WAL record using the specified key."""
        try:
            from deep_git.core.security import KeyManager, CommitSigner
            km = KeyManager(self.dg_dir)
            signer = CommitSigner(km)
            data = json.dumps(asdict(record), sort_keys=True).encode("utf-8")
            sig_hex, used_key_id = signer.sign(data, key_id)
            record.signature = sig_hex
            record.signing_key_id = used_key_id
        except Exception:
            pass  # Signing is optional; failure doesn't block operation
        return record

    def _write(self, record: TxRecord):
        from deep_git.core.utils import AtomicWriter
        with AtomicWriter(self.log_path, mode="a") as aw:
            aw.write(json.dumps(asdict(record)) + "\n")

    def read_all(self) -> list[TxRecord]:
        if not self.log_path.exists():
            return []
        records = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(TxRecord(**json.loads(line)))
                except Exception:
                    pass
        return records

    def get_incomplete(self) -> list[TxRecord]:
        """Find transactions that were started but never committed or rolled back."""
        records = self.read_all()
        begun: dict[str, TxRecord] = {}
        completed: set[str] = set()
        for r in records:
            if r.status == "BEGIN":
                begun[r.tx_id] = r
            elif r.status in ("COMMIT", "ROLLBACK"):
                completed.add(r.tx_id)
        
        return [r for tx_id, r in begun.items() if tx_id not in completed]

    def needs_recovery(self) -> bool:
        """Check if there are incomplete transactions."""
        return len(self.get_incomplete()) > 0

    def verify_record_signature(self, record: TxRecord) -> bool:
        """Verify the HMAC signature of a WAL record.

        Returns True if valid or if unsigned (backward compat).
        """
        if not record.signature or not record.signing_key_id:
            return True  # Unsigned records pass (backward compat)

        try:
            from deep_git.core.security import KeyManager, CommitSigner
            km = KeyManager(self.dg_dir)
            signer = CommitSigner(km)

            # Reconstruct the record without signature for verification
            verify_record = TxRecord(
                tx_id=record.tx_id,
                operation=record.operation,
                status=record.status,
                timestamp=record.timestamp,
                details=record.details,
                target_object_id=record.target_object_id,
                branch_ref=record.branch_ref,
                previous_commit_sha=record.previous_commit_sha,
            )
            data = json.dumps(asdict(verify_record), sort_keys=True).encode("utf-8")
            return signer.verify(data, record.signature, record.signing_key_id)
        except Exception:
            return False

    def verify_all(self) -> list[tuple[str, bool]]:
        """Verify signatures on all WAL records.

        Returns list of (tx_id, is_valid) tuples.
        """
        results = []
        for record in self.read_all():
            is_valid = self.verify_record_signature(record)
            results.append((record.tx_id, is_valid))
        return results

    def recover(self):
        """Perform idempotent recovery on incomplete transactions.

        GOD MODE: Verifies WAL entry signatures before applying recovery.
        """

        incomplete = self.get_incomplete()
        if not incomplete:
            return

        from deep_git.core.refs import get_branch, update_branch
        from deep_git.core.objects import read_object_safe

        for record in incomplete:
            # GOD MODE: Verify signature before trusting the WAL entry
            if record.signature and not self.verify_record_signature(record):
                self.rollback(record.tx_id, "Crash recovery: WAL signature verification failed")
                continue

            # If a commit crashed mid-flight, we need to restore the branch pointer
            # to its previous state. The objects written are content-addressable and 
            # won't cause corruption if left dangling.
            if record.operation == "commit" and record.branch_ref:
                # We attempt to rollback the branch to `previous_commit_sha`
                # Only if the database doesn't actually contain the `target_object_id`
                # If it DOES contain the target_object_id, maybe the branch update DID succeed 
                # but the txlog COMMIT write failed.
                objects_dir = self.log_path.parent / "objects"
                commit_fully_written = False
                
                if record.target_object_id:
                    try:
                        read_object_safe(objects_dir, record.target_object_id)
                        commit_fully_written = True
                    except (FileNotFoundError, ValueError):
                        pass

                if commit_fully_written:
                    # The commit objects made it to disk. 
                    # We ensure the branch points to it, effectively rolling *forward*.
                    update_branch(self.log_path.parent, record.branch_ref, record.target_object_id)
                    self.commit(record.tx_id)
                elif record.previous_commit_sha:
                    # Rollback the branch to the previous state.
                    update_branch(self.log_path.parent, record.branch_ref, record.previous_commit_sha)
                    self.rollback(record.tx_id, "Crash recovery: rolled back branch pointer")
                else:
                    # It was a detached HEAD or first commit, we can't cleanly restore a branch ref
                    # but we mark it rolled back so it isn't repeatedly retried.
                    self.rollback(record.tx_id, "Crash recovery: aborted incomplete transaction")
            else:
                self.rollback(record.tx_id, "Crash recovery: unknown operation aborted")

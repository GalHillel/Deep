"""
deep.core.txlog
~~~~~~~~~~~~~~~~~~~
Write-ahead transaction log for crash recovery.

GOD MODE: WAL entries can be cryptographically signed for integrity verification.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Any, cast


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
    """Write-ahead log at .deep/txlog.

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
        # Unique TxID: operation + timestamp_ms + 8-char UUID suffix
        tx_id = f"{operation}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}" # type: ignore
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
        self._write(TxRecord(
            tx_id=tx_id, 
            operation="", 
            status="COMMIT", 
            timestamp=time.time()
        ))

    def rollback(self, tx_id: Optional[str] = None, reason: str = ""):
        """Mark a transaction as rolled back.
        
        If tx_id is not provided, attempting to rollback the last successful commit.
        """
        if tx_id:
            self._write(TxRecord(
                tx_id=tx_id, 
                operation="", 
                status="ROLLBACK", 
                timestamp=time.time(), 
                details=reason
            ))
        else:
            # Revert the last committed transaction intentionally
            records = self.read_all()
            last_commit_record = None
            last_begin_record = None
            
            for r in reversed(records):
                if r.status == "COMMIT":
                    last_commit_record = r
                    break
                    
            if not last_commit_record:
                print("No committed transactions found to rollback.")
                return False
            
            # Explicitly cast to Any for subsequent comparisons
            lcr_any = cast(Any, last_commit_record)
            for r in reversed(records):
                r_any = cast(Any, r)
                if r_any.tx_id == lcr_any.tx_id and r_any.status == "BEGIN":
                    last_begin_record = r
                    break
                    
            if last_begin_record:
                lbr_any = cast(Any, last_begin_record)
                if lbr_any.branch_ref:
                    from deep.core.refs import update_branch, update_head, resolve_head # type: ignore
                    # Restore the previous commit
                    if lbr_any.previous_commit_sha:
                        update_branch(self.log_path.parent, lbr_any.branch_ref, lbr_any.previous_commit_sha)
                    
                    # Append a new rollback record for the system
                    self._write(TxRecord(
                        tx_id=lbr_any.tx_id, 
                        operation="manual_rollback", 
                        status="ROLLBACK", 
                        timestamp=time.time(), 
                        details=reason
                    ))
                    return True
            return False

    def _sign_record(self, record: TxRecord, key_id: str) -> TxRecord:
        """Sign a WAL record using the specified key."""
        try:
            from deep.core.security import KeyManager, CommitSigner # type: ignore
            km = KeyManager(self.dg_dir)
            signer = CommitSigner(km)
            data = json.dumps(asdict(cast(Any, record)), sort_keys=True).encode("utf-8") # type: ignore
            sig_hex, used_key_id = signer.sign(data, key_id)
            record.signature = sig_hex
            record.signing_key_id = used_key_id
        except Exception:
            pass  # Signing is optional; failure doesn't block operation
        return record

    def _write(self, record: TxRecord):
        # Use the thread-safe AtomicWriter (which uses locks for appends).
        from deep.utils.utils import AtomicWriter # type: ignore
        with AtomicWriter(self.log_path, mode="a") as aw:
            aw.write(json.dumps(asdict(cast(Any, record))) + "\n") # type: ignore

    def read_all(self) -> list[TxRecord]:
        if not self.log_path.exists():
            return []
        records = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(TxRecord(**cast(dict, json.loads(line)))) # type: ignore
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
            from deep.core.security import KeyManager, CommitSigner # type: ignore
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
            data = json.dumps(asdict(cast(Any, verify_record)), sort_keys=True).encode("utf-8") # type: ignore
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

        from deep.core.refs import get_branch, update_branch, update_head # type: ignore
        from deep.storage.objects import read_object_safe # type: ignore

        for record in incomplete:
            # GOD MODE: Verify signature before trusting the WAL entry
            if record.signature and not self.verify_record_signature(record):
                self.rollback(record.tx_id, "Crash recovery: WAL signature verification failed")
                continue

            # If an operation crashed mid-flight, we need to ensure the branch pointer
            # is consistent (either rolled back to previous or forward to target).
            supported_ops = (
                "commit", "checkout", "merge", "merge-ff", "merge-3way",
                "reset-hard", "reset-soft", "reset-mixed", "stash-save"
            )
            
            if record.operation in supported_ops and record.branch_ref:
                objects_dir = self.log_path.parent / "objects"
                target_fully_written = False
                
                if record.target_object_id:
                    try:
                        # For commits/merges, ensure the commit object exists.
                        # For checkout/reset, ensure the target commit exists.
                        read_object_safe(objects_dir, record.target_object_id)
                        target_fully_written = True
                    except (FileNotFoundError, ValueError):
                        pass

                # If the target object is on disk, we can potentially roll forward the ref.
                # However, for checkout/reset-hard, rolling forward also implies WD update.
                # For safety, we only roll forward the ref if it was most likely the last step.
                
                current_ref_sha = None
                try:
                    from deep.core.refs import resolve_head, get_branch # type: ignore
                    if record.branch_ref == "HEAD":
                        current_ref_sha = resolve_head(self.log_path.parent)
                    elif record.branch_ref.startswith("refs/heads/"):
                        current_ref_sha = get_branch(self.log_path.parent, record.branch_ref[len("refs/heads/"):]) # type: ignore
                except Exception:
                    pass

                if current_ref_sha == record.target_object_id:
                    # Pointer already updated! Just commit the WAL entry.
                    self.commit(record.tx_id)
                elif target_fully_written and record.operation in (
                    "commit", "merge", "merge-3way", "merge-ff", "checkout", 
                    "reset-hard", "reset-mixed", "reset-soft"
                ):
                    # Roll forward is safe for these if the target object is fully available.
                    
                    # For operations that modify the WD, we MUST restore the WD too.
                    if record.operation in ("checkout", "reset-hard", "merge", "merge-3way", "merge-ff"):
                        self._restore_workdir(record.target_object_id, record.previous_commit_sha)

                    if record.branch_ref == "HEAD":
                        update_head(self.log_path.parent, record.target_object_id)
                    else:
                        branch_name = record.branch_ref
                        if branch_name.startswith("refs/heads/"):
                            branch_name = branch_name[len("refs/heads/"):] # type: ignore
                        update_branch(self.log_path.parent, branch_name, record.target_object_id)
                    self.commit(record.tx_id)
                elif record.previous_commit_sha:
                    # Rollback the pointer to the previous state for safety.
                    
                    # If we are rolling back a WD-modifying op, should we restore old WD?
                    # For now, rolling back mostly happens if target commit is missing.
                    if record.branch_ref == "HEAD":
                        update_head(self.log_path.parent, record.previous_commit_sha)
                    else:
                        branch_name = record.branch_ref
                        if branch_name.startswith("refs/heads/"):
                            branch_name = branch_name[len("refs/heads/"):] # type: ignore
                        update_branch(self.log_path.parent, branch_name, record.previous_commit_sha)
                    self.rollback(record.tx_id, "Crash recovery: rolled back pointer")
                else:
                    self.rollback(record.tx_id, "Crash recovery: aborted incomplete transaction")
            else:
                self.rollback(record.tx_id, f"Crash recovery: operation '{record.operation}' aborted")

    def _restore_workdir(self, commit_sha: str, previous_commit_sha: str = ""):
        """Restore the working directory to the state of the given commit."""
        from deep.storage.objects import read_object, Commit # type: ignore
        from deep.storage.index import DeepIndex, DeepIndexEntry, write_index, read_index_no_lock # type: ignore
        from deep.core.repository import _get_tree_files # type: ignore

        dg_dir = self.log_path.parent
        repo_root = dg_dir.parent
        objects_dir = dg_dir / "objects"

        commit = read_object(objects_dir, commit_sha)
        if not isinstance(commit, Commit):
            return

        target_files = _get_tree_files(objects_dir, commit.tree_sha)
        
        current_index = DeepIndex()
        try:
            current_index = read_index_no_lock(dg_dir)
        except Exception:
            pass

        if previous_commit_sha:
            try:
                prev_commit = read_object(objects_dir, previous_commit_sha)
                if isinstance(prev_commit, Commit):
                    prev_files = _get_tree_files(objects_dir, prev_commit.tree_sha)
                    for p in prev_files:
                        if p not in target_files:
                            full_path = repo_root / p
                            if full_path.exists():
                                full_path.unlink()
                                parent = full_path.parent
                                while parent != repo_root:
                                    try:
                                        parent.rmdir()
                                    except OSError:
                                        break
                                    parent = parent.parent
                            if p in current_index.entries:
                                del current_index.entries[p]
            except Exception:
                pass

        import hashlib as _hashlib
        for p, sha in target_files.items():
            full = repo_root / p
            full.parent.mkdir(parents=True, exist_ok=True)
            obj = read_object(objects_dir, sha)
            full.write_bytes(obj.serialize_content())
            stat = full.stat()
            current_index.entries[p] = DeepIndexEntry(
                content_hash=sha,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                path_hash=_hashlib.sha1(p.encode()).hexdigest(),
            )
        
        write_index(dg_dir, current_index)

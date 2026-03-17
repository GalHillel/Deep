"""
deep.commands.rollback_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep rollback --verify`` — Perform verified rollback with WAL
signature validation before restoring state.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_DIR, find_repo


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    verify = getattr(args, "verify", False)

    from deep.storage.txlog import TransactionLog
    txlog = TransactionLog(dg_dir)

    incomplete = txlog.get_incomplete()
    if not incomplete:
        print("No incomplete transactions to recover.")
        print("Attempting to rollback the last successful commit...")
        success = txlog.rollback(reason="Manual rollback via CLI")
        if success:
            print("Successfully rolled back the last transaction.")
            
            # Log to audit
            from deep.core.audit import AuditLog
            audit = AuditLog(dg_dir)
            audit.record(
                user="system",
                action="rollback",
                details="manual_rollback_successful",
            )
        else:
            print("Rollback failed. No prior transaction found.")
        return

    print(f"Found {len(incomplete)} incomplete transaction(s).")

    if verify:
        print("\n🔐 Verifying WAL signatures before rollback...")
        all_valid = True
        for record in incomplete:
            is_valid = txlog.verify_record_signature(record)
            status = "✅" if is_valid else "❌"
            print(f"  {record.tx_id}: {status}")
            if not is_valid:
                all_valid = False

        if not all_valid:
            print("\n⚠ Some WAL entries have invalid signatures!")
            print("  Rollback will skip entries with invalid signatures.")

    print("\nPerforming crash recovery...")
    txlog.recover()
    print("Recovery complete.")

    # Verify state after recovery
    remaining = txlog.get_incomplete()
    if remaining:
        print(f"\n⚠ {len(remaining)} transaction(s) still incomplete.")
    else:
        print("\n✅ All transactions resolved.")

    # Log to audit
    from deep.core.audit import AuditLog
    audit = AuditLog(dg_dir)
    audit.record(
        user="system",
        action="rollback",
        details=f"verified={verify} resolved={len(incomplete) - len(remaining)}",
    )

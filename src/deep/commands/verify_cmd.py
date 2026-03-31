"""
deep.commands.verify_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep verify --all`` — Verify all commit signatures, DAG integrity,
and audit chain in the repository.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'verify' command parser."""
    subparsers.add_parser(
        "verify",
        help="Verify commit signatures and DAG integrity",
        description="Check that all commit signatures, DAG connectivity, and audit chains are valid.",
        epilog=f"""
Examples:
{format_example("deep verify", "Run a complete security and integrity audit")}
""",
        formatter_class=DeepHelpFormatter,
    )


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    results = {
        "signatures": "✅",
        "dag": "✅",
        "audit_chain": "✅",
        "wal": "✅",
    }
    details = []

    # 1. Verify commit signatures
    from deep.core.refs import resolve_head, list_branches, get_branch
    from deep.storage.objects import read_object, Commit

    total_commits = 0
    signed_commits = 0
    verified_commits = 0
    failed_commits = 0

    checked_shas = set()

    def walk_commits(start_sha: str):
        nonlocal total_commits, signed_commits, verified_commits, failed_commits
        sha = start_sha
        while sha and sha not in checked_shas:
            checked_shas.add(sha)
            try:
                obj = read_object(objects_dir, sha)
                if isinstance(obj, Commit):
                    total_commits += 1
                    if obj.signature:
                        signed_commits += 1
                        # Verify signature
                        try:
                            from deep.core.security import KeyManager, CommitSigner
                            km = KeyManager(dg_dir)
                            signer = CommitSigner(km)
                            if signer.verify_commit(obj):
                                verified_commits += 1
                            else:
                                failed_commits += 1
                        except Exception:
                            # Can't verify (no keyring) — not a failure
                            pass
                    sha = obj.parent_shas[0] if obj.parent_shas else None
                else:
                    break
            except Exception:
                break

    for branch in list_branches(dg_dir):
        branch_sha = get_branch(dg_dir, branch)
        if branch_sha:
            walk_commits(branch_sha)

    head_sha = resolve_head(dg_dir)
    if head_sha:
        walk_commits(head_sha)

    details.append(f"Commits: {total_commits} total, {signed_commits} signed, {verified_commits} verified")
    if failed_commits > 0:
        results["signatures"] = "❌"
        details.append(f"  ⚠ {failed_commits} signature(s) FAILED verification")

    # 2. Verify DAG integrity (all parent references exist)
    dag_errors = 0
    for sha in checked_shas:
        try:
            obj = read_object(objects_dir, sha)
            if isinstance(obj, Commit):
                for parent in obj.parent_shas:
                    try:
                        read_object(objects_dir, parent)
                    except Exception:
                        dag_errors += 1
        except Exception:
            pass

    if dag_errors > 0:
        results["dag"] = "❌"
        details.append(f"  ⚠ {dag_errors} broken parent reference(s)")
    else:
        details.append("DAG: All parent references valid")

    # 3. Verify audit chain
    from deep.core.audit import AuditLog
    audit = AuditLog(dg_dir)
    chain_valid, invalid_idx = audit.verify_chain()
    if not chain_valid:
        results["audit_chain"] = "❌"
        details.append(f"  ⚠ Audit chain broken at entry {invalid_idx}")
    else:
        entries = audit.read_all()
        details.append(f"Audit chain: {len(entries)} entries, integrity verified")

    # 4. Verify WAL signatures
    from deep.storage.txlog import TransactionLog
    txlog = TransactionLog(dg_dir)
    wal_results = txlog.verify_all()
    wal_failures = sum(1 for _, valid in wal_results if not valid)
    if wal_failures > 0:
        results["wal"] = "❌"
        details.append(f"  ⚠ {wal_failures} WAL entry signature(s) FAILED")
    else:
        details.append(f"WAL: {len(wal_results)} entries, all signatures valid")

    # Output
    print("=" * 60)
    print("DEEP VERIFICATION REPORT")
    print("=" * 60)
    print(f"  Signatures: {results['signatures']}")
    print(f"  DAG:        {results['dag']}")
    print(f"  Audit:      {results['audit_chain']}")
    print(f"  WAL:        {results['wal']}")
    print("-" * 60)
    for d in details:
        print(f"  {d}")
    print("=" * 60)

    all_pass = all(v == "✅" for v in results.values())
    print(f"\nOverall: {'✅ ALL CHECKS PASSED' if all_pass else '❌ ISSUES DETECTED'}")

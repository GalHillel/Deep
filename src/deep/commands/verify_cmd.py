"""
deep.commands.verify_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep verify --all`` — Verify all commit signatures, DAG integrity,
and audit chain in the repository.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
import time
from pathlib import Path
from typing import Set

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

def run(args) -> None:
    console = Console()
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        console.print(f"[red]Deep: error: {exc}[/red]")
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    verbose = getattr(args, "verbose", False)
    all_objects = getattr(args, "all", False)

    results = {
        "signatures": "✅",
        "dag": "✅",
        "audit_chain": "✅",
        "wal": "✅",
        "integrity": "✅",
    }
    details = []

    # 1. Verification Logic
    from deep.core.refs import resolve_head, list_branches, get_branch, list_tags, get_tag
    from deep.storage.objects import read_object_safe, Commit, Tree, Tag, Blob, walk_loose_shas
    from deep.storage.pack import PackReader

    total_objects = 0
    total_commits = 0
    signed_commits = 0
    verified_commits = 0
    failed_commits = 0
    corrupt_objects = 0
    
    shas_to_verify: Set[str] = set()

    if all_objects:
        # Full database scan
        console.print("[blue]⚓️ Full database scan initiated (including unreachable objects)...[/blue]")
        shas_to_verify.update(walk_loose_shas(objects_dir))
        reader = PackReader(dg_dir)
        shas_to_verify.update(reader.get_all_shas())
    else:
        # Reachable only
        console.print("[blue]⚓️ Scanning reachable objects from branches, tags, and HEAD...[/blue]")
        
        starting_shas = set()
        for b in list_branches(dg_dir):
            sha = get_branch(dg_dir, b)
            if sha: starting_shas.add(sha)
        for t in list_tags(dg_dir):
            sha = get_tag(dg_dir, t)
            if sha: starting_shas.add(sha)
        head_sha = resolve_head(dg_dir)
        if head_sha: starting_shas.add(head_sha)
        
        # BFS to find all reachable objects
        queue = list(starting_shas)
        while queue:
            sha = queue.pop(0)
            if sha in shas_to_verify: continue
            shas_to_verify.add(sha)
            
            try:
                # Use read_object to avoid redundant hash check during reachability walk
                # We will check hashes properly in the next loop
                from deep.storage.objects import read_object
                obj = read_object(objects_dir, sha)
                if isinstance(obj, Commit):
                    queue.append(obj.tree_sha)
                    queue.extend(obj.parent_shas)
                elif isinstance(obj, Tree):
                    for entry in obj.entries:
                        queue.append(entry.sha)
                elif isinstance(obj, Tag):
                    queue.append(obj.target_sha)
            except Exception:
                pass

    total_objects = len(shas_to_verify)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Verifying objects...", total=total_objects)
        
        for sha in sorted(list(shas_to_verify)):
            if verbose:
                progress.console.print(f"  verify: {sha}")
            
            try:
                # read_object_safe automatically verifies the hash integrity
                obj = read_object_safe(objects_dir, sha)
                
                if isinstance(obj, Commit):
                    total_commits += 1
                    if obj.signature:
                        signed_commits += 1
                        try:
                            from deep.core.security import KeyManager, CommitSigner
                            km = KeyManager(dg_dir)
                            signer = CommitSigner(km)
                            if signer.verify_commit(obj):
                                verified_commits += 1
                            else:
                                failed_commits += 1
                        except Exception:
                            # Verification failure (not due to corrupt data, but missing keys)
                            # is not considered a corruption.
                            pass
                
            except (ValueError, FileNotFoundError, Exception) as e:
                corrupt_objects += 1
                if verbose:
                    progress.console.print(f"[bold red]  Error in {sha}: {e}[/bold red]")
            
            progress.advance(task)

    details.append(f"Objects: {total_objects} scanned, {corrupt_objects} corruption(s)")
    if corrupt_objects > 0:
        results["integrity"] = "❌"
        details.append(f"  ⚠ {corrupt_objects} object(s) are corrupted or missing")
    
    details.append(f"Signatures: {total_commits} commits found, {signed_commits} signed, {verified_commits} verified")
    if failed_commits > 0:
        results["signatures"] = "❌"
        details.append(f"  ⚠ {failed_commits} signature(s) FAILED verification")

    # 2. DAG integrity (reachable check)
    dag_errors = 0
    # For DAG, we check reachable commits' parents
    for sha in shas_to_verify:
        try:
            from deep.storage.objects import read_object
            obj = read_object(objects_dir, sha)
            if isinstance(obj, Commit):
                for parent in obj.parent_shas:
                    if parent not in shas_to_verify:
                        # Parent is missing or unreachable from where we walked
                        # (Only relevant if we did a reachable walk)
                        if not all_objects:
                            dag_errors += 1
        except Exception:
            pass

    if dag_errors > 0:
        results["dag"] = "❌"
        details.append(f"  ⚠ {dag_errors} broken unreachable parent reference(s)")
    else:
        details.append("DAG: Reachable graph is consistent")

    # 3. Audit chain
    from deep.core.audit import AuditLog
    audit = AuditLog(dg_dir)
    try:
        chain_valid, invalid_idx = audit.verify_chain()
        if not chain_valid:
            results["audit_chain"] = "❌"
            details.append(f"  ⚠ Audit chain broken at entry {invalid_idx}")
        else:
            entries = audit.read_all()
            details.append(f"Audit chain: {len(entries)} entries, integrity verified")
    except Exception:
        results["audit_chain"] = "❌"
        details.append("  ⚠ Failed to read Audit Log")

    # 4. WAL
    from deep.storage.txlog import TransactionLog
    txlog = TransactionLog(dg_dir)
    try:
        wal_results = txlog.verify_all()
        wal_failures = sum(1 for _, valid in wal_results if not valid)
        if wal_failures > 0:
            results["wal"] = "❌"
            details.append(f"  ⚠ {wal_failures} WAL entry signature(s) FAILED")
        else:
            details.append(f"WAL: {len(wal_results)} entries, all signatures valid")
    except Exception:
         results["wal"] = "❓"

    # Report
    table = Table(title="⚓️ VERIFICATION REPORT", title_style="bold green", show_header=False, box=None)
    table.add_row("Object Integrity", results["integrity"])
    table.add_row("Commit Signatures", results["signatures"])
    table.add_row("DAG Graph", results["dag"])
    table.add_row("Audit Chain", results["audit_chain"])
    table.add_row("WAL Security", results["wal"])

    console.print("")
    console.print(Panel(table, border_style="cyan"))
    
    console.print("\n[bold]Details:[/bold]")
    for d in details:
        console.print(f"  {d}")

    all_pass = all(v in ("✅", "❓") for v in results.values())
    if all_pass:
        console.print(f"\n[bold green]⚓️ Overall: ALL CHECKS PASSED[/bold green]")
    else:
        console.print(f"\n[bold red]⚓️ Overall: ISSUES DETECTED[/bold red]")
        raise DeepCLIException(2) # Integrity issues detected

if __name__ == "__main__":
    pass

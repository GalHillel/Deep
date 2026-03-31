"""
deep.commands.doctor_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep doctor`` command implementation.

Verifies the integrity of the repository: refs, index, and objects.
"""
from deep.core.issue import Issue
from deep.core.issue import IssueManager
from deep.core.pr import PR
from deep.core.pr import PRManager
from deep.utils.ux import Color
import shutil

from __future__ import annotations
from deep.core.errors import DeepCLIException

import argparse
import os
import sys
import zlib
from pathlib import Path

from deep.storage.index import read_index
from deep.storage.objects import Blob, Commit, Tag, Tree, read_object, DeepObject
from deep.core.refs import list_branches, resolve_head, list_tags, get_tag, get_branch
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo

from typing import Any

def setup_parser(subparsers: Any) -> None:
    """Set up the 'doctor' command parser."""
    p_doctor = subparsers.add_parser(
        "doctor",
        help="Check the repository for consistency and health",
        description="""Deep Doctor performs a deep diagnostic scan of the repository.

It verifies the structural integrity of objects, ensures references (refs) point to valid commits, checks the index for corruption, and validates the consistency of branching and PR metadata.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep doctor\033[0m
     Run a comprehensive health check on the current repository
  \033[1;34m⚓️ deep doctor --fix\033[0m
     Identify and attempt to automatically repair non-critical issues
  \033[1;34m⚓️ deep doctor --verbose\033[0m
     Show detailed diagnostic output for every verified component
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_doctor.add_argument("--fix", action="store_true", help="Attempt to automatically repair detected issues")

def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``doctor`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    fix_mode = getattr(args, "fix", False)
    
    errors = 0
    warnings = 0

    print("Checking object database...")
    seen_objects = 0
    corrupt = set()
    all_shas = set()
    
    # Try importing read_object_safe if it exists
    try:
        from deep.storage.objects import read_object_safe
    except ImportError:
        read_object_safe = None

    if objects_dir.exists():
        from deep.storage.objects import walk_loose_shas
        for sha in walk_loose_shas(objects_dir):
            seen_objects += 1
            all_shas.add(sha)
            try:
                if read_object_safe:
                    obj = read_object_safe(objects_dir, sha)
                else:
                    obj = read_object(objects_dir, sha)
                        
                # Structural checks
                if isinstance(obj, Commit):
                    for p_sha in obj.parent_shas:
                        try: read_object(objects_dir, p_sha)
                        except:
                            print(Color.wrap(Color.RED, f"Error: Commit {sha[:7]} missing parent {p_sha[:7]}"))
                            errors += 1
                elif isinstance(obj, Tree):
                    for entry in obj.entries:
                        try: read_object(objects_dir, entry.sha)
                        except:
                            print(Color.wrap(Color.RED, f"Error: Tree {sha[:7]} missing entry {entry.sha[:7]}"))
                            errors += 1
            except ValueError as e:
                print(Color.wrap(Color.RED, f"Error: {e}"))
                corrupt.add(sha)
                errors += 1
            except Exception as e:
                print(Color.wrap(Color.RED, f"Error: Object {sha} failed to parse: {e}"))
                corrupt.add(sha)
                errors += 1

    print(f"Verified {seen_objects} objects.")
    
    print("Checking references...")
    for b in list_branches(dg_dir):
        sha = get_branch(dg_dir, b)
        if sha:
            try: read_object(objects_dir, sha)
            except:
                print(Color.wrap(Color.RED, f"Error: Branch '{b}' missing commit {sha[:7]}"))
                errors += 1
    
    head_sha = resolve_head(dg_dir)
    if head_sha:
        try: read_object(objects_dir, head_sha)
        except:
            print(Color.wrap(Color.RED, f"Error: HEAD missing commit {head_sha[:7]}"))
            errors += 1
    else:
        print(Color.wrap(Color.YELLOW, "Warning: HEAD is unborn or missing"))
        warnings += 1

    print("Checking index...")
    try:
        index = read_index(dg_dir)
        for path, entry in index.entries.items():
            try: read_object(objects_dir, entry.content_hash)
            except:
                print(Color.wrap(Color.RED, f"Error: Index '{path}' missing blob {entry.content_hash[:7]}"))
                errors += 1
    except Exception as e:
        print(Color.wrap(Color.RED, f"Error: Index read failure: {e}"))
        errors += 1

    print("Checking Pull Requests...")
    pm = PRManager(dg_dir)
    branches = list_branches(dg_dir)
    for pr in pm.list_prs():
        # Check branches
        if pr.head not in branches:
            print(Color.wrap(Color.RED, f"Error: PR #{pr.id} head branch '{pr.head}' missing"))
            errors += 1
        if pr.base not in branches:
            print(Color.wrap(Color.RED, f"Error: PR #{pr.id} base branch '{pr.base}' missing"))
            errors += 1
        
        # Check linked issue
        if pr.linked_issue:
            im = IssueManager(dg_dir)
            if not im.get_issue(pr.linked_issue):
                print(Color.wrap(Color.YELLOW, f"Warning: PR #{pr.id} linked to missing Issue #{pr.linked_issue}"))
                warnings += 1

    print("Checking Issues...")
    im = IssueManager(dg_dir)
    for issue in im.list_issues():
        # Check linked PRs
        for pr_id in issue.linked_prs:
            if not pm.get_pr(pr_id):
                print(Color.wrap(Color.YELLOW, f"Warning: Issue #{issue.id} linked to missing PR #{pr_id}"))
                warnings += 1
        
    reachable = mark_reachable(dg_dir)
    dangling = all_shas - reachable - corrupt
    
    if dangling:
        print(Color.wrap(Color.YELLOW, f"Warning: {len(dangling)} dangling objects found."))
        warnings += len(dangling)
        
    if fix_mode and (corrupt or dangling):
        print(Color.wrap(Color.CYAN, "\nApplying fixes..."))
        import time, shutil
        quarantine_dir = dg_dir / "quarantine" / str(int(time.time()))
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        from deep.storage.objects import _object_path

        for sha in corrupt:
            src = _object_path(objects_dir, sha, level=2)
            if not src.exists():
                src = _object_path(objects_dir, sha, level=1)
            
            already_quarantined = dg_dir / "quarantine" / sha
            
            if src.exists():
                shutil.move(src, quarantine_dir / f"{sha}_corrupt")
                print(Color.wrap(Color.GREEN, f"Fixed: Quarantined corrupt object {sha}"))
                errors -= 1
            elif already_quarantined.exists():
                shutil.move(already_quarantined, quarantine_dir / f"{sha}_corrupt")
                print(Color.wrap(Color.GREEN, f"Fixed: Quarantined corrupt object {sha}"))
                errors -= 1
        
        for sha in dangling:
            src = _object_path(objects_dir, sha, level=2)
            if not src.exists():
                src = _object_path(objects_dir, sha, level=1)
            if src.exists():
                shutil.move(src, quarantine_dir / sha)
                print(Color.wrap(Color.GREEN, f"Fixed: Quarantined dangling object {sha}"))
                warnings -= 1

    print()
    if errors == 0:
        print(Color.wrap(Color.GREEN, f"Repository consistent. {warnings} warnings."))
    else:
        print(Color.wrap(Color.RED, f"Integrity compromised. {errors} errors, {warnings} warnings."))
        raise DeepCLIException(1)


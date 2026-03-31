"""
deep.commands.fsck_cmd
~~~~~~~~~~~~~~~~~~~~~~~~
Verify the connectivity and validity of objects in the database.
"""

from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Set, Dict, List, Tuple, Optional, Any
from deep.utils.ux import DeepHelpFormatter, format_example


def setup_parser(subparsers: Any) -> None:
    """Set up the 'fsck' command parser."""
    subparsers.add_parser(
        "fsck",
        help="Verify the connectivity and validity of objects",
        description="Verifies the connectivity and validity of the objects in the Deep database.",
        epilog=f"""
Examples:
{format_example("deep fsck", "Verify database integrity")}
{format_example("deep fsck --unreachable", "Find objects not reachable from any ref")}
""",
        formatter_class=DeepHelpFormatter,
    )

def verify_object_integrity(objects_dir: Path, sha: str) -> bool:
    """Verify that a physical object file's content matches its SHA name."""
    import zlib
    import hashlib
    path = objects_dir / sha[:2] / sha[2:]
    if not path.exists():
        return False
    
    try:
        data = path.read_bytes()
        try:
            raw = zlib.decompress(data)
        except zlib.error:
            raw = data
            
        actual_sha = hashlib.sha1(raw).hexdigest()
        return actual_sha == sha
    except Exception:
        return False

def run(args):
    # Defer imports to avoid circularity
    from deep.core.repository import find_repo, DEEP_DIR
    from deep.storage.objects import read_object, Commit, Tree, Blob
    from deep.core.refs import list_branches, list_tags, resolve_head, get_branch, get_tag
    from rich.console import Console

    console = Console()
    repo_root = find_repo(Path.cwd())
    if not repo_root:
        console.print("[red]Deep: error: not a Deep repository[/red]")
        return
    
    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    # 1. Verify integrity of all physical files
    console.print("[bold blue]Verifying object integrity...[/bold blue]")
    all_shas: Set[str] = set()
    corrupt_objects: List[str] = []
    
    if not objects_dir.exists():
        console.print("[yellow]Empty repository (no objects).[/yellow]")
        return

    for xx_dir in objects_dir.iterdir():
        if not xx_dir.is_dir() or len(xx_dir.name) != 2:
            continue
        for yy_file in xx_dir.iterdir():
            sha = xx_dir.name + yy_file.name
            all_shas.add(sha)
            if not verify_object_integrity(objects_dir, sha):
                corrupt_objects.append(sha)
    
    if corrupt_objects:
        console.print(f"[bold red]Found {len(corrupt_objects)} corrupt objects![/bold red]")
        for sha in corrupt_objects:
            console.print(f"  corrupt: {sha}")
    else:
        console.print(f"Checked {len(all_shas)} objects, 0 corruption.")

    # 2. Connectivity check from all refs
    console.print("\n[bold blue]Checking connectivity...[/bold blue]")
    reachable: Set[str] = set()
    missing: Set[str] = set()
    
    # Entry points
    heads = set()
    for b in list_branches(dg_dir):
        sha = get_branch(dg_dir, b)
        if sha: heads.add(sha)
    for t in list_tags(dg_dir):
        sha = get_tag(dg_dir, t)
        if sha: heads.add(sha)
    head_sha = resolve_head(dg_dir)
    if head_sha: heads.add(head_sha)
    
    stack = list(heads)
    while stack:
        sha = stack.pop()
        if sha in reachable:
            continue
        
        try:
            obj = read_object(objects_dir, sha)
            reachable.add(sha)
            
            if isinstance(obj, Commit):
                if obj.parent_shas:
                    stack.extend(obj.parent_shas)
                if obj.tree_sha:
                    stack.append(obj.tree_sha)
            elif isinstance(obj, Tree):
                for entry in obj.entries:
                    stack.append(entry.sha)
            # Blobs have no children
        except Exception:
            missing.add(sha)
            console.print(f"[red]Missing object: {sha}[/red]")
            
    if not missing:
        console.print("Connectivity OK.")
    
    # 3. Find dangling objects
    dangling = all_shas - reachable
    if dangling:
        console.print(f"\n[yellow]Found {len(dangling)} dangling objects (unreachable from any ref):[/yellow]")
        # Only show first 5 to avoid spam
        for sha in sorted(list(dangling))[:5]:
            console.print(f"  dangling: {sha}")
        if len(dangling) > 5:
            console.print(f"  ... and {len(dangling) - 5} more.")
    
    if not corrupt_objects and not missing:
        console.print("\n[bold green]Fsck complete. Repository is healthy.[/bold green]")
    else:
        console.print("\n[bold red]Fsck complete. Repository has ISSUES.[/bold red]")

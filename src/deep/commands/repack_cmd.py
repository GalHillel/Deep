"""
deep.commands.repack_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Repack loose objects into packfiles and generate reachability bitmaps.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException
import sys
from pathlib import Path
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'repack' command parser."""
    p_repack = subparsers.add_parser(
        "repack",
        help="Pack detached objects into a packfile",
        description=format_description("Deep Repack optimizes the object database by aggregating loose objects into highly compressed packfiles. It also generates reachability bitmaps to ultra-accelerate network transfers and revision traversal."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep repack", "Repack all loose objects and generate optimized bitmaps")}
{format_example("deep repack --no-bitmaps", "Perform repacking without bitmap generation")}
{format_example("deep repack --aggressive", "Perform a resource-intensive, high-compression repack")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_repack.add_argument("--no-bitmaps", dest="bitmaps", action="store_false", help="Disable reachability bitmap generation")

def run(args):
    from deep.core.repository import find_repo, DEEP_DIR
    from deep.storage.pack import PackWriter
    from deep.storage.bitmap import generate_pack_bitmaps
    from deep.storage.objects import get_reachable_objects
    from deep.core.refs import list_branches, list_tags, resolve_head, get_branch, get_tag
    from deep.storage.transaction import TransactionManager
    
    console = Console()
    repo_root = find_repo(Path.cwd())
    if not repo_root:
        console.print("[red]Error: not a deep repository[/red]")
        raise DeepCLIException(1)
        
    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    with TransactionManager(dg_dir) as tm:
        tm.begin("repack")
        console.print("[bold blue]Repacking repository objects...[/bold blue]")
        
        # 1. Identify all reachable SHAs
        heads = set()
        for b in list_branches(dg_dir):
            sha = get_branch(dg_dir, b)
            if sha: heads.add(sha)
        for t in list_tags(dg_dir):
            sha = get_tag(dg_dir, t)
            if sha: heads.add(sha)
        head_sha = resolve_head(dg_dir)
        if head_sha: heads.add(head_sha)
        
        if not heads:
            console.print("[yellow]Nothing to repack (no commits).[/yellow]")
            return
            
        reachable_shas = get_reachable_objects(objects_dir, list(heads))
        console.print(f"Found {len(reachable_shas)} reachable objects.")
        
        # 2. Write new packfile
        pw = PackWriter(dg_dir)
        pack_sha, idx_sha = pw.create_pack(reachable_shas)
        console.print(f"[green]Created pack-{pack_sha}.pack[/green]")
        
        # 3. Generate bitmaps
        if getattr(args, "bitmaps", True):
            console.print("[bold blue]Generating reachability bitmaps...[/bold blue]")
            num_bm = generate_pack_bitmaps(dg_dir, pack_sha)
            console.print(f"[green]Generated bitmaps for {num_bm} commits.[/green]")
            
        tm.commit()
        console.print("[bold green]Repack complete.[/bold green]")

"""
deep.commands.repack_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Repack loose objects into packfiles and generate reachability bitmaps.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException
import sys
from pathlib import Path
from rich.console import Console

def run(args) -> None:
    from deep.core.repository import find_repo, DEEP_DIR
    from deep.storage.pack import PackWriter
    from deep.storage.bitmap import generate_pack_bitmaps
    from deep.storage.objects import get_reachable_objects
    from deep.core.refs import list_branches, list_tags, resolve_head, get_branch, get_tag
    from deep.storage.transaction import TransactionManager
    
    console = Console()
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        console.print(f"[red]Deep: error: {exc}[/red]")
        raise DeepCLIException(1)
        
    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"
    
    # Flag check: --no-bitmaps sets 'bitmaps' to False via action="store_false"
    bitmaps_enabled = getattr(args, "bitmaps", True)
    
    with TransactionManager(dg_dir) as tm:
        tm.begin("repack")
        console.print("[bold blue]⚓️ Repacking repository objects...[/bold blue]")
        
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
            console.print("[yellow]⚓️ Nothing to repack (no commits found).[/yellow]")
            return
            
        try:
            reachable_shas = get_reachable_objects(objects_dir, list(heads))
            console.print(f"Found [yellow]{len(reachable_shas)}[/yellow] reachable objects.")
            
            # 2. Write new packfile
            pw = PackWriter(dg_dir)
            pack_sha, idx_sha = pw.create_pack(reachable_shas)
            console.print(f"[green]⚓️ Created pack-{pack_sha}.pack[/green]")
            
            # 3. Generate bitmaps
            if bitmaps_enabled:
                console.print("[bold blue]⚓️ Generating reachability bitmaps...[/bold blue]")
                num_bm = generate_pack_bitmaps(dg_dir, pack_sha)
                console.print(f"[green]⚓️ Generated bitmaps for {num_bm} commits.[/green]")
            else:
                console.print("[yellow]⚓️ Bitmap generation disabled by user flag.[/yellow]")
                
            tm.commit()
            console.print("[bold green]⚓️ Repack complete. Object database optimized.[/bold green]")
            
        except Exception as e:
            console.print(f"[red]Deep: error: Object optimization failed: {e}[/red]")
            raise DeepCLIException(1)

if __name__ == "__main__":
    pass

"""
deep.commands.commit_graph_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Manage the commit-graph index.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException
import sys
from pathlib import Path
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'commit-graph' command parser."""
    p_cg = subparsers.add_parser(
        "commit-graph",
        help="Write and verify the commit-graph file",
        description="Manage the commit-graph binary index to accelerate history walks and generation counting.",
        epilog=f"""
Examples:
{format_example("deep commit-graph write", "Regenerate the commit-graph index")}
{format_example("deep commit-graph verify", "Verify the integrity of the commit-graph index")}
""",
        formatter_class=DeepHelpFormatter,
    )
    csub = p_cg.add_subparsers(dest="cg_command", metavar="ACTION")
    csub.add_parser("write", help="Regenerate the commit-graph binary index")
    csub.add_parser("verify", help="Verify the checksum and structure of the commit-graph index")
    csub.add_parser("clear", help="Remove the commit-graph index file")

def run(args):
    from deep.core.repository import find_repo
    from deep.storage.commit_graph import build_history_graph, DeepHistoryGraph
    
    console = Console()
    repo_root = find_repo(Path.cwd())
    if not repo_root:
        console.print("[red]Deep: error: not a Deep repository[/red]")
        raise DeepCLIException(1)
        
    from deep.core.constants import DEEP_DIR
    dg_dir = repo_root / DEEP_DIR
    
    if args.cg_command == "write":
        console.print("[bold blue]Generating commit-graph index...[/bold blue]")
        num = build_history_graph(dg_dir)
        if num > 0:
            console.print(f"[bold green]Success: Created index for {num} commits.[/bold green]")
        else:
            console.print("[yellow]No commits found to index.[/yellow]")
            
    elif args.cg_command == "verify":
        console.print("[bold blue]Verifying commit-graph index...[/bold blue]")
        cg = DeepHistoryGraph(dg_dir)
        if not cg.load():
            console.print("[red]Deep: error: Could not load commit-graph or it does not exist.[/red]")
            return
            
        # Verify a sample
        if cg._oids:
            console.print(f"Index loaded correctly with {len(cg._oids)} commits.")
        else:
            console.print("[yellow]Index is empty.[/yellow]")
            
    elif args.cg_command == "clear":
        cg_path = dg_dir / "objects" / "info" / "commit-graph"
        if cg_path.exists():
            cg_path.unlink()
            console.print("[green]Commit-graph deleted.[/green]")
        else:
            console.print("[yellow]No commit-graph found to delete.[/yellow]")

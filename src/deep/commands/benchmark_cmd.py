"""
deep.commands.benchmark_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep benchmark`` massive-scale command implementation.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from deep.core.benchmark import run_benchmarks
from deep.utils.ux import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the massive-scale ``benchmark`` command."""
    print(Color.wrap(Color.CYAN, "⚓️ Initializing Massive Performance Engine..."))
    print(Color.wrap(Color.YELLOW, "⚓️ Stress-testing: 10,000 files, 1,000 commits. (Stand by)..."))
    
    results = run_benchmarks(
        verbose=getattr(args, "verbose", False),
        compare_git=False # Legacy removed as per performance engineering mode
    )
    
    if getattr(args, "report", False):
        report_path = Path("benchmark_report.json")
        with open(report_path, "w") as f:
            json.dump(results, f, indent=4)
        print(f"⚓️ Report saved to {Color.wrap(Color.GREEN, str(report_path))}")

    print()
    print(f"{Color.wrap(Color.BOLD, '--- MASSIVE SCALE PERFORMANCE REPORT ---')}")
    
    # Indexing Metrics
    print(f"{Color.wrap(Color.BLUE, 'Deep Graphics Index Engine:')}")
    print(f"  Indexed 10,000 files in {results['index_add_10k_time']:.4f} seconds ({results['index_add_10k_throughput']:.2f} files/sec)")
    
    # Tree/Commit Metrics
    print(f"{Color.wrap(Color.BLUE, 'Massive Object Commits:')}")
    print(f"  Committed 10,000-file tree in {results['commit_10k_tree_time']:.4f} seconds ({results['commit_10k_throughput']:.2f} entries/sec)")
    
    # Status Scanning
    print(f"{Color.wrap(Color.BLUE, 'Status Scan Engine (Worker Parallelism):')}")
    status_color = Color.SUCCESS if results.get("status_detected") else Color.RED
    status_txt = "DETECTED" if results.get("status_detected") else "FAILED"
    print(f"  Scan 10,000-index vs worktree in {results['status_scan_10k_time']:.4f} seconds (1 modification {Color.wrap(status_color, status_txt)})")

    # DAG Traversal
    if "log_1k_traversal_time" in results:
        print(f"{Color.wrap(Color.BLUE, 'DAG History Traversal:')}")
        traversal_throughput = results["log_1k_count"] / results["log_1k_traversal_time"]
        print(f"  Traversed 1,000 commits in {results['log_1k_traversal_time']:.4f} seconds ({traversal_throughput:.2f} commits/sec)")

    print()
    print(f"⚓️ {Color.wrap(Color.SUCCESS, 'Benchmark complete. System stable at scale.')}")

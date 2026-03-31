"""
deep.commands.benchmark_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep benchmark`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from deep.core.benchmark import run_benchmarks
from deep.utils.ux import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``benchmark`` command."""
    compare_git = getattr(args, "compare_git", False)
    
    print(Color.wrap(Color.CYAN, "Running Deep Performance Benchmarks..."))
    if compare_git:
        print(Color.wrap(Color.YELLOW, "Comparing against native Deep... (This will take longer)"))
    
    results = run_benchmarks(
        verbose=getattr(args, "verbose", False),
        compare_git=compare_git
    )
    
    if getattr(args, "report", False):
        import json
        report_path = Path("benchmark_report.json")
        with open(report_path, "w") as f:
            json.dump(results, f, indent=4)
        print(f"Report saved to {Color.wrap(Color.GREEN, str(report_path))}")

    print()
    print(f"{Color.wrap(Color.BOLD, '--- RESULTS ---')}")
    
    # Deep Metrics
    print(f"{Color.wrap(Color.BLUE, 'Deep:')}")
    print(f"  Blob Hashing: {results['deep_blob_total_time']:.4f}s ({results['deep_blob_throughput']:.2f} obj/s)")
    print(f"  Commit Speed: {results['deep_commit_avg_time']*1000:.2f}ms/commit")
    
    if "deep" in results:
        g = results["deep"]
        print()
        print(f"{Color.wrap(Color.BLUE, 'Native Deep:')}")
        print(f"  Commit Speed: {g['commit_avg_time']*1000:.2f}ms/commit")
        
        ratio = results['deep_commit_avg_time'] / g['commit_avg_time']
        color = Color.GREEN if ratio < 1.2 else Color.RED
        print(f"  Performance Ratio: {Color.wrap(color, f'{ratio:.2f}')} (lower is better for Deep)")

    print()
    print(Color.wrap(Color.GREEN, "Benchmark complete."))

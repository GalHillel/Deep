"""
deep.commands.benchmark_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep benchmark`` command implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from deep.core.benchmark import run_benchmarks
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description, Color
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'benchmark' command parser."""
    p_bench = subparsers.add_parser(
        "benchmark",
        help="Measure performance of core operations",
        description=format_description("Deep Benchmark runs a comprehensive performance suite against the current repository. It measures the throughput of object hashing, commit creation speed, the efficiency of the history graph traversal, and provides comparative analysis against native Deep implementations."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep benchmark", "Run the standard performance suite and display summary results")}
{format_example("deep benchmark --verbose", "Show live metrics for every operation during the benchmark")}
{format_example("deep benchmark --compare-git", "Compare current performance against native Deep standards")}
{format_example("deep benchmark --report", "Generate a detailed JSON report (benchmark_report.json)")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_bench.add_argument("--verbose", action="store_true", help="Show detailed metrics during benchmarking")
    p_bench.add_argument("--report", action="store_true", help="Save results to benchmark_report.json")
    p_bench.add_argument("--compare-git", action="store_true", help="Compare performance against native Deep implementation")


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

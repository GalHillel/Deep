"""
deep_git.commands.benchmark_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit benchmark`` command implementation.
"""

from __future__ import annotations

import sys
from deep_git.core.benchmark import run_benchmarks
from deep_git.core.utils import Color


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``benchmark`` command."""
    print(Color.wrap(Color.CYAN, "Running Deep Git Performance Benchmarks..."))
    print(Color.wrap(Color.DIM, "(This may take a few seconds)"))
    
    results = run_benchmarks(verbose=getattr(args, "verbose", False))
    
    print()
    print(f"{Color.wrap(Color.BOLD, '--- RESULTS ---')}")
    
    # Blobs
    print(f"{Color.wrap(Color.BLUE, 'Blob Hashing/Compression:')}")
    print(f"  Total time: {results['blob_total_time']:.4f}s")
    print(f"  Throughput: {results['blob_throughput']:.2f} objects/sec")
    
    # Commits
    print(f"{Color.wrap(Color.BLUE, 'Commit Creation:')}")
    print(f"  Total time: {results['commit_total_time']:.4f}s")
    print(f"  Avg time:   {results['commit_avg_time']*1000:.2f}ms per commit")
    
    # Index
    print(f"{Color.wrap(Color.BLUE, 'Index Management:')}")
    print(f"  Write time: {results['index_write_time']:.4f}s for {results['index_file_count']} files")
    
    print()
    print(Color.wrap(Color.GREEN, "Benchmark complete."))

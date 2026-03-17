"""
deep.commands.pipeline_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep pipeline`` command implementation.

Commands:
  pipeline run [--commit <sha>] - Trigger a pipeline run.
  pipeline status <run_id>     - Check status of a run.
  pipeline list                - List all recent runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.repository import DEEP_DIR, find_repo
from deep.core.pipeline import PipelineRunner
from deep.core.refs import resolve_head


def run(args) -> None:
    """Execute the ``pipeline`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    runner = PipelineRunner(dg_dir)
    cmd = getattr(args, "pipe_command", None) or getattr(args, "pipeline_command", None) or "list"

    if cmd == "run":
        sha = args.commit or resolve_head(dg_dir)
        if not sha:
            print("DeepGit: error: No commit specified and HEAD not resolved.", file=sys.stderr)
            sys.exit(1)
        
        pipeline_run = runner.create_run(sha)
        print(f"🚀 Triggered pipeline run: {pipeline_run.run_id}")
        runner.run_pipeline(pipeline_run)
        print(f"Done. Status: {pipeline_run.status}")

    elif cmd == "status":
        run_id = args.run_id
        runs = runner.list_runs()
        match = [r for r in runs if r.run_id == run_id]
        if not match:
            print(f"DeepGit: error: Run '{run_id}' not found.", file=sys.stderr)
            sys.exit(1)
        
        r = match[0]
        print(f"Run: {r.run_id} | Status: {r.status} | Commit: {r.commit_sha[:7]}")
        for job in r.jobs:
            print(f"  - {job.name:20} [{job.status:8}] {job.duration:.2f}s")
            if job.status == "failed" and job.output:
                print(f"    Error: {job.output[:100]}...")

    elif cmd == "list":
        runs = runner.list_runs()
        if not runs:
            print("No pipeline runs found.")
            return
            
        print(f"{'Run ID':\u003c20} {'Status':\u003c10} {'Commit':\u003c10} {'Start Time'}")
        print("-" * 60)
        import datetime
        for r in runs[:10]:
            dt = datetime.datetime.fromtimestamp(r.start_time).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{r.run_id:\u003c20} {r.status:\u003c10} {r.commit_sha[:7]:\u003c10} {dt}")

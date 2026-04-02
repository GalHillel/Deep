"""
deep.commands.pipeline_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep pipeline`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import time
import datetime
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.pipeline import PipelineRunner
from deep.core.refs import resolve_head
from deep.utils.ux import Color, print_error, print_success, print_info
import deep.utils.network as net

def get_description() -> str:
    return """Local-First CI/CD Pipeline Engine.

Manage, trigger, and monitor build/test pipelines locally.
Optionally synchronize with GitHub Actions for cloud-based verification.
"""

def get_epilog() -> str:
    return """\033[1mEXAMPLES:\033[0m

  \033[1;34m⚓️ deep pipeline list\033[0m
     Display all localized pipeline runs, their status, and durations.

  \033[1;34m⚓️ deep pipeline trigger\033[0m
     Initiate a new local pipeline execution for the current HEAD commit.

  \033[1;34m⚓️ deep pipeline status 5\033[0m
     Show a detailed report for pipeline run #5, including job-level outputs.

  \033[1;34m⚓️ deep pipeline sync\033[0m
     Fetch and synchronize remote workflow statuses from GitHub Actions.

\033[1;33m💡 SETUP TOKEN:\033[0m
  # Windows (PowerShell/CMD):
  $env:GH_TOKEN="..."  # PowerShell
  set GH_TOKEN=...      # CMD

  # Linux / macOS (Zsh/Bash):
  export GH_TOKEN="..."

\033[1;31m⚠️  NOTE:\033[0m 'sync' requires a GitHub remote and GH_TOKEN/DEEP_TOKEN.
      Without these, all operations remain local-only.
"""


def run(args) -> None:
    """Execute the ``pipeline`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print_error(f"{exc}")
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    runner = PipelineRunner(dg_dir)
    verbose = getattr(args, "verbose", False)
    
    cmd = getattr(args, "pipe_command", None) or "list"
    
    if cmd in ("run", "trigger"):
        sha = getattr(args, "commit", None) or resolve_head(dg_dir)
        if not sha:
            print_error("No commit specified and HEAD not resolved.")
            raise DeepCLIException(1)
        
        pipeline_run = runner.create_run(sha)
        print_info(f"🚀 Triggering pipeline run locally: {pipeline_run.run_id}")
        runner.run_pipeline(pipeline_run)
        print_success(f"Pipeline complete. Status: {pipeline_run.status.upper()}")

    elif cmd == "status":
        run_id = getattr(args, "id", None)
        runs = runner.list_runs()
        
        if not run_id:
            # No run_id provided: show latest run if available
            if not runs:
                print_error("No pipeline runs found.")
                raise DeepCLIException(1)
            r = runs[-1]
            run_id = r.run_id
            match = [r]
        else:
            match = [r for r in runs if r.run_id == run_id]
        
        if not match:
            print_error(f"Run '{run_id}' not found locally.")
            raise DeepCLIException(1)
        
        r = match[0]
        status_col = Color.GREEN if r.status == "success" else (Color.RED if r.status == "failed" else Color.YELLOW)
        
        print(Color.wrap(Color.CYAN, f"\nPipeline Run: {r.run_id}"))
        print(Color.wrap(Color.CYAN, "-" * 65))
        print(f"Status:   {Color.wrap(status_col, r.status.upper())}")
        print(f"Commit:   {r.commit_sha[:7]}")
        if r.github_run_id:
            print(f"GitHub:   Run ID #{r.github_run_id}")
        
        print(f"\n{Color.wrap(Color.BOLD, 'Jobs:')}")
        for job in r.jobs:
            job_col = Color.GREEN if job.status == "success" else (Color.RED if job.status == "failed" else Color.DIM)
            print(f"  - {job.name:20} [{Color.wrap(job_col, job.status.upper()):18}] {job.duration:.2f}s")
            if job.status == "failed" and job.output:
                print(f"    Error: {job.output[:150]}...")
        print("")

    elif cmd == "list":
        runs = runner.list_runs()
        print(Color.wrap(Color.CYAN, f"\nRepository: {repo_root}"))
        print(Color.wrap(Color.CYAN, f"Recent Pipeline Runs: {len(runs)} total\n"))
        
        if not runs:
            print("No pipeline runs found.")
            return
            
        print(f"{'Run ID':<20} {'Status':<10} {'Commit':<10} {'Start Time'}")
        print("-" * 65)
        for r in runs[:10]:
            dt = datetime.datetime.fromtimestamp(r.start_time).strftime("%Y-%m-%d %H:%M:%S")
            status_col = Color.GREEN if r.status == "success" else (Color.RED if r.status == "failed" else Color.YELLOW)
            print(f"{r.run_id:<20} {Color.wrap(status_col, r.status.upper()):<10} {r.commit_sha[:7]:<10} {dt}")

    elif cmd == "sync":
        gh_repo = net.get_github_remote(repo_root)
        token = net.get_token()
        
        if not gh_repo or not token:
            print_error("Sync requires a GitHub remote and GH_TOKEN.")
            raise DeepCLIException(1)
            
        print_info(f"Checking for remote runs on {gh_repo}...")
        path = f"{gh_repo}/actions/runs"
        res = net.api_request(path, verbose=verbose)
        
        if res and isinstance(res, dict) and "workflow_runs" in res:
            remote_runs = res["workflow_runs"]
            print_success(f"Found {len(remote_runs)} remote runs on GitHub.")
        else:
            print_error("Failed to fetch remote pipeline runs.")

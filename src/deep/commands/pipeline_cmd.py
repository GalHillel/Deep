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
    """Return a color-coded description for the pipeline command."""
    return "Manage CI/CD pipelines locally and optionally sync with GitHub Actions."

def get_epilog() -> str:
    """Return a color-coded epilog with usage examples."""
    examples_title = Color.wrap(Color.CYAN, "Examples:")
    note_title = Color.wrap(Color.RED, "Note:")
    
    list_ex    = f"  {Color.wrap(Color.YELLOW, 'deep pipeline list')}      {Color.wrap(Color.GREEN, '# List all local pipeline runs')}"
    trigger_ex = f"  {Color.wrap(Color.YELLOW, 'deep pipeline trigger')}   {Color.wrap(Color.GREEN, '# Trigger a new local pipeline run')}"
    status_ex  = f"  {Color.wrap(Color.YELLOW, 'deep pipeline status 5')}  {Color.wrap(Color.GREEN, '# Show status for run #5')}"
    sync_ex    = f"  {Color.wrap(Color.YELLOW, 'deep pipeline sync')}      {Color.wrap(Color.GREEN, '# Sync local runs with GitHub Actions')}"
    
    token_ex  = f"\n{Color.wrap(Color.CYAN, 'Setup Token (Windows):')}\n" \
                f"  {Color.wrap(Color.YELLOW, '$env:GH_TOKEN=\"...\"')}  {Color.wrap(Color.GREEN, '# PowerShell')}\n" \
                f"  {Color.wrap(Color.YELLOW, 'set GH_TOKEN=...')}      {Color.wrap(Color.GREEN, '# CMD')}"

    sync_note = f"\n{note_title} 'sync' requires a GitHub remote and GH_TOKEN/DEEP_TOKEN. \n      Without these, all operations remain local-only."
    
    return f"\n{examples_title}\n{list_ex}\n{trigger_ex}\n{status_ex}\n{sync_ex}\n{token_ex}\n{sync_note}\n"

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
    
    cmd = getattr(args, "pipe_command", None) or getattr(args, "pipeline_command", None) or "list"
    
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
        run_id = getattr(args, "id", None) or getattr(args, "run_id", None)
        if not run_id:
            print_error("Missing run ID.")
            raise DeepCLIException(1)
            
        runs = runner.list_runs()
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

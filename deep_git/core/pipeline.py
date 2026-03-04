"""
deep_git.core.pipeline
~~~~~~~~~~~~~~~~~~~~~~
CI/CD Pipeline runner for Deep Git.

Loads pipeline definitions from `.deep_git/pipelines/*.json` or `.deep_git/pipeline.json`
and executes them sequentially or in parallel.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class PipelineJob:
    name: str
    command: str
    status: str = "pending"  # pending, running, success, failed
    duration: float = 0.0
    output: str = ""


@dataclass
class PipelineRun:
    run_id: str
    commit_sha: str
    jobs: List[PipelineJob] = field(default_factory=list)
    status: str = "pending"
    start_time: float = field(default_factory=time.time)


class PipelineRunner:
    """Executes CI/CD pipelines defined in the repository."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.runs_dir = dg_dir / "pipelines" / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> List[Dict]:
        """Load pipeline configuration from .deep_git/pipeline.json."""
        config_path = self.dg_dir / "pipeline.json"
        if not config_path.exists():
            return []
        try:
            return json.loads(config_path.read_text())
        except Exception:
            return []

    def create_run(self, commit_sha: str) -> PipelineRun:
        config = self.load_config()
        run_id = f"run_{int(time.time())}_{commit_sha[:7]}"
        
        # Handle dict or list config
        if isinstance(config, dict):
            job_list = config.get("jobs", [])
        else:
            job_list = config
            
        jobs = [PipelineJob(name=j["name"], command=j["command"]) for j in job_list]
        run = PipelineRun(run_id=run_id, commit_sha=commit_sha, jobs=jobs)
        self.save_run(run)
        return run

    def save_run(self, run: PipelineRun):
        path = self.runs_dir / f"{run.run_id}.json"
        with open(path, "w") as f:
            json.dump(asdict_deep(run), f, indent=2)

    def run_pipeline(self, run: PipelineRun, env: Optional[Dict] = None):
        """Execute all jobs in the pipeline run."""
        run.status = "running"
        self.save_run(run)
        
        all_success = True
        for job in run.jobs:
            job.status = "running"
            self.save_run(run)
            
            start = time.time()
            try:
                # Execute the job command
                result = subprocess.run(
                    job.command,
                    shell=True,
                    cwd=self.dg_dir.parent,
                    env=env or os.environ,
                    capture_output=True,
                    text=True
                )
                job.output = result.stdout + result.stderr
                if result.returncode == 0:
                    job.status = "success"
                else:
                    job.status = "failed"
                    all_success = False
            except Exception as e:
                job.status = "failed"
                job.output = str(e)
                all_success = False
            
            job.duration = time.time() - start
            self.save_run(run)
            
        run.status = "success" if all_success else "failed"
        self.save_run(run)

    def list_runs(self) -> List[PipelineRun]:
        runs = []
        for p in self.runs_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                # Reconstruct PipelineRun
                jobs = []
                for j in data.get("jobs", []):
                    # Ensure all required keys exist for PipelineJob
                    job_data = {"name": j["name"], "command": j["command"]}
                    if "status" in j: job_data["status"] = j["status"]
                    if "duration" in j: job_data["duration"] = j["duration"]
                    if "output" in j: job_data["output"] = j["output"]
                    jobs.append(PipelineJob(**job_data))
                
                run = PipelineRun(
                    run_id=data["run_id"],
                    commit_sha=data["commit_sha"],
                    jobs=jobs,
                    status=data["status"],
                    start_time=data["start_time"]
                )
                runs.append(run)
            except Exception:
                continue
        return sorted(runs, key=lambda x: x.start_time, reverse=True)

    def cascade_to_dependents(self, commit_sha: str):
        """Trigger pipelines in sibling repos that depend on this one."""
        repo_name = self.dg_dir.parent.name
        parent_dir = self.dg_dir.parent.parent
        
        cascaded = []
        for sibling in parent_dir.iterdir():
            if sibling.is_dir() and sibling.name != repo_name:
                sib_dg = sibling / ".deep_git"
                if sib_dg.exists():
                    sib_runner = PipelineRunner(sib_dg)
                    sib_config = sib_runner.load_config()
                    # Check if sibling depends on us (simulated check)
                    # In a real system, pipeline.json would have "depends_on": ["repo_name"]
                    if any(dep.get("repo") == repo_name for dep in sib_config.get("dependencies", [])):
                        run = sib_runner.create_run(f"cascade_from_{repo_name}_{commit_sha[:7]}")
                        threading.Thread(target=sib_runner.run_pipeline, args=(run,), daemon=True).start()
                        cascaded.append(sibling.name)
        return cascaded

import threading


def asdict_deep(obj):
    if isinstance(obj, list):
        return [asdict_deep(i) for i in obj]
    if hasattr(obj, "__dict__"):
        return {k: asdict_deep(v) for k, v in obj.__dict__.items()}
    return obj

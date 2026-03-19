"""
deep.core.pipeline
~~~~~~~~~~~~~~~~~~~~~~
CI/CD Pipeline runner for Deep.

Loads pipeline definitions from `.deep/pipelines/*.json` or `.deep/pipeline.json`
and executes them sequentially or in parallel.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import threading
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from deep.core.constants import DEEP_DIR
from typing import Dict, List, Optional, Any


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
        """Load pipeline configuration from .deepci.yml or .deep/pipeline.json."""
        # Try .deepci.yml first
        yml_path = self.dg_dir.parent / ".deepci.yml"
        if yml_path.exists():
            try:
                data = yaml.safe_load(yml_path.read_text())
                if isinstance(data, dict) and "jobs" in data:
                    return data["jobs"]
                return []
            except Exception:
                pass

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
        """Execute all jobs in the pipeline run using SandboxRunner."""
        run.status = "running"
        self.save_run(run)
        
        from deep.core.security import SandboxRunner
        # Allowed write paths: tmp and wal
        allowed = [self.dg_dir / "tmp", self.dg_dir / "wal"]
        (self.dg_dir / "tmp").mkdir(exist_ok=True)
        
        all_success = True
        for job in run.jobs:
            job.status = "running"
            self.save_run(run)
            
            # Use SandboxRunner. Since it expects a script, we'll write a temporary wrapper
            # if the job is a shell command, or run it directly if it's a script.
            runner = SandboxRunner(self.dg_dir, allowed_write_paths=allowed)
            
            # Simple hack: write command to a temp .py or .sh script
            # For now, let's assume jobs are python-compatible or simple shell wrappers
            # We'll stick to a simple subprocess for now but wrap it in sandbox context if possible
            # Actually, let's just use SandboxRunner as it was intended.
            
            start = time.time()
            try:
                # Use subprocess.run for safer execution than os.system
                # We still allow shell-like behavior within the sandbox for CI jobs,
                # but the environment (PATH) is now hardened in SandboxRunner.
                script_body = f"""
import subprocess
import sys
import os
import shlex

cmd = {repr(job.command)}
try:
    # Use shlex.split and shell=False to prevent RCE.
    # We no longer support shell features (pipes/redirects) directly in the command string
    # for security reasons. Users should use scripts if they need complex logic.
    parsed_cmd = shlex.split(cmd)
    
    # On Windows, 'echo' and other built-ins are not executables. 
    # To support them safely without shell=True for everything, 
    # we prepend cmd /c if the executable is not found.
    import shutil
    if os.name == 'nt' and shutil.which(parsed_cmd[0]) is None:
        parsed_cmd = ["cmd", "/c"] + parsed_cmd
        
    res = subprocess.run(parsed_cmd, shell=False, capture_output=False)
    sys.exit(res.returncode)
except Exception as e:
    print(f"Pipeline Execution Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
                temp_script = self.dg_dir / "tmp" / f"job_{job.name}.py"
                temp_script.write_text(script_body.strip())
                
                res = runner.run(temp_script, timeout=60, cwd=self.dg_dir.parent)
                job.output = res.stdout + res.stderr
                if res.exit_code == 0 and not res.timed_out:
                    job.status = "success"
                else:
                    job.status = "failed"
                    all_success = False
                
                # Cleanup
                if temp_script.exists():
                    temp_script.unlink()
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
                sib_dg = sibling / DEEP_DIR
                if sib_dg.exists():
                    sib_runner = PipelineRunner(sib_dg)
                    sib_config = sib_runner.load_config()
                    # Check if sibling depends on us (simulated check)
                    # In a real system, pipeline.json would have "depends_on": ["repo_name"]
                    if isinstance(sib_config, dict):
                        deps = sib_config.get("dependencies", [])
                    else:
                        deps = [] # fallback if list
                        
                    if any(dep.get("repo") == repo_name for dep in deps):
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

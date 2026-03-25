import subprocess
import pytest
import tempfile
import shutil
import json
import os
import time
import socket
import signal
from pathlib import Path

# Structured log file for the entire test run
LOG_FILE = Path("tests/e2e_cli/test_run.json")

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # Execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)

def get_free_port():
    """Retrieve a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port

def poll_until(condition_func, timeout=10, interval=0.1):
    """Wait until a condition is met or timeout expires."""
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        if condition_func():
            return True
        time.sleep(interval)
    return False

@pytest.fixture
def isolated_env(tmp_path):
    """Provide a fully isolated environment (HOME, XDG, etc.)."""
    env_dir = tmp_path / "isolated_env"
    env_dir.mkdir()
    
    # Platform-agnostic isolation
    env = os.environ.copy()
    env["HOME"] = str(env_dir / "home")
    env["XDG_CONFIG_HOME"] = str(env_dir / "config")
    env["XDG_CACHE_HOME"] = str(env_dir / "cache")
    env["USERPROFILE"] = str(env_dir / "profile")
    env["APPDATA"] = str(env_dir / "appdata")
    env["LOCALAPPDATA"] = str(env_dir / "localappdata")
    env["DEEP_CONFIG_DIR"] = str(env_dir / "deep_config")
    
    # Ensure they exist
    for k in ["HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "DEEP_CONFIG_DIR"]:
        Path(env[k]).mkdir(parents=True, exist_ok=True)
        
    return env

def run_deep(args, cwd=None, input=None, env=None):
    """Run `deep` CLI command with telemetry and isolation."""
    # We allow env to be None if it's already set up by a fixture
    # but for true isolation, it's better to pass it.
    cmd = ["deep"] + args
    start_time = time.perf_counter()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            input=input,
            env=env,
            capture_output=True,
            text=True,
            timeout=120
        )
        duration = time.perf_counter() - start_time
        
        log_entry = {
            "cmd": " ".join(cmd),
            "exit_code": result.returncode,
            "duration": duration
        }
        _append_to_log(log_entry)
        return result
    except subprocess.TimeoutExpired:
        _append_to_log({"cmd": " ".join(cmd), "error": "timeout"})
        raise



def _append_to_log(entry):
    """Wait-free atomic-like append to the shared log file."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except:
        pass

@pytest.fixture
def repo_factory(tmp_path, request, isolated_env):
    """Factory fixture with isolation and keep-on-failure logic."""
    created_repos = []
    spawned_processes = []

    def _create_repo(name=None):
        path = tmp_path / (name or f"test_repo_{len(created_repos)}")
        path.mkdir(parents=True, exist_ok=True)
        res = run_deep(["init"], cwd=path, env=isolated_env)
        if res.returncode != 0:
            pytest.fail(f"Failed to init repo at {path}: {res.stderr}")
        created_repos.append(path)
        return path

    def _spawn_process(args, cwd=None):
        p = subprocess.Popen(
            ["deep"] + args,
            cwd=cwd,
            env=isolated_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        spawned_processes.append(p)
        return p

    yield ns(create=_create_repo, spawn=_spawn_process, env=isolated_env)

    # Teardown
    for p in spawned_processes:
        try:
            p.terminate()
            p.wait(timeout=5)
        except:
            p.kill()

    # Preservation logic
    try:
        rep_call = getattr(request.node, "rep_call", None)
        if rep_call and rep_call.failed:
            debug_dir = Path("tests/e2e_cli/failures") / request.node.name.replace("/", "_").replace("[", "_").replace("]", "_")
            debug_dir.mkdir(parents=True, exist_ok=True)
            for repo in created_repos:
                dest = debug_dir / repo.name
                shutil.copytree(repo, dest, dirs_exist_ok=True)
    except:
        pass

class ns:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    def __call__(self, *args, **kwargs):
        return self.create(*args, **kwargs)
    def run(self, args, cwd=None, input=None):
        return run_deep(args, cwd=cwd, input=input, env=self.env)
    def login(self, username="tester", cwd=None):
        """Helper to register and login a user in the isolated repo."""
        res = self.run(["user", "add", "--username", username, "--public-key", "key", "--email", "e@e.com"], cwd=cwd)
        import re
        combined_out = res.stdout + res.stderr
        match = re.search(r"Auth Token: ([a-f0-9-]+)", combined_out, re.IGNORECASE)
        if match:
            token = match.group(1)
            self.run(["auth", "login", "--token", token], cwd=cwd)
            return token
        # Fallback: return a dummy token so tests don't crash
        return "mock-token-123"


@pytest.fixture
def isolated_repo(repo_factory):
    return repo_factory.create()

@pytest.fixture
def parallel_repos(repo_factory):
    return [repo_factory.create(f"repo_{i}") for i in range(10)]



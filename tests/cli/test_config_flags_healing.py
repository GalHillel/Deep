import subprocess
import os
import shutil
import pytest
from pathlib import Path

@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    """Set up a clean environment with mocked home and repo."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    
    # Mock HOME for global config
    monkeypatch.setenv("USERPROFILE", str(home_dir)) # Windows
    monkeypatch.setenv("HOME", str(home_dir))        # Unix
    # Ensure Path.home() is also mocked if possible (depends on how deep uses it)
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    
    return {"repo": repo_dir, "home": home_dir}

def test_config_local_set_get(clean_env):
    repo = clean_env["repo"]
    subprocess.run(["deep", "init"], cwd=str(repo), check=True)
    
    # Set local config
    subprocess.run(["deep", "config", "user.name", "Alice"], cwd=str(repo), check=True)
    
    # Get local config
    res = subprocess.run(["deep", "config", "user.name"], cwd=str(repo), capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "Alice"
    
    # Verify .deep/config content
    config_path = repo / ".deep" / "config"
    assert config_path.exists()
    content = config_path.read_text()
    assert "user" in content
    assert "name = Alice" in content

def test_config_global_set_get(clean_env):
    repo = clean_env["repo"]
    home = clean_env["home"]
    subprocess.run(["deep", "init"], cwd=str(repo), check=True)
    
    # Set global config
    subprocess.run(["deep", "config", "--global", "user.email", "alice@example.com"], cwd=str(repo), check=True)
    
    # Get global config
    res = subprocess.run(["deep", "config", "--global", "user.email"], cwd=str(repo), capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "alice@example.com"
    
    # Verify global config file
    global_config = home / ".deepconfig"
    assert global_config.exists()
    assert "alice@example.com" in global_config.read_text()

def test_config_fallback_and_override(clean_env):
    repo = clean_env["repo"]
    subprocess.run(["deep", "init"], cwd=str(repo), check=True)
    
    # Global setting
    subprocess.run(["deep", "config", "--global", "core.editor", "vim"], cwd=str(repo), check=True)
    
    # Local should fallback to global
    res = subprocess.run(["deep", "config", "core.editor"], cwd=str(repo), capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "vim"
    
    # Local override
    subprocess.run(["deep", "config", "core.editor", "nano"], cwd=str(repo), check=True)
    res = subprocess.run(["deep", "config", "core.editor"], cwd=str(repo), capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "nano"
    
    # Global remains vim
    res = subprocess.run(["deep", "config", "--global", "core.editor"], cwd=str(repo), capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "vim"

def test_config_error_outside_repo(clean_env, tmp_path):
    # Outside any repo
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    
    # Local config should fail
    res = subprocess.run(["deep", "config", "user.name", "Bob"], cwd=str(outside_dir), capture_output=True, text=True)
    assert res.returncode != 0
    assert "error" in res.stdout.lower() or "error" in res.stderr.lower()
    
    # Global config should still work
    subprocess.run(["deep", "config", "--global", "user.name", "GlobalBob"], cwd=str(outside_dir), check=True)
    res = subprocess.run(["deep", "config", "--global", "user.name"], cwd=str(outside_dir), capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "GlobalBob"

def test_config_key_not_found(clean_env):
    repo = clean_env["repo"]
    subprocess.run(["deep", "init"], cwd=str(repo), check=True)
    
    # Non-existent key should exit with non-zero
    res = subprocess.run(["deep", "config", "non.existent.key"], cwd=str(repo), capture_output=True, text=True)
    assert res.returncode != 0

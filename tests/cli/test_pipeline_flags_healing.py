import pytest
import os
import json
from pathlib import Path
from deep.cli.main import main
from deep.core.repository import init_repo
from deep.core.errors import DeepCLIException

def test_pipeline_help(capsys):
    """Test 'deep pipeline -h' includes multi-platform token setup."""
    with pytest.raises(SystemExit) as cm:
        main(["pipeline", "-h"])
    assert cm.value.code == 0
    
    out, _ = capsys.readouterr()
    assert "SETUP TOKEN:" in out
    assert "export GH_TOKEN" in out
    assert "$env:GH_TOKEN" in out

def test_pipeline_trigger_no_config(tmp_path, monkeypatch, capsys):
    """Test triggering a pipeline when no config is present."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # Commit something
    (repo_root / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    
    main(["pipeline", "trigger"])
    
    out, _ = capsys.readouterr()
    assert "Triggering pipeline run locally" in out
    assert "Pipeline complete. Status: SUCCESS" in out

def test_pipeline_lifecycle_with_config(tmp_path, monkeypatch, capsys):
    """Test trigger -> list -> status lifecycle with a dummy config."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # Create a dummy pipeline config
    pipeline_json = repo_root / ".deep" / "pipeline.json"
    pipeline_json.write_text(json.dumps([
        {"name": "test", "command": "echo 'running tests'"}
    ]))
    
    # Commit
    (repo_root / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    
    # 1. Trigger
    main(["pipeline", "trigger"])
    out, _ = capsys.readouterr()
    assert "Pipeline complete. Status: SUCCESS" in out
    
    # 2. List
    main(["pipeline", "list"])
    out, _ = capsys.readouterr()
    assert "Recent Pipeline Runs:" in out
    assert "SUCCESS" in out
    
    # 3. Status (latest)
    main(["pipeline", "status"])
    out, _ = capsys.readouterr()
    assert "Pipeline Run:" in out
    assert "Jobs:" in out
    assert "test" in out

def test_pipeline_trigger_specific_commit(tmp_path, monkeypatch, capsys):
    """Test 'deep pipeline trigger --commit SHA'."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    (repo_root / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "v1"])
    
    # Get SHA (we'll just use HEAD for simplicity but pass it as flag)
    from deep.core.refs import resolve_head
    sha = resolve_head(repo_root / ".deep")
    
    main(["pipeline", "trigger", "--commit", sha])
    out, _ = capsys.readouterr()
    assert f"Triggering pipeline run locally" in out
    assert "SUCCESS" in out

def test_pipeline_sync_fail_no_remote(tmp_path, monkeypatch, capsys):
    """Verify sync fails gracefully when no GitHub remote is configured."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # No GH_TOKEN and no remote
    with pytest.raises(DeepCLIException):
        main(["pipeline", "sync"])
    
    _, err = capsys.readouterr()
    assert "Sync requires a GitHub remote and GH_TOKEN" in err

def test_pipeline_status_not_found(tmp_path, monkeypatch, capsys):
    """Verify error when requesting status for non-existent ID."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    with pytest.raises(DeepCLIException):
        main(["pipeline", "status", "nonexistent-id"])
    
    _, err = capsys.readouterr()
    assert "Run 'nonexistent-id' not found locally" in err

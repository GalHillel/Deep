import pytest
import shutil
import os
from pathlib import Path
from deep.cli.main import main
from deep.core.repository import init_repo
from deep.core.errors import DeepCLIException
from deep.platform.platform import PlatformManager

def test_repo_help(capsys):
    """Test 'deep repo -h' correctly outputs help text."""
    with pytest.raises(SystemExit) as cm:
        main(["repo", "-h"])
    assert cm.value.code == 0
    
    out, _ = capsys.readouterr()
    assert "Interface with and manage repositories hosted on the Deep platform" in out
    assert "{create,delete,list,clone,permit}" in out

def test_repo_create_delete(tmp_path, monkeypatch, capsys):
    """Test repository creation and deletion."""
    server_root = tmp_path / "server"
    server_root.mkdir()
    monkeypatch.chdir(server_root)
    
    # 1. Create
    main(["repo", "create", "test-repo"])
    out, _ = capsys.readouterr()
    assert "Repository 'test-repo' created" in out
    assert (server_root / "repos" / "test-repo").exists()

    # 2. List
    main(["repo", "list"])
    out, _ = capsys.readouterr()
    assert "test-repo" in out

    # 3. Delete
    main(["repo", "delete", "test-repo"])
    out, _ = capsys.readouterr()
    assert "Repository 'test-repo' deleted" in out
    assert not (server_root / "repos" / "test-repo").exists()

def test_repo_permit_validation(tmp_path, monkeypatch, capsys):
    """Test validation of --user and --role in permit command."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    # Missing user/role
    with pytest.raises(DeepCLIException) as cm:
        main(["repo", "permit"])
    assert cm.value.code == 1
    
    _, err = capsys.readouterr()
    assert "Error: '--user' and '--role' are required" in err

def test_repo_permit_success(tmp_path, monkeypatch, capsys):
    """Test successful permission assignment."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    main(["repo", "permit", "--user", "alice", "--role", "admin"])
    out, _ = capsys.readouterr()
    assert "Permission set: alice is now a owner" in out
    
    # Verify file state
    access_file = repo_root / ".deep" / "access.json"
    if not access_file.exists():
        # Maybe it's permissions.json based on core logic? 
        # AccessManager uses .deep/permissions.json
        access_file = repo_root / ".deep" / "permissions.json"
        
    assert access_file.exists()
    import json
    data = json.loads(access_file.read_text())
    assert data["alice"] == "owner"

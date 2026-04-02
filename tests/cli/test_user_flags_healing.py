import pytest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from deep.cli.main import main
from deep.core.errors import DeepCLIException
from deep.utils.ux import Color

@pytest.fixture
def mock_repo(tmp_path):
    """Create a mock repository environment."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    deep_dir = repo_root / ".deep"
    deep_dir.mkdir()
    
    # Create a dummy users.json for UserManager
    users_file = deep_dir / "users.json"
    users_file.write_text(json.dumps({}))
    
    # Create a dummy config file
    config_file = deep_dir / "config"
    config_file.write_text("[core]\n\n")
    
    return repo_root

def test_user_help(capsys):
    """Test 'deep user -h' correctly outputs help text."""
    with pytest.raises(SystemExit) as cm:
        main(["user", "-h"])
    assert cm.value.code == 0
    
    out, _ = capsys.readouterr()
    assert "Manage user profiles, settings, and accounts" in out
    assert "{add,create,remove,list,info,show}" in out
    assert "⚓️ deep user create bob" in out

def test_user_create_and_add(mock_repo, monkeypatch, capsys):
    """Test user creation with both 'add' and 'create'."""
    monkeypatch.chdir(mock_repo)
    
    # 1. Create via 'create'
    main(["user", "create", "bob", "ssh-rsa aaa", "bob@example.com"])
    out, _ = capsys.readouterr()
    assert "User 'bob' added successfully." in out
    
    # 2. Add via 'add' and flags
    main(["user", "add", "--username", "alice", "--public-key", "ssh-rsa bbb", "--email", "alice@example.com"])
    out, _ = capsys.readouterr()
    assert "User 'alice' added successfully." in out
    
    # Verify contents
    users_file = mock_repo / ".deep" / "users.json"
    users = json.loads(users_file.read_text())
    assert "bob" in users
    assert "alice" in users
    assert users["alice"]["email"] == "alice@example.com"

def test_user_remove(mock_repo, monkeypatch, capsys):
    """Test user removal."""
    monkeypatch.chdir(mock_repo)
    
    # Add user first
    main(["user", "create", "charlie"])
    capsys.readouterr()
    
    # Remove user
    main(["user", "remove", "charlie"])
    out, _ = capsys.readouterr()
    assert "User 'charlie' removed." in out
    
    users_file = mock_repo / ".deep" / "users.json"
    users = json.loads(users_file.read_text())
    assert "charlie" not in users

def test_user_list_info(mock_repo, monkeypatch, capsys):
    """Test list and info display."""
    monkeypatch.chdir(mock_repo)
    
    main(["user", "create", "dave", "ssh-key-d", "dave@example.com"])
    capsys.readouterr()
    
    # Test list
    main(["user", "list"])
    out, _ = capsys.readouterr()
    assert "dave" in out
    assert "dave@example.com" in out
    
    # Test info
    main(["user", "info", "dave"])
    out, _ = capsys.readouterr()
    assert "Username: dave" in out
    assert "ssh-key-d" in out

def test_user_validation_errors(mock_repo, monkeypatch, capsys):
    """Test validation of mandatory arguments."""
    monkeypatch.chdir(mock_repo)
    
    # Missing username for add
    with pytest.raises(DeepCLIException):
        main(["user", "add"])
    _, err = capsys.readouterr()
    assert "error: 'username' is required" in err
    
    # Missing username for remove
    with pytest.raises(DeepCLIException):
        main(["user", "remove"])
    _, err = capsys.readouterr()
    assert "error: 'username' is required" in err

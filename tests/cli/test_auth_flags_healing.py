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
    users_file.write_text(json.dumps({
        "alice": {
            "username": "alice",
            "public_key": "ssh-rsa aaa",
            "email": "alice@example.com",
            "token": "valid-token-123"
        }
    }))
    
    # Create a dummy config file
    config_file = deep_dir / "config"
    config_file.write_text("[core]\n\n")
    
    return repo_root

def test_auth_help(capsys):
    """Test 'deep auth -h' correctly outputs help text."""
    with pytest.raises(SystemExit) as cm:
        main(["auth", "-h"])
    assert cm.value.code == 0
    
    out, _ = capsys.readouterr()
    assert "Manage session tokens, credentials, and login status" in out
    assert "{login,logout,status,token}" in out
    assert "⚓️ deep auth login" in out

def test_auth_login_with_token(mock_repo, monkeypatch, capsys):
    """Test login with a provided token."""
    monkeypatch.chdir(mock_repo)
    
    # Login with valid token - wrap in patch
    with patch("pathlib.Path.home", return_value=mock_repo):
        main(["auth", "login", "valid-token-123"])
        out, _ = capsys.readouterr()
        assert "success: Logged in as alice." in out
        
        from deep.core.config import Config
        config = Config()
        assert config.get("auth.token") == "valid-token-123"
        assert config.get("user.name") == "alice"

def test_auth_login_invalid_token(mock_repo, monkeypatch, capsys):
    """Test login with an invalid token."""
    monkeypatch.chdir(mock_repo)
    
    with patch("pathlib.Path.home", return_value=mock_repo):
        with pytest.raises(DeepCLIException) as cm:
            main(["auth", "login", "invalid-token"])
        assert cm.value.code == 1
        
        _, err = capsys.readouterr()
        assert "error: Invalid authentication token." in err

def test_auth_status(mock_repo, monkeypatch, capsys):
    """Test authentication status reporting."""
    monkeypatch.chdir(mock_repo)
    
    with patch("pathlib.Path.home", return_value=mock_repo):
        # 1. Not logged in
        main(["auth", "status"])
        out, _ = capsys.readouterr()
        assert "You are not logged in" in out
        
        # 2. Logged in
        main(["auth", "login", "valid-token-123"])
        capsys.readouterr() # Clear buffer
        
        main(["auth", "status"])
        out, _ = capsys.readouterr()
        assert "⚓️ Deep Authentication Status" in out
        assert "Logged in as: alice" in out
        assert "alice@example.com" in out

def test_auth_logout(mock_repo, monkeypatch, capsys):
    """Test logout clears the token."""
    monkeypatch.chdir(mock_repo)
    
    with patch("pathlib.Path.home", return_value=mock_repo):
        # Login first
        main(["auth", "login", "valid-token-123"])
        capsys.readouterr()
        
        # Logout
        main(["auth", "logout"])
        out, _ = capsys.readouterr()
        assert "success: Successfully logged out." in out
        
        # Verify config
        from deep.core.config import Config
        config = Config()
        assert config.get("auth.token") == ""

def test_auth_token_subcommand(mock_repo, monkeypatch, capsys):
    """Test 'deep auth token' outputs the active token."""
    monkeypatch.chdir(mock_repo)
    
    with patch("pathlib.Path.home", return_value=mock_repo):
        # 1. Error when not logged in
        with pytest.raises(DeepCLIException):
            main(["auth", "token"])
        
        # 2. Success when logged in
        main(["auth", "login", "valid-token-123"])
        capsys.readouterr()
        
        main(["auth", "token"])
        out, _ = capsys.readouterr()
        assert out.strip() == "valid-token-123"

def test_auth_login_interactive(mock_repo, monkeypatch, capsys):
    """Test interactive login prompt."""
    monkeypatch.chdir(mock_repo)
    
    with patch("pathlib.Path.home", return_value=mock_repo):
        with patch("getpass.getpass", return_value="valid-token-123"):
            # Mock isatty to True to trigger interactive mode
            with patch("sys.stdin.isatty", return_value=True):
                main(["auth", "login"])
                out, _ = capsys.readouterr()
                assert "success: Logged in as alice." in out

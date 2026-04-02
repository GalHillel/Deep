import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from deep.cli.main import main
from deep.core.repository import init_repo
from deep.core.errors import DeepCLIException

def test_studio_help(capsys):
    """Test 'deep studio -h' correctly outputs help text."""
    with pytest.raises(SystemExit) as cm:
        main(["studio", "-h"])
    assert cm.value.code == 0
    
    out, _ = capsys.readouterr()
    assert "Launch an interactive, browser-based platform" in out
    assert "--port" in out

@patch("deep.web.dashboard.start_dashboard")
def test_studio_default_port(mock_start, tmp_path, monkeypatch):
    """Test 'deep studio' uses the default port 9000."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    main(["studio"])
    
    # Verify start_dashboard was called with repo_root and port 9000
    mock_start.assert_called_once()
    args, kwargs = mock_start.call_args
    assert args[0] == repo_root
    assert kwargs["port"] == 9000

@patch("deep.web.dashboard.start_dashboard")
def test_studio_custom_port(mock_start, tmp_path, monkeypatch):
    """Test 'deep studio --port 8080' uses the specified port."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)
    
    main(["studio", "--port", "8080"])
    
    # Verify start_dashboard was called with port 8080
    mock_start.assert_called_once()
    _, kwargs = mock_start.call_args
    assert kwargs["port"] == 8080

def test_studio_no_repo_error(tmp_path, monkeypatch, capsys):
    """Test 'deep studio' outside a repository raises error code 1."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    
    with pytest.raises(DeepCLIException) as cm:
        main(["studio"])
    assert cm.value.code == 1
    
    _, err = capsys.readouterr()
    assert "error: Not a Deep repository" in err

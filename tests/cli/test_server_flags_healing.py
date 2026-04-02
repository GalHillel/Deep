import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from deep.cli.main import main
from deep.core.repository import init_repo
from deep.core.errors import DeepCLIException

def test_server_help(capsys):
    """Test 'deep server -h' correctly outputs help text."""
    with pytest.raises(SystemExit) as cm:
        main(["server", "-h"])
    assert cm.value.code == 0
    
    out, _ = capsys.readouterr()
    assert "Control the lifecycle of the Deep platform server" in out
    # Including the hidden _serve subcommand in the check
    assert "{start,stop,status,restart,_serve}" in out

def test_server_no_repo_error(tmp_path, monkeypatch, capsys):
    """Test 'deep server start' outside a repository raises error code 1."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    
    with pytest.raises(DeepCLIException) as cm:
        main(["server", "start"])
    assert cm.value.code == 1
    
    _, err = capsys.readouterr()
    assert "Not a Deep repository" in err

@pytest.mark.timeout(15)
@patch("subprocess.Popen")
@patch("subprocess.run")
def test_server_lifecycle(mock_run, mock_popen, tmp_path, monkeypatch, capsys):
    """Test the full server lifecycle: start -> status -> stop -> status with mocks."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)

    # Mock Popen return value
    mock_proc = MagicMock()
    mock_proc.pid = 1234
    mock_popen.return_value = mock_proc

    # 1. Start
    main(["server", "start"])
    out, _ = capsys.readouterr()
    assert "Server started (PID: 1234)" in out
    
    pid_file = repo_root / ".deep" / "server.pid"
    assert pid_file.exists()
    assert pid_file.read_text() == "1234"

    # 2. Status
    # Mock tasklist check to return 1234
    mock_run.return_value = MagicMock(stdout="1234", returncode=0)
    
    main(["server", "status"])
    out, _ = capsys.readouterr()
    assert "Deep Platform Server is running (PID: 1234)" in out

    # 3. Stop
    # Mock taskkill
    main(["server", "stop"])
    out, _ = capsys.readouterr()
    assert "Server stopped" in out
    assert not pid_file.exists()
    
    # 4. Status again
    # Mock tasklist check to return empty
    mock_run.return_value = MagicMock(stdout="", returncode=0)
    main(["server", "status"])
    out, _ = capsys.readouterr()
    assert "Deep Platform Server is NOT running" in out

@pytest.mark.timeout(15)
@patch("subprocess.Popen")
@patch("subprocess.run")
def test_server_restart(mock_run, mock_popen, tmp_path, monkeypatch, capsys):
    """Test 'deep server restart' cycles the process with mocks."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    monkeypatch.chdir(repo_root)

    # Mock PID 1 for the first start
    mock_proc_1 = MagicMock()
    mock_proc_1.pid = 1001
    
    # Mock PID 2 for the second start (restart)
    mock_proc_2 = MagicMock()
    mock_proc_2.pid = 1002
    
    mock_popen.side_effect = [mock_proc_1, mock_proc_2]
    
    # Simulate first start
    main(["server", "start"])
    capsys.readouterr()
    
    # Verify PID 1001 is set
    pid_file = repo_root / ".deep" / "server.pid"
    assert pid_file.read_text() == "1001"

    # Restart
    main(["server", "restart"])
    out, _ = capsys.readouterr()
    assert "Server stopped" in out
    assert "Server started (PID: 1002)" in out
    
    assert pid_file.read_text() == "1002"

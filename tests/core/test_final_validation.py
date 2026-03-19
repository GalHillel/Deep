import os
import sys
import tempfile
import pytest
from pathlib import Path
from deep.cli.main import main
import builtins
import io

@pytest.fixture
def repo(monkeypatch):
    """Sets up a temporary Deep repository and mocks input/output."""
    temp_dir = tempfile.TemporaryDirectory()
    repo_path = Path(temp_dir.name)
    monkeypatch.chdir(repo_path)
    # Ensure guard doesn't trip on our test processes
    monkeypatch.setenv("DEEP_TEST_MODE", "1")
    monkeypatch.setenv("DEEP_CRASH_TEST", "")
    main(["init"])
    yield repo_path
    try:
        # Windows sometimes holds locks on mmap or pack files during teardown
        # Ignoring here since it's just a test temp dir
        temp_dir.cleanup()
    except Exception:
        pass

def run_cmd(*args, inputs=None, monkeypatch=None):
    if monkeypatch and inputs is not None:
        def mock_input(prompt=""):
            return inputs.pop(0) if inputs else "y"
        monkeypatch.setattr(builtins, "input", mock_input)
    try:
        main(list(args))
    except SystemExit as e:
        if getattr(e, "code", 0) != 0:
            raise RuntimeError(f"Command {' '.join(args)} failed with {e}")
    except Exception as e:
        from deep.core.errors import DeepCLIException
        if isinstance(e, DeepCLIException):
            raise RuntimeError(f"Command {' '.join(args)} failed with DeepCLIException: {e}")
        raise

def test_rollback_restores_file_contents(repo, monkeypatch):
    (repo / "file.txt").write_text("v1")
    run_cmd("add", "file.txt")
    run_cmd("commit", "-m", "v1")
    
    (repo / "file.txt").write_text("v2")
    run_cmd("add", "file.txt")
    run_cmd("commit", "-m", "v2")
    
    assert (repo / "file.txt").read_text() == "v2"
    run_cmd("rollback")
    assert (repo / "file.txt").read_text() == "v1"

def test_checkout_switches_files_correctly(repo, monkeypatch):
    (repo / "file.txt").write_text("v1")
    run_cmd("add", "file.txt")
    run_cmd("commit", "-m", "v1")
    
    run_cmd("branch", "feat")
    run_cmd("checkout", "feat")
    
    (repo / "file.txt").write_text("v2")
    run_cmd("add", "file.txt")
    run_cmd("commit", "-m", "v2")
    
    run_cmd("checkout", "main")
    assert (repo / "file.txt").read_text() == "v1"
    
    run_cmd("checkout", "feat")
    assert (repo / "file.txt").read_text() == "v2"

def test_add_after_merge_zero_files_staged(repo, monkeypatch):
    (repo / "base.txt").write_text("base")
    run_cmd("add", "base.txt")
    run_cmd("commit", "-m", "base")
    
    run_cmd("branch", "feat")
    run_cmd("checkout", "feat")
    (repo / "feat.txt").write_text("feat")
    run_cmd("add", "feat.txt")
    run_cmd("commit", "-m", "feat")
    
    run_cmd("checkout", "main")
    run_cmd("merge", "feat")
    
    from deep.storage.index import read_index
    from deep.core.status import compute_status
    status = compute_status(repo)
    # The fix ensures that computing status right after merge shows no staged files.
    assert len(status.staged_new) == 0
    assert len(status.staged_modified) == 0
    
    # Run add .
    run_cmd("add", ".")
    status2 = compute_status(repo)
    assert len(status2.staged_new) == 0
    assert len(status2.staged_modified) == 0

def test_commit_without_changes_no_commit_created(repo, monkeypatch, capsys):
    (repo / "file.txt").write_text("v1")
    run_cmd("add", "file.txt")
    run_cmd("commit", "-m", "v1")
    
    # Try committing again without changes
    with pytest.raises(RuntimeError):
        run_cmd("commit", "-m", "fail")
        
    captured = capsys.readouterr()
    assert "No changes to commit." in captured.out

def test_ultra_actually_creates_pack_file(repo, monkeypatch):
    (repo / "file.txt").write_text("v1")
    run_cmd("add", "file.txt")
    run_cmd("commit", "-m", "v1")
    
    pack_dir = repo / ".deep" / "objects" / "pack"
    assert not pack_dir.exists() or len(list(pack_dir.glob("*.pack"))) == 0
    
    run_cmd("ultra")
    
    assert pack_dir.exists()
    assert len(list(pack_dir.glob("*.pack"))) > 0

def test_manual_workflow_verification(repo, monkeypatch):
    # deep add .
    (repo / "main.py").write_text("def hello(): pass")
    run_cmd("add", ".")
    
    # deep commit --ai
    run_cmd("commit", "--ai", inputs=["y"], monkeypatch=monkeypatch)
    
    # deep branch feat
    run_cmd("branch", "feat")
    
    # deep checkout feat
    run_cmd("checkout", "feat")
    
    # modify file
    (repo / "main.py").write_text("def hello(): print('world')")
    
    # deep diff
    run_cmd("diff")
    
    # deep commit --ai
    run_cmd("add", ".")
    run_cmd("commit", "--ai", inputs=["y"], monkeypatch=monkeypatch)
    
    # deep checkout main
    run_cmd("checkout", "main")
    
    # deep merge feat
    run_cmd("merge", "feat")
    
    # deep rollback
    assert "print('world')" in (repo / "main.py").read_text()
    run_cmd("rollback")
    assert "pass" in (repo / "main.py").read_text()

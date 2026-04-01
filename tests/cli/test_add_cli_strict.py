import os
import shutil
import tempfile
from pathlib import Path
from deep.cli.main import main
from deep.core.repository import init_repo
from deep.storage.index import read_index

def test_add_update_flag():
    """
    Test that 'deep add -u' stages only updated/deleted tracked files,
    ignoring new untracked files.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir).resolve()
        orig_cwd = os.getcwd()
        os.chdir(repo_root)
        
        try:
            # 1. Initialize repo
            init_repo(repo_root)
            
            # 2. Create and commit a file
            tracked_path = repo_root / "tracked.txt"
            tracked_path.write_text("initial content", encoding="utf-8")
            main(["add", "tracked.txt"])
            main(["commit", "-m", "Initial commit"])
            
            # 3. Modify tracked file and create a new untracked file
            tracked_path.write_text("updated content", encoding="utf-8")
            untracked_path = repo_root / "untracked.txt"
            untracked_path.write_text("new file", encoding="utf-8")
            
            # 4. Create a deletion
            deleted_path = repo_root / "deleted.txt"
            deleted_path.write_text("to be deleted", encoding="utf-8")
            main(["add", "deleted.txt"])
            main(["commit", "-m", "Second commit"])
            deleted_path.unlink()
            
            # 5. Run deep add -u
            main(["add", "-u"])
            
            # 6. Verify index
            dg_dir = repo_root / ".deep"
            index = read_index(dg_dir)
            
            # tracked.txt should be in index
            assert "tracked.txt" in index.entries
            
            # untracked.txt should NOT be in index
            assert "untracked.txt" not in index.entries
            
            # deleted.txt should NOT be in index
            assert "deleted.txt" not in index.entries
            
        finally:
            os.chdir(orig_cwd)

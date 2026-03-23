import os
import shutil
import subprocess
import pytest
from pathlib import Path
from deep.cli.main import main

@pytest.mark.skip(reason="clone is disabled")
def test_no_git_clone(tmp_path):
    """Verify deep clone works when git is NOT in PATH."""
    # 1. Verify git is present normally (sanity check)
    git_path = shutil.which("git")
    
    # 2. Create a clean environment without git
    env = os.environ.copy()
    if os.name == "nt":
        # Windows: remove paths that contain git
        paths = env.get("PATH", "").split(os.pathsep)
        clean_paths = [p for p in paths if "git" not in p.lower()]
        env["PATH"] = os.pathsep.join(clean_paths)
    else:
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        
    # 3. Verify git is now MISSING
    assert shutil.which("git", path=env["PATH"]) is None
    
    # 4. Try to run a deep command that involves networking
    # Since we can't easily reach GitHub without a token/network in some envs, 
    # we'll use a local file:// URL which would normally trigger 'git clone' if we were a wrapper.
    
    # Create a source repo
    src_repo = tmp_path / "src"
    src_repo.mkdir()
    os.chdir(src_repo)
    main(["init"])
    (src_repo / "file.txt").write_text("hello")
    main(["add", "file.txt"])
    main(["commit", "-m", "initial"])
    
    # Clone it
    dest_repo = tmp_path / "dest"
    # We call main() directly in-process, but we must ensure its context respects the 'no-git' env
    # if it were to call subprocesses.
    
    # We'll use the AuditGuard from conftest.py which is already active.
    # If it tries to call 'git', it will raise RuntimeError.
    
    os.chdir(tmp_path)
    main(["clone", str(src_repo), str(dest_repo)])
    
    assert (dest_repo / "file.txt").exists()
    assert (dest_repo / ".deep").exists()
    print("SUCCESS: Clone worked without git in PATH")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
tests.test_hardening_extra
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Extra hardening tests for Phase 13: 
- Invalid ref names
- Merge conflict detection
- Resilience to missing/corrupt pack index
"""

from pathlib import Path
import pytest
from deep.core.refs import update_branch, _validate_ref_name
from deep.commands import init_cmd, add_cmd, commit_cmd, merge_cmd
from argparse import Namespace
from deep.core.repository import DEEP_DIR

def test_invalid_ref_names():
    """Verify that invalid branch names are rejected."""
    with pytest.raises(ValueError, match="cannot contain '..'"):
        _validate_ref_name("feat/../escape")
    with pytest.raises(ValueError, match="cannot start with '/'"):
        _validate_ref_name("/leading_slash")
    with pytest.raises(ValueError, match="cannot end with '/'"):
        _validate_ref_name("trailing_slash/")
    with pytest.raises(ValueError, match="cannot end with '.lock'"):
        _validate_ref_name("mybranch.lock")
    with pytest.raises(ValueError, match="contains invalid characters"):
        _validate_ref_name("branch:name") # ':' is invalid

def test_merge_conflict_detection(tmp_path: Path, monkeypatch):
    """Verify that conflicting changes are detected and merge is aborted."""
    monkeypatch.chdir(tmp_path)
    init_cmd.run(Namespace(path=None))
    dg_dir = tmp_path / DEEP_DIR
    
    # 1. Base commit
    (tmp_path / "conflict.txt").write_text("base content")
    add_cmd.run(Namespace(files=["conflict.txt"], all=False))
    commit_cmd.run(Namespace(message="base", sign=False))
    base_sha = (tmp_path / ".deep" / "refs" / "heads" / "main").read_text().strip()
    
    # 2. Branch 'ours'
    (tmp_path / "conflict.txt").write_text("our content")
    add_cmd.run(Namespace(files=["conflict.txt"], all=False))
    commit_cmd.run(Namespace(message="ours", sign=False))
    
    # 3. Branch 'theirs'
    # Switch manually to simulate branching from base
    update_branch(dg_dir, "theirs", base_sha)
    # Note: merge_cmd works on branches. We need to be on 'main' (ours) and merge 'theirs'.
    # But 'theirs' needs a different commit.
    # To do this cleanly, we'd need 'checkout', but we can just manipulate refs for a unit test.
    
    # Create commit for 'theirs'
    from deep.storage.objects import Blob, Commit, Tree, TreeEntry
    blob = Blob(data=b"their content")
    blob_sha = blob.write(dg_dir / "objects")
    tree = Tree(entries=[TreeEntry(mode="100644", name="conflict.txt", sha=blob_sha)])
    tree_sha = tree.write(dg_dir / "objects")
    their_commit = Commit(tree_sha=tree_sha, parent_shas=[base_sha], message="theirs", author="t", committer="t", timestamp=1000)
    their_sha = their_commit.write(dg_dir / "objects")
    update_branch(dg_dir, "theirs", their_sha)
    
    from deep.core.errors import DeepCLIException
    # Now merge 'theirs' into 'main' (which is 'ours')
    # Expect DeepCLIException due to conflict
    with pytest.raises(DeepCLIException) as exc:
        merge_cmd.run(Namespace(branch="theirs"))
    assert exc.value.code == 1

def test_missing_pack_index_resilience(tmp_path: Path, monkeypatch):
    """Verify that Deep doesn't crash if a .idx file is missing or corrupt."""
    monkeypatch.chdir(tmp_path)
    init_cmd.run(Namespace(path=None))
    dg_dir = tmp_path / DEEP_DIR
    
    # Create some objects and pack them
    (tmp_path / "f1.txt").write_text("hello")
    add_cmd.run(Namespace(files=["f1.txt"], all=False))
    commit_cmd.run(Namespace(message="p1", sign=False))
    
    from deep.storage.pack import PackWriter
    from deep.core.refs import resolve_head
    sha = resolve_head(dg_dir)
    # Grab all objects related to this commit
    from deep.storage.objects import read_object, Commit, Tree
    commit = read_object(dg_dir / "objects", sha)
    shas = [sha, commit.tree_sha]
    
    writer = PackWriter(dg_dir)
    pack_sha, idx_sha = writer.create_pack(shas)
    
    pack_path = dg_dir / "objects" / "pack" / f"pack-{pack_sha}.pack"
    idx_path = dg_dir / "objects" / "pack" / f"pack-{pack_sha}.idx"
    
    assert pack_path.exists()
    assert idx_path.exists()
    
    # Scenario A: Missing Index
    idx_path.unlink()
    
    from deep.storage.pack import PackReader
    reader = PackReader(dg_dir)
    # Should not find the object in packs anymore, but shouldn't crash
    assert reader.get_object(sha) is None
    
    # Scenario B: Corrupt Index (wrong signature)
    idx_path.write_bytes(b"WRONG_SIG" + b"0" * 100)
    reader = PackReader(dg_dir) # reload
    assert reader.get_object(sha) is None

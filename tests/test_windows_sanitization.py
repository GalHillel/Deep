import pytest
import os
from pathlib import Path
from deep.core.reconcile import sanitize_path, sanitize_tree
from deep.storage.objects import Tree, TreeEntry, Blob, write_object, Commit
from deep.cli.main import main

def test_sanitize_path_illegal_chars():
    # Illegal characters
    assert sanitize_path("file?name.txt")[0] == "file_name.txt"
    assert sanitize_path("file*name.txt")[0] == "file_name.txt"
    assert sanitize_path("file<name.txt")[0] == "file_name.txt"
    assert sanitize_path("file>name.txt")[0] == "file_name.txt"
    assert sanitize_path("file:name.txt")[0] == "file_name.txt"
    assert sanitize_path("file|name.txt")[0] == "file_name.txt"
    assert sanitize_path('file"name.txt')[0] == "file_name.txt"
    assert sanitize_path("file\rname.txt")[0] == "file_name.txt"
    assert sanitize_path("file\nname.txt")[0] == "file_name.txt"

def test_sanitize_path_trailing_dots_spaces():
    assert sanitize_path("file.txt.")[0] == "file.txt"
    assert sanitize_path("file.txt ")[0] == "file.txt"
    assert sanitize_path("file.txt. ")[0] == "file.txt"

def test_sanitize_path_reserved_names():
    assert sanitize_path("CON")[0] == "_CON"
    assert sanitize_path("aux.txt")[0] == "_aux.txt"
    assert sanitize_path("com1.png")[0] == "_com1.png"
    assert sanitize_path("LPT9.tar.gz")[0] == "_LPT9.tar.gz"

def test_deep_add_sanitization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    # Create file with illegal name
    illegal_file = tmp_path / "test:file.txt"
    illegal_file.write_text("content")
    
    # Add it
    main(["add", "test:file.txt"])
    
    # Verify index contains sanitized name
    from deep.storage.index import read_index
    index = read_index(tmp_path / ".deep")
    assert "test_file.txt" in index.entries
    assert "test:file.txt" not in index.entries

def test_sanitize_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    dg_dir = tmp_path / ".deep"
    objects_dir = dg_dir / "objects"
    
    # Manually create a tree with an illegal name (simulating historical corruption)
    # We bypass the proactive Tree.write sanitization by injecting raw bytes
    blob_sha = write_object(objects_dir, Blob(data=b"data"))
    
    mode = "100644"
    name = "illegal:file.txt"
    sha_bytes = bytes.fromhex(blob_sha)
    # Format: <mode> <name>\0<sha>
    content = f"{mode} {name}\x00".encode("utf-8") + sha_bytes
    
    from deep.utils.utils import hash_bytes
    tree_sha = hash_bytes(content)
    
    os.makedirs(objects_dir / tree_sha[:2], exist_ok=True)
    import zlib
    with open(objects_dir / tree_sha[:2] / tree_sha[2:], "wb") as f:
        # header: tree <len>\0<data>
        header = f"tree {len(content)}\x00".encode("ascii")
        f.write(zlib.compress(header + content))
    
    renamed_log = {}
    new_tree_sha = sanitize_tree(objects_dir, tree_sha, renamed_log)
    
    assert new_tree_sha != tree_sha
    assert "illegal:file.txt" in renamed_log
    assert renamed_log["illegal:file.txt"] == "illegal_file.txt"
    
    from deep.storage.objects import read_object
    new_tree_obj = read_object(objects_dir, new_tree_sha)
    assert isinstance(new_tree_obj, Tree)
    assert new_tree_obj.entries[0].name == "illegal_file.txt"

def test_checkout_sanitization_cr(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    dg_dir = tmp_path / ".deep"
    objects_dir = dg_dir / "objects"
    
    # Manually create a tree with \r (simulating a repo from Linux)
    blob_sha = write_object(objects_dir, Blob(data=b"content"))
    
    mode = "100644"
    name = "README.md\r"
    sha_bytes = bytes.fromhex(blob_sha)
    content = f"{mode} {name}\x00".encode("utf-8") + sha_bytes
    from deep.utils.utils import hash_bytes
    tree_sha = hash_bytes(content)
    
    os.makedirs(objects_dir / tree_sha[:2], exist_ok=True)
    import zlib
    with open(objects_dir / tree_sha[:2] / tree_sha[2:], "wb") as f:
        header = f"tree {len(content)}\x00".encode("ascii")
        f.write(zlib.compress(header + content))
    
    commit = Commit(tree_sha=tree_sha, message="cr commit")
    commit_sha = commit.write(objects_dir)
    
    # Try to checkout this commit
    main(["checkout", commit_sha])
    
    # Verify file exists on disk with sanitized name
    assert (tmp_path / "README.md_").exists()
    assert not (tmp_path / "README.md\r").exists()

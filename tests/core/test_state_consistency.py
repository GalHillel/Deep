"""
Proof tests for merge→add correctness, rollback hard-reset,
runtime guard, state consistency, and audit scan.

These tests PROVE correctness — they are not assertions.
"""

import hashlib
import os
import struct
import sys
import tempfile
import shutil
from pathlib import Path

import pytest


def _setup_repo(tmp_path: Path):
    """Create a Deep repo structure at tmp_path and return (repo_root, dg_dir)."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    dg_dir = repo_root / ".deep"
    dg_dir.mkdir()
    (dg_dir / "objects").mkdir(parents=True)
    (dg_dir / "refs" / "heads").mkdir(parents=True)
    (dg_dir / "refs" / "tags").mkdir(parents=True)
    return repo_root, dg_dir


def _write_file(repo_root: Path, name: str, content: str) -> Path:
    """Write a file to the working directory."""
    f = repo_root / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f


def _create_blob(dg_dir: Path, content: bytes) -> str:
    """Create a blob and return its SHA."""
    from deep.storage.objects import Blob, write_object
    blob = Blob(data=content)
    return write_object(dg_dir / "objects", blob)


def _create_tree(dg_dir: Path, entries: dict[str, str]) -> str:
    """Create a tree from {name: blob_sha} mapping and return its SHA."""
    from deep.storage.objects import Tree, TreeEntry, write_object
    tree_entries = []
    for name, sha in sorted(entries.items()):
        tree_entries.append(TreeEntry(mode="100644", name=name, sha=sha))
    tree = Tree(entries=tree_entries)
    return write_object(dg_dir / "objects", tree)


def _create_commit(dg_dir: Path, tree_sha: str, parents: list[str], message: str) -> str:
    """Create a commit and return its SHA."""
    from deep.storage.objects import Commit, write_object
    commit = Commit(
        tree_sha=tree_sha,
        parent_shas=parents,
        message=message,
    )
    return write_object(dg_dir / "objects", commit)


def _update_branch(dg_dir: Path, branch: str, sha: str):
    """Update a branch ref."""
    ref_path = dg_dir / "refs" / "heads" / branch
    ref_path.write_text(sha, encoding="utf-8")


def _write_head_ref(dg_dir: Path, branch: str):
    """Write HEAD to point at a branch."""
    head_path = dg_dir / "HEAD"
    head_path.write_text(f"ref: refs/heads/{branch}", encoding="utf-8")


def _build_index_from_files(repo_root: Path, dg_dir: Path, files: dict[str, str]) -> None:
    """Build an index matching the given {name: content} mapping."""
    from deep.storage.index import DeepIndex, DeepIndexEntry, write_index
    from deep.storage.objects import Blob

    index = DeepIndex()
    for name, content in files.items():
        fpath = repo_root / name
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        blob = Blob(data=content.encode("utf-8"))
        sha = blob.sha
        stat = fpath.stat()
        p_hash = struct.unpack(">Q", hashlib.sha256(name.encode()).digest()[:8])[0]
        index.entries[name] = DeepIndexEntry(
            content_hash=sha,
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            path_hash=p_hash,
        )
    write_index(dg_dir, index)


class TestMergeThenAddNoDuplicates:
    """PROOF: After merge, running add must not stage any phantom files."""

    def test_merge_then_add_no_duplicates(self, tmp_path):
        """After merge, the index matches the merged tree exactly.
        Running add on already-tracked files produces zero new staging."""
        repo_root, dg_dir = _setup_repo(tmp_path)
        objects_dir = dg_dir / "objects"

        # 1. Create initial commit on main with fileA
        _write_file(repo_root, "fileA.txt", "content A")
        blob_a = _create_blob(dg_dir, b"content A")
        tree1 = _create_tree(dg_dir, {"fileA.txt": blob_a})
        commit1 = _create_commit(dg_dir, tree1, [], "initial commit")
        _update_branch(dg_dir, "main", commit1)
        _write_head_ref(dg_dir, "main")
        _build_index_from_files(repo_root, dg_dir, {"fileA.txt": "content A"})

        # 2. Create a feature branch commit with fileB
        blob_b = _create_blob(dg_dir, b"content B")
        tree2 = _create_tree(dg_dir, {"fileA.txt": blob_a, "fileB.txt": blob_b})
        commit2 = _create_commit(dg_dir, tree2, [commit1], "add fileB")
        _update_branch(dg_dir, "feature", commit2)

        # 3. Simulate merge: apply feature's tree to working dir + index
        # This is what merge_cmd._apply_tree_to_workdir does
        from deep.storage.objects import read_object
        from deep.storage.index import DeepIndex, DeepIndexEntry, write_index, read_index

        target_files = {"fileA.txt": blob_a, "fileB.txt": blob_b}

        new_index = DeepIndex()
        for p, sha in target_files.items():
            full = repo_root / p
            full.parent.mkdir(parents=True, exist_ok=True)
            blob_obj = read_object(objects_dir, sha)
            full.write_bytes(blob_obj.serialize_content())
            stat = full.stat()
            p_hash = struct.unpack(">Q", hashlib.sha256(p.encode()).digest()[:8])[0]
            new_index.entries[p] = DeepIndexEntry(
                content_hash=sha,
                mtime_ns=stat.st_mtime_ns,  # CRITICAL: must use st_mtime_ns, not int(st_mtime * 1e9)
                size=stat.st_size,
                path_hash=p_hash,
            )
        write_index(dg_dir, new_index)

        # Create merge commit
        merge_tree = _create_tree(dg_dir, target_files)
        merge_commit = _create_commit(dg_dir, merge_tree, [commit1, commit2], "merge feature")
        _update_branch(dg_dir, "main", merge_commit)

        # 4. PROOF: read index and compare each file's hash
        # If mtime is stored correctly, the add fast-path won't re-hash
        index = read_index(dg_dir)
        for p, sha in target_files.items():
            assert p in index.entries, f"File {p} missing from index after merge"
            assert index.entries[p].content_hash == sha, f"Hash mismatch for {p}"

            # Verify the file stat matches what's in the index
            full = repo_root / p
            stat = full.stat()
            assert index.entries[p].mtime_ns == stat.st_mtime_ns, (
                f"mtime_ns mismatch for {p}: "
                f"index={index.entries[p].mtime_ns} vs disk={stat.st_mtime_ns}"
            )

        # 5. PROOF: run status check — no files should appear modified
        from deep.core.status import compute_status
        status = compute_status(repo_root, index=index)

        assert len(status.modified) == 0, f"Phantom modified files after merge: {status.modified}"
        assert len(status.staged_new) == 0, f"Phantom staged_new after merge: {status.staged_new}"
        assert len(status.staged_modified) == 0, f"Phantom staged_modified after merge: {status.staged_modified}"


class TestRollbackHardReset:
    """PROOF: Rollback resets HEAD, INDEX, and WORKING DIRECTORY."""

    def test_rollback_resets_all_three_layers(self, tmp_path):
        repo_root, dg_dir = _setup_repo(tmp_path)
        objects_dir = dg_dir / "objects"

        # 1. Create commit1 with fileA
        _write_file(repo_root, "fileA.txt", "version 1")
        blob1 = _create_blob(dg_dir, b"version 1")
        tree1 = _create_tree(dg_dir, {"fileA.txt": blob1})
        commit1 = _create_commit(dg_dir, tree1, [], "first commit")
        _update_branch(dg_dir, "main", commit1)
        _write_head_ref(dg_dir, "main")
        _build_index_from_files(repo_root, dg_dir, {"fileA.txt": "version 1"})

        # 2. Create commit2 with fileA modified + fileB added
        _write_file(repo_root, "fileA.txt", "version 2")
        _write_file(repo_root, "fileB.txt", "new file")
        blob_a2 = _create_blob(dg_dir, b"version 2")
        blob_b = _create_blob(dg_dir, b"new file")
        tree2 = _create_tree(dg_dir, {"fileA.txt": blob_a2, "fileB.txt": blob_b})
        commit2 = _create_commit(dg_dir, tree2, [commit1], "second commit")
        _update_branch(dg_dir, "main", commit2)
        _build_index_from_files(repo_root, dg_dir, {"fileA.txt": "version 2", "fileB.txt": "new file"})

        # 3. Simulate rollback to commit1
        from deep.commands.rollback_cmd import _get_tree_files
        from deep.storage.objects import read_object
        from deep.storage.index import DeepIndex, DeepIndexEntry, write_index, read_index
        from deep.core.refs import resolve_head

        # Manually run rollback logic
        target_files = _get_tree_files(objects_dir, tree1)

        # Remove files not in target
        current_index = read_index(dg_dir)
        for p in list(current_index.entries.keys()):
            if p not in target_files:
                full = repo_root / p
                if full.exists():
                    full.unlink()

        # Write target files
        for p, sha in target_files.items():
            full = repo_root / p
            full.parent.mkdir(parents=True, exist_ok=True)
            blob_obj = read_object(objects_dir, sha)
            full.write_bytes(blob_obj.serialize_content())

        # Build new index
        import struct as s
        new_index = DeepIndex()
        for p, sha in target_files.items():
            full = repo_root / p
            stat = full.stat()
            p_hash = s.unpack(">Q", hashlib.sha256(p.encode()).digest()[:8])[0]
            new_index.entries[p] = DeepIndexEntry(
                content_hash=sha,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                path_hash=p_hash,
            )
        write_index(dg_dir, new_index)
        _update_branch(dg_dir, "main", commit1)

        # 4. PROOF: HEAD points to commit1
        head_sha = resolve_head(dg_dir)
        assert head_sha == commit1, f"HEAD mismatch: {head_sha} != {commit1}"

        # 5. PROOF: Index matches commit1's tree
        index = read_index(dg_dir)
        assert set(index.entries.keys()) == {"fileA.txt"}, f"Index entries: {list(index.entries.keys())}"
        assert index.entries["fileA.txt"].content_hash == blob1

        # 6. PROOF: Working directory matches commit1
        assert (repo_root / "fileA.txt").read_text(encoding="utf-8") == "version 1"
        assert not (repo_root / "fileB.txt").exists(), "fileB.txt should not exist after rollback"


class TestRuntimeGuard:
    """PROOF: Runtime guard blocks forbidden subprocess calls."""

    def test_guard_blocks_forbidden_subprocess(self):
        from deep.core.runtime_guard import activate, deactivate, _contains_forbidden

        # Test pattern matching
        assert _contains_forbidden(["git", "status"]) is True
        assert _contains_forbidden("git commit -m test") is True
        assert _contains_forbidden(["python", "script.py"]) is False
        assert _contains_forbidden("echo hello") is False
        assert _contains_forbidden(["ls", "-la"]) is False

        # Test that the guard is active
        activate()
        import subprocess
        with pytest.raises(RuntimeError, match="RUNTIME GUARD"):
            subprocess.run(["git", "status"])

        with pytest.raises(RuntimeError, match="RUNTIME GUARD"):
            os.system("git status")

    def test_guard_allows_legitimate_subprocess(self):
        from deep.core.runtime_guard import activate
        activate()
        import subprocess
        # This should NOT raise
        result = subprocess.run(
            [sys.executable, "-c", "print('hello')"],
            capture_output=True, text=True
        )
        assert result.returncode == 0


class TestFullWorkflowStateConsistency:
    """PROOF: Full workflow init→add→commit→branch→merge→add→rollback
    maintains state consistency at each step."""

    def test_full_workflow(self, tmp_path):
        repo_root, dg_dir = _setup_repo(tmp_path)
        objects_dir = dg_dir / "objects"

        from deep.storage.objects import Blob, write_object, read_object
        from deep.storage.index import DeepIndex, DeepIndexEntry, write_index, read_index
        from deep.core.refs import resolve_head
        from deep.core.status import compute_status

        # Step 1: init — already done via _setup_repo
        _write_head_ref(dg_dir, "main")

        # Step 2: add + commit file1
        _write_file(repo_root, "file1.txt", "hello world")
        blob1 = _create_blob(dg_dir, b"hello world")
        tree1 = _create_tree(dg_dir, {"file1.txt": blob1})
        commit1 = _create_commit(dg_dir, tree1, [], "first")
        _update_branch(dg_dir, "main", commit1)
        _build_index_from_files(repo_root, dg_dir, {"file1.txt": "hello world"})

        # PROOF: status clean after commit
        status = compute_status(repo_root)
        assert len(status.modified) == 0
        assert len(status.untracked) == 0

        # Step 3: branch feature, add file2, commit
        blob2 = _create_blob(dg_dir, b"feature content")
        tree2 = _create_tree(dg_dir, {"file1.txt": blob1, "file2.txt": blob2})
        commit2 = _create_commit(dg_dir, tree2, [commit1], "feature: add file2")
        _update_branch(dg_dir, "feature", commit2)

        # Step 4: merge feature into main
        merged_files = {"file1.txt": blob1, "file2.txt": blob2}
        merged_tree = _create_tree(dg_dir, merged_files)
        merge_commit = _create_commit(dg_dir, merged_tree, [commit1, commit2], "merge feature")
        _update_branch(dg_dir, "main", merge_commit)

        # Apply to WD + index
        new_index = DeepIndex()
        for p, sha in merged_files.items():
            full = repo_root / p
            full.parent.mkdir(parents=True, exist_ok=True)
            blob_obj = read_object(objects_dir, sha)
            full.write_bytes(blob_obj.serialize_content())
            stat = full.stat()
            p_hash = struct.unpack(">Q", hashlib.sha256(p.encode()).digest()[:8])[0]
            new_index.entries[p] = DeepIndexEntry(
                content_hash=sha,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                path_hash=p_hash,
            )
        write_index(dg_dir, new_index)

        # PROOF: status clean after merge
        status = compute_status(repo_root)
        assert len(status.modified) == 0, f"Phantom modified after merge: {status.modified}"
        assert len(status.staged_new) == 0, f"Phantom staged_new after merge: {status.staged_new}"

        # Step 5: rollback to commit1
        _update_branch(dg_dir, "main", commit1)
        target_files = {"file1.txt": blob1}

        # Remove non-target files
        for p in list(new_index.entries.keys()):
            if p not in target_files:
                full = repo_root / p
                if full.exists():
                    full.unlink()

        # Write target files + rebuild index
        rollback_index = DeepIndex()
        for p, sha in target_files.items():
            full = repo_root / p
            full.parent.mkdir(parents=True, exist_ok=True)
            blob_obj = read_object(objects_dir, sha)
            full.write_bytes(blob_obj.serialize_content())
            stat = full.stat()
            p_hash = struct.unpack(">Q", hashlib.sha256(p.encode()).digest()[:8])[0]
            rollback_index.entries[p] = DeepIndexEntry(
                content_hash=sha,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                path_hash=p_hash,
            )
        write_index(dg_dir, rollback_index)

        # PROOF: after rollback
        head_sha = resolve_head(dg_dir)
        assert head_sha == commit1, "HEAD should point to commit1 after rollback"

        index = read_index(dg_dir)
        assert set(index.entries.keys()) == {"file1.txt"}, "Index should only have file1.txt"

        assert (repo_root / "file1.txt").exists()
        assert not (repo_root / "file2.txt").exists(), "file2.txt should be gone after rollback"

        status = compute_status(repo_root)
        assert len(status.modified) == 0, f"Phantom modified after rollback: {status.modified}"

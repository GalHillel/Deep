"""
deep.core.diff
~~~~~~~~~~~~~~~~~~~~
Diff engine using Python's :mod:`difflib`.

Compares file content between the working directory and the index (staged
version), or between two blobs.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Optional

from deep.storage.index import read_index
from deep.storage.objects import Blob, read_object
from deep.core.constants import DEEP_DIR

def robust_decode(raw_bytes: bytes) -> str:
    """Decode bytes gracefully, handling UTF-16 BOMs and UTF-8."""
    if not raw_bytes:
        return ""
    if raw_bytes.startswith((b'\xff\xfe', b'\xfe\xff')):
        try:
            return raw_bytes.decode('utf-16')
        except UnicodeDecodeError:
            pass
    try:
        return raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return raw_bytes.decode('utf-8', errors='replace')



def diff_lines(
    old_lines: list[str],
    new_lines: list[str],
    old_label: str = "a",
    new_label: str = "b",
) -> str:
    """Return a unified diff string between two lists of lines.

    Args:
        old_lines: Lines of the old version.
        new_lines: Lines of the new version.
        old_label: Label for the old file.
        new_label: Label for the new file.

    Returns:
        Unified diff as a string (may be empty if files are identical).
    """
    result = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=old_label,
        tofile=new_label,
        lineterm="",
    )
    return "\n".join(result)


def diff_blob_vs_file(
    objects_dir: Path,
    blob_sha: str,
    file_path: Path,
    rel_path: str,
) -> Optional[str]:
    """Diff an indexed blob against the current working-directory file.

    Args:
        objects_dir: Path to the objects directory.
        blob_sha:    SHA of the indexed blob.
        file_path:   Absolute path to the working-directory file.
        rel_path:    Relative path for display labels.

    Returns:
        Unified diff string, or ``None`` if the files are identical.
    """
    obj = read_object(objects_dir, blob_sha)
    if not isinstance(obj, Blob):
        return None

    try:
        old_text = robust_decode(obj.data)
    except Exception:
        old_text = ""

    try:
        new_bytes = file_path.read_bytes()
        new_text = robust_decode(new_bytes)
    except FileNotFoundError:
        new_text = ""

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    if old_lines == new_lines:
        if old_text != new_text:
            # Line endings changed but content is identical
            return f"--- a/{rel_path}\n+++ b/{rel_path}\n@@ -0,0 +0,0 @@\n Note: Line endings changed (e.g. CRLF -> LF)"
        return None

    return diff_lines(
        old_lines,
        new_lines,
        old_label=f"a/{rel_path}",
        new_label=f"b/{rel_path}",
    )

def diff_blobs(
    objects_dir: Path,
    sha_a: str,
    sha_b: str,
    rel_path: str,
) -> Optional[str]:
    """Diff two blobs by their SHAs.

    Args:
        objects_dir: Path to the objects directory.
        sha_a:       SHA of the first (old) blob.
        sha_b:       SHA of the second (new) blob.
        rel_path:    Relative path for display labels.

    Returns:
        Unified diff string, or ``None`` if identical.
    """
    if sha_a == sha_b:
        return None

    try:
        obj_a = read_object(objects_dir, sha_a) if sha_a else None
        obj_b = read_object(objects_dir, sha_b) if sha_b else None
        try:
            old_text = robust_decode(obj_a.data) if isinstance(obj_a, Blob) else ""
        except Exception:
            old_text = ""

        try:
            new_text = robust_decode(obj_b.data) if isinstance(obj_b, Blob) else ""
        except Exception:
            new_text = ""
        
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        
        from_label = f"a/{rel_path}" if sha_a else "/dev/null"
        to_label = f"b/{rel_path}" if sha_b else "/dev/null"
        
        return diff_lines(old_lines, new_lines, from_label, to_label)
    except Exception:
        return None


def _get_tree_entries_recursive(objects_dir: Path, tree_sha: str, prefix: str = "") -> dict[str, str]:
    """Recursively collect all {rel_path: sha} from a tree."""
    from deep.storage.objects import Tree, read_object
    files = {}
    try:
        obj = read_object(objects_dir, tree_sha)
        if not isinstance(obj, Tree):
            return {}
        for entry in obj.entries:
            rel_path = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.mode == "40000":
                files.update(_get_tree_entries_recursive(objects_dir, entry.sha, rel_path))
            else:
                files[rel_path] = entry.sha
    except Exception:
        pass
    return files


def diff_trees(dg_dir: Path, sha1: str, sha2: str) -> list[tuple[str, str]]:
    """Compute diffs between two tree/commit SHAs.

    Args:
        dg_dir: Path to .deep
        sha1:   Old tree/commit SHA
        sha2:   New tree/commit SHA

    Returns:
        List of (rel_path, diff_text)
    """
    from deep.storage.objects import Commit, read_object
    objs_dir = dg_dir / "objects"
    
    def get_tree(s):
        o = read_object(objs_dir, s)
        return o.tree_sha if isinstance(o, Commit) else s

    t1 = get_tree(sha1)
    t2 = get_tree(sha2)
    
    files1 = _get_tree_entries_recursive(objs_dir, t1)
    files2 = _get_tree_entries_recursive(objs_dir, t2)
    
    all_paths = sorted(set(files1.keys()) | set(files2.keys()))
    diffs = []
    
    for path in all_paths:
        s1 = files1.get(path)
        s2 = files2.get(path)
        if s1 != s2:
            res = diff_blobs(objs_dir, s1, s2, path)
            if res:
                diffs.append((path, res))
    return diffs


def diff_working_tree(repo_root: Path) -> list[tuple[str, str]]:
    """Compute diffs for all tracked files that differ from the index, and untracked files.

    Args:
        repo_root: Repository root directory.

    Returns:
        List of ``(rel_path, diff_text)`` tuples for files that differ.
    """
    from deep.core.constants import DEEP_DIR
    from deep.core.status import compute_status
    dg_dir = repo_root / DEEP_DIR
    objs_dir = dg_dir / "objects"
    index = read_index(dg_dir)

    diffs: list[tuple[str, str]] = []
    for rel_path, entry in sorted(index.entries.items()):
        file_path = repo_root / rel_path
        result = diff_blob_vs_file(objs_dir, entry.content_hash, file_path, rel_path)
        if result is not None:
            diffs.append((rel_path, result))

    # Also include completely untracked files so the UI displays them as additions!
    status = compute_status(repo_root)
    for rel_path in sorted(status.untracked):
        file_path = repo_root / rel_path
        try:
            new_text = robust_decode(file_path.read_bytes())
            res = diff_lines([], new_text.splitlines(), f"/dev/null", f"b/{rel_path}")
            if res:
                diffs.append((rel_path, res))
        except Exception:
            pass

    return diffs

def diff_index_vs_head(repo_root: Path) -> list[tuple[str, str]]:
    """Compute diffs for staged files (Index vs HEAD)."""
    from deep.core.constants import DEEP_DIR
    from deep.core.refs import resolve_head
    from deep.storage.objects import Commit, read_object
    dg_dir = repo_root / DEEP_DIR
    objs_dir = dg_dir / "objects"
    index = read_index(dg_dir)
    
    head_sha = resolve_head(dg_dir)
    head_files = {}
    if head_sha:
        try:
            commit = read_object(objs_dir, head_sha)
            if isinstance(commit, Commit):
                head_files = _get_tree_entries_recursive(objs_dir, commit.tree_sha)
        except Exception:
            pass
            
    diffs = []
    all_paths = sorted(set(index.entries.keys()) | set(head_files.keys()))
    for path in all_paths:
        s1 = head_files.get(path)
        s2 = index.entries[path].content_hash if path in index.entries else None
        if s1 != s2:
            res = diff_blobs(objs_dir, s1, s2, path)
            if res:
                diffs.append((path, res))
    return diffs

"""
deep_git.core.diff
~~~~~~~~~~~~~~~~~~~~
Diff engine using Python's :mod:`difflib`.

Compares file content between the working directory and the index (staged
version), or between two blobs.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Optional

from deep_git.core.index import read_index
from deep_git.core.objects import Blob, read_object
from deep_git.core.repository import DEEP_GIT_DIR


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
        old_text = obj.data.decode("utf-8", errors="replace")
    except Exception:
        old_text = ""

    try:
        new_text = file_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        new_text = ""

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    if old_lines == new_lines:
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
        
        text_a = obj_a.data.decode("utf-8", errors="replace") if isinstance(obj_a, Blob) else ""
        text_b = obj_b.data.decode("utf-8", errors="replace") if isinstance(obj_b, Blob) else ""
        
        old_lines = text_a.splitlines()
        new_lines = text_b.splitlines()
        
        return diff_lines(old_lines, new_lines, f"a/{rel_path}", f"b/{rel_path}")
    except Exception:
        return None


def diff_working_tree(repo_root: Path) -> list[tuple[str, str]]:
    """Compute diffs for all tracked files that differ from the index.

    Args:
        repo_root: Repository root directory.

    Returns:
        List of ``(rel_path, diff_text)`` tuples for files that differ.
    """
    dg_dir = repo_root / DEEP_GIT_DIR
    objects_dir = dg_dir / "objects"
    index = read_index(dg_dir)

    diffs: list[tuple[str, str]] = []
    for rel_path, entry in sorted(index.entries.items()):
        file_path = repo_root / rel_path
        result = diff_blob_vs_file(objects_dir, entry.sha, file_path, rel_path)
        if result is not None:
            diffs.append((rel_path, result))

    return diffs

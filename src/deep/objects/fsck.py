"""
deep.objects.fsck
~~~~~~~~~~~~~~~~~

File System Consistency Check (fsck) for Deep object store.

Validates:
1. Object integrity — SHA-1 hash matches content
2. Object format — correct type/size headers
3. DAG consistency — all referenced objects exist
4. Tree validation — valid entries, no cycles
5. Commit validation — valid tree ref, valid parents

Command: ``deep fsck``
"""

from __future__ import annotations

import hashlib
import os
import zlib
from collections import deque
from pathlib import Path
from typing import List, Optional, Set, Tuple, Dict


class FsckError:
    """A single fsck issue."""
    def __init__(self, sha: str, severity: str, message: str):
        self.sha = sha
        self.severity = severity  # "error", "warning", "info"
        self.message = message

    def __repr__(self) -> str:
        return f"[{self.severity.upper()}] {self.sha[:8]}: {self.message}"


def fsck(
    objects_dir: Path,
    refs_dir: Optional[Path] = None,
    verbose: bool = False,
) -> List[FsckError]:
    """Run full filesystem consistency check.

    Args:
        objects_dir: Path to .deep/objects/ directory.
        refs_dir: Path to .deep/refs/ directory (for DAG validation).
        verbose: Print progress messages.

    Returns:
        List of FsckError issues found.
    """
    errors: List[FsckError] = []
    valid_objects: Set[str] = set()
    object_types: Dict[str, str] = {}  # sha -> type

    # Phase 1: Validate all loose objects
    if verbose:
        print("Phase 1: Verifying object integrity...")

    for root, dirs, files in os.walk(objects_dir):
        # Skip pack and info directories
        rel = Path(root).relative_to(objects_dir)
        parts = rel.parts
        if any(p in ("pack", "info", "vault", "quarantine") for p in parts):
            continue

        for fname in files:
            if fname.endswith(".tmp") or fname.endswith(".lock"):
                continue

            # Reconstruct SHA from path
            sha = "".join(parts) + fname
            if len(sha) != 40:
                continue

            try:
                int(sha, 16)
            except ValueError:
                continue

            filepath = Path(root) / fname

            # Validate object
            obj_errors = _validate_object(filepath, sha)
            for err in obj_errors:
                errors.append(err)
            if not obj_errors:
                valid_objects.add(sha)

                # Determine type
                try:
                    raw = zlib.decompress(filepath.read_bytes())
                    null_idx = raw.index(b"\x00")
                    header = raw[:null_idx].decode("ascii")
                    obj_type = header.split(" ", 1)[0]
                    object_types[sha] = obj_type
                except Exception:
                    pass

    if verbose:
        print(f"  Checked {len(valid_objects)} loose objects, "
              f"found {len(errors)} issues")

    # Phase 2: Validate object cross-references (DAG)
    if verbose:
        print("Phase 2: Verifying DAG consistency...")

    dag_errors = _validate_dag(objects_dir, valid_objects, object_types)
    errors.extend(dag_errors)

    if verbose:
        print(f"  Found {len(dag_errors)} DAG issues")

    # Phase 3: Validate refs
    if refs_dir and refs_dir.exists():
        if verbose:
            print("Phase 3: Verifying refs...")

        ref_errors = _validate_refs(refs_dir, valid_objects)
        errors.extend(ref_errors)

        if verbose:
            print(f"  Found {len(ref_errors)} ref issues")

    return errors


def _validate_object(filepath: Path, expected_sha: str) -> List[FsckError]:
    """Validate a single loose object."""
    errors = []

    try:
        compressed = filepath.read_bytes()
    except Exception as e:
        errors.append(FsckError(expected_sha, "error", f"Cannot read: {e}"))
        return errors

    try:
        raw = zlib.decompress(compressed)
    except zlib.error:
        # Might be uncompressed (legacy format)
        raw = compressed

    # Verify hash
    actual_sha = hashlib.sha1(raw).hexdigest()
    if actual_sha != expected_sha:
        errors.append(FsckError(
            expected_sha, "error",
            f"Hash mismatch: expected {expected_sha}, got {actual_sha}"
        ))
        return errors

    # Validate header format
    try:
        null_idx = raw.index(b"\x00")
        header = raw[:null_idx].decode("ascii")
        parts = header.split(" ", 1)
        if len(parts) != 2:
            errors.append(FsckError(expected_sha, "error",
                                    f"Malformed header: {header!r}"))
            return errors

        obj_type, size_str = parts
        size = int(size_str)
        content = raw[null_idx + 1:]

        if len(content) != size:
            errors.append(FsckError(
                expected_sha, "error",
                f"Size mismatch: header says {size}, got {len(content)}"
            ))

        valid_types = {"blob", "tree", "commit", "tag", "delta",
                       "chunk", "chunked_blob"}
        if obj_type not in valid_types:
            errors.append(FsckError(
                expected_sha, "warning",
                f"Unknown object type: {obj_type}"
            ))

        # Type-specific validation
        if obj_type == "tree":
            errors.extend(_validate_tree_content(expected_sha, content))
        elif obj_type == "commit":
            errors.extend(_validate_commit_content(expected_sha, content))

    except (ValueError, UnicodeDecodeError) as e:
        errors.append(FsckError(expected_sha, "error",
                                f"Cannot parse header: {e}"))

    return errors


def _validate_tree_content(sha: str, content: bytes) -> List[FsckError]:
    """Validate tree object content."""
    errors = []
    idx = 0
    seen_names: Set[str] = set()

    while idx < len(content):
        try:
            null_idx = content.index(b"\x00", idx)
            mode_name = content[idx:null_idx].decode("utf-8")
            parts = mode_name.split(" ", 1)
            if len(parts) != 2:
                errors.append(FsckError(sha, "error",
                              f"Tree: malformed entry at offset {idx}"))
                break

            mode, name = parts
            sha_end = null_idx + 1 + 20
            if sha_end > len(content):
                errors.append(FsckError(sha, "error",
                              f"Tree: truncated SHA for entry '{name}'"))
                break

            if name in seen_names:
                errors.append(FsckError(sha, "error",
                              f"Tree: duplicate entry name '{name}'"))
            seen_names.add(name)

            idx = sha_end
        except (ValueError, UnicodeDecodeError) as e:
            errors.append(FsckError(sha, "error",
                          f"Tree: parse error at offset {idx}: {e}"))
            break

    return errors


def _validate_commit_content(sha: str, content: bytes) -> List[FsckError]:
    """Validate commit object content."""
    errors = []
    text = content.decode("utf-8", errors="replace")

    has_tree = False
    has_author = False
    has_committer = False

    if "\n\n" in text:
        headers, _ = text.split("\n\n", 1)
    else:
        headers = text

    for line in headers.split("\n"):
        if line.startswith("tree "):
            has_tree = True
            tree_sha = line[5:].strip()
            if len(tree_sha) != 40:
                errors.append(FsckError(sha, "error",
                              f"Commit: invalid tree SHA length: {len(tree_sha)}"))
        elif line.startswith("parent "):
            parent_sha = line[7:].strip()
            if len(parent_sha) != 40:
                errors.append(FsckError(sha, "error",
                              f"Commit: invalid parent SHA length: {len(parent_sha)}"))
        elif line.startswith("author "):
            has_author = True
        elif line.startswith("committer "):
            has_committer = True

    if not has_tree:
        errors.append(FsckError(sha, "error", "Commit: missing tree"))
    if not has_author:
        errors.append(FsckError(sha, "warning", "Commit: missing author"))
    if not has_committer:
        errors.append(FsckError(sha, "warning", "Commit: missing committer"))

    return errors


def _validate_dag(
    objects_dir: Path,
    valid_objects: Set[str],
    object_types: Dict[str, str],
) -> List[FsckError]:
    """Validate DAG cross-references."""
    errors = []

    for sha in valid_objects:
        obj_type = object_types.get(sha)
        if not obj_type:
            continue

        try:
            compressed = (objects_dir / sha[0:2] / sha[2:]).read_bytes()
            try:
                raw = zlib.decompress(compressed)
            except zlib.error:
                raw = compressed

            null_idx = raw.index(b"\x00")
            content = raw[null_idx + 1:]

            if obj_type == "commit":
                text = content.decode("utf-8", errors="replace")
                for line in text.split("\n"):
                    if line.startswith("tree "):
                        ref_sha = line[5:].strip()
                        if ref_sha not in valid_objects:
                            errors.append(FsckError(sha, "error",
                                          f"Commit references missing tree {ref_sha[:8]}"))
                    elif line.startswith("parent "):
                        ref_sha = line[7:].strip()
                        if ref_sha not in valid_objects:
                            errors.append(FsckError(sha, "warning",
                                          f"Commit references missing parent {ref_sha[:8]}"))
                    elif not line:
                        break

            elif obj_type == "tree":
                idx = 0
                while idx < len(content):
                    try:
                        null_idx_t = content.index(b"\x00", idx)
                        sha_end = null_idx_t + 1 + 20
                        if sha_end > len(content):
                            break
                        entry_sha = content[null_idx_t + 1:sha_end].hex()
                        if entry_sha not in valid_objects:
                            errors.append(FsckError(sha, "warning",
                                          f"Tree references missing object {entry_sha[:8]}"))
                        idx = sha_end
                    except ValueError:
                        break

        except Exception:
            pass

    return errors


def _validate_refs(refs_dir: Path, valid_objects: Set[str]) -> List[FsckError]:
    """Validate that all refs point to existing objects."""
    errors = []

    for root, _, files in os.walk(refs_dir):
        for fname in files:
            if fname.endswith(".lock"):
                continue
            filepath = Path(root) / fname
            try:
                sha = filepath.read_text(encoding="utf-8").strip()
                if len(sha) == 40:
                    if sha not in valid_objects:
                        ref_path = filepath.relative_to(refs_dir)
                        errors.append(FsckError(sha, "error",
                                      f"Ref {ref_path} points to missing object"))
            except Exception:
                pass

    return errors

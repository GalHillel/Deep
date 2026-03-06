import re
from pathlib import Path
from typing import List, Optional, Dict, Tuple

from deep.storage.objects import Commit, Tree, read_object, TreeEntry
from deep.core.merge import find_lca, three_way_merge
from deep.core.refs import update_branch, update_head

import unicodedata

INVALID_WIN_CHARS = r'[\x00-\x1f\\?*<>|:"]'
RESERVED_WIN_NAMES = {
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

def sanitize_filename(name: str) -> str:
    """
    Guarantees a safe filename for Git and all filesystems.
    - Replaces \r, \n, \t and control characters with underscores
    - Normalizes Unicode to NFC
    - Replaces Windows-illegal characters with underscores
    - Strips leading/trailing whitespace and trailing dots
    """
    if not name:
        return "unnamed_file"

    # 1. Unicode Normalization (NFC)
    name = unicodedata.normalize('NFC', name)
    
    # 2. Replace all Windows-illegal and control characters (including \r \n \t) with underscores
    # Note: We do this before stripping to ensure trailing control characters become underscores 
    # and are NOT stripped by name.strip().
    name = re.sub(INVALID_WIN_CHARS, '_', name)
    
    # 3. Strip whitespace and basic cleanup
    name = name.strip()
    
    # 4. Final safety check for empty or dot-only names
    name = name.rstrip('. ')
    if not name:
        return "sanitized_file"
        
    return name

def sanitize_path(path: str) -> Tuple[str, bool]:
    """
    Robustly sanitize a filename/path part for Windows compatibility.
    """
    if not path:
        return path, False
        
    new_path = sanitize_filename(path)
    
    # Handle reserved Windows names (case-insensitive)
    base_name = new_path.split('.')[0].upper()
    if base_name in RESERVED_WIN_NAMES:
        new_path = "_" + new_path
        
    return new_path, new_path != path

def sanitize_tree(objects_dir: Path, tree_sha: str, renamed_log: Dict[str, str], path_prefix: str = "") -> str:
    """Recursively sanitize entries in a tree. Returns new tree SHA."""
    tree = read_object(objects_dir, tree_sha)
    assert isinstance(tree, Tree)
    
    new_entries = []
    changed = False
    
    for entry in tree.entries:
        full_path = f"{path_prefix}/{entry.name}" if path_prefix else entry.name
        new_name, name_changed = sanitize_path(entry.name)
        
        if name_changed:
            new_full_path = f"{path_prefix}/{new_name}" if path_prefix else new_name
            renamed_log[full_path] = new_full_path
            changed = True
        
        obj = read_object(objects_dir, entry.sha)
        new_sha = entry.sha
        if isinstance(obj, Tree):
            # Recurse into subdirectories with updated prefix
            new_sha = sanitize_tree(
                objects_dir, 
                entry.sha, 
                renamed_log, 
                path_prefix=f"{path_prefix}/{new_name}" if path_prefix else new_name
            )
            if new_sha != entry.sha:
                changed = True
        
        new_entries.append(TreeEntry(name=new_name, mode=entry.mode, sha=new_sha))
        
    if not changed:
        return tree_sha
        
    # Maintain sorting by name for Git compatibility
    new_entries.sort(key=lambda e: e.name)
    new_tree = Tree(entries=new_entries)
    return new_tree.write(objects_dir)

def logical_rebase(
    repo_root: Path,
    objects_dir: Path,
    head_sha: str,
    target_sha: str,
    branch_name: Optional[str] = None,
    sanitize_windows: bool = True
) -> Tuple[str, Dict[str, str]]:
    """
    Perform a logical rebase of head_sha onto target_sha.
    Returns (new_HEAD_SHA, renamed_files_log).
    """
    lca_sha = find_lca(objects_dir, head_sha, target_sha)
    renamed_log = {}
    
    # Base starting point
    curr_head = target_sha
    
    # If we are just sanitizing without rebasing (e.g. ff or already on top)
    if lca_sha == head_sha:
        # Fast-forward case
        curr_head = target_sha
        commits_to_apply = []
    elif lca_sha == target_sha:
        # Already on top, but might need sanitization
        commits_to_apply = []
        # We handle this by re-applying the head if needed or just sanitizing it
        # However, logical_rebase usually implies moving commits. 
        # For simplicity, if sanitize_windows is True, we re-apply the local history
        # to ensure all paths are clean.
        curr = head_sha
        while curr and curr != lca_sha:
            commits_to_apply.append(curr)
            c_obj = read_object(objects_dir, curr)
            assert isinstance(c_obj, Commit)
            if not c_obj.parent_shas: break
            curr = c_obj.parent_shas[0]
        commits_to_apply.reverse()
    else:
        # Normal rebase
        commits_to_apply = []
        curr = head_sha
        while curr and curr != lca_sha:
            commits_to_apply.append(curr)
            c_obj = read_object(objects_dir, curr)
            assert isinstance(c_obj, Commit)
            if not c_obj.parent_shas: break
            curr = c_obj.parent_shas[0]
        commits_to_apply.reverse()

    for commit_sha in commits_to_apply:
        c_obj = read_object(objects_dir, commit_sha)
        assert isinstance(c_obj, Commit)
        
        parent_sha = c_obj.parent_shas[0] if c_obj.parent_shas else ""
        parent_tree = ""
        if parent_sha:
            p_obj = read_object(objects_dir, parent_sha)
            assert isinstance(p_obj, Commit)
            parent_tree = p_obj.tree_sha
            
        curr_head_obj = read_object(objects_dir, curr_head)
        assert isinstance(curr_head_obj, Commit)
        curr_tree = curr_head_obj.tree_sha
        
        commit_tree = c_obj.tree_sha
        
        merged_entries, conflicts = three_way_merge(
            objects_dir, parent_tree, curr_tree, commit_tree
        )
        
        if conflicts:
            raise RuntimeError(f"CONFLICT applying commit {commit_sha[:7]}: Conflict in {conflicts[0]}")
            
        merged_tree = Tree(entries=merged_entries)
        merged_tree_sha = merged_tree.write(objects_dir)
        
        if sanitize_windows:
            merged_tree_sha = sanitize_tree(objects_dir, merged_tree_sha, renamed_log)
        
        new_commit = Commit(
            tree_sha=merged_tree_sha,
            parent_shas=[curr_head],
            author=c_obj.author,
            committer=c_obj.committer,
            message=c_obj.message,
            timestamp=c_obj.timestamp,
            timezone=getattr(c_obj, "timezone", "+0000"),
        )
        curr_head = new_commit.write(objects_dir)
        
    # If no commits were applied but we want to sanitize the result anyway
    if not commits_to_apply and sanitize_windows:
        head_obj = read_object(objects_dir, head_sha)
        new_tree_sha = sanitize_tree(objects_dir, head_obj.tree_sha, renamed_log)
        if new_tree_sha != head_obj.tree_sha:
            # We must create a new commit even for "up-to-date" if paths changed
            new_commit = Commit(
                tree_sha=new_tree_sha,
                parent_shas=head_obj.parent_shas,
                author=head_obj.author,
                committer=head_obj.committer,
                message=head_obj.message + " (Windows Path Sanitization)",
                timestamp=head_obj.timestamp,
                timezone=getattr(head_obj, "timezone", "+0000"),
            )
            curr_head = new_commit.write(objects_dir)
        else:
            curr_head = head_sha

    return curr_head, renamed_log

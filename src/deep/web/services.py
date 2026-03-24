"""
deep.web.services
~~~~~~~~~~~~~~~~~~~~~
Enterprise-grade Service layer for the Deep Web Dashboard (Final Overhaul).
"""

from __future__ import annotations
import os
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import argparse
from deep.storage.cache import CacheManager
from deep.core.snapshot import RepositorySnapshot
from deep.ai import analyzer

def api_lang_format(code, language):
    try:
        formatted_code = code
        if language in ['python']:
            try:
                import autopep8
                formatted_code = autopep8.fix_code(code, options={'aggressive': 1})
            except ImportError:
                import ast
                formatted_code = ast.unparse(ast.parse(code))
                
        elif language == 'json':
            import json
            formatted_code = json.dumps(json.loads(code), indent=4)
            
        # Return cleanly so the frontend gets exactly what it needs
        return {"status": "success", "formatted": formatted_code}
    except Exception as e:
        # Fallback to original code so we don't destroy user's work on error
        return {"status": "error", "message": str(e), "formatted": code}

def api_lang_analyze(code, language):
    diagnostics = []
    if language == 'python':
        try:
            import subprocess
            import tempfile
            # Use flake8 for real linting if available
            with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
                f.write(code)
                temp_name = f.name
            
            # Using absolute path for flake8 if it's in the environment. 
            # Note: subprocess.run on windows might need shell=True or finding the full path if not in the PATH of the python process.
            result = subprocess.run(['flake8', temp_name, '--format=%(row)d:%(col)d:%(code)s:%(text)s'], capture_output=True, text=True)
            import os
            try:
                os.remove(temp_name)
            except:
                pass
            
            for line in result.stdout.splitlines():
                parts = line.split(':', 3)
                if len(parts) >= 4:
                    diagnostics.append({
                        "line": int(parts[0]),
                        "column": int(parts[1]),
                        "message": f"[{parts[2]}] {parts[3].strip()}",
                        "severity": 8 if parts[2].startswith('E') or parts[2].startswith('F') else 4 # 8=Error, 4=Warning
                    })
        except Exception:
            pass # Fallback to basic AST or ignore if flake8 missing
            
    return {"status": "success", "diagnostics": diagnostics}

def api_lang_complete(payload):
    try:
        import jedi
        code = payload.get('code', '')
        line = payload.get('line', 1)
        column = payload.get('column', 1) - 1 # Jedi uses 0-based columns
        
        script = jedi.Script(code)
        completions = script.complete(line, column)
        
        results = []
        for c in completions:
            kind_map = {'class': 5, 'function': 2, 'instance': 4, 'module': 8, 'keyword': 13, 'statement': 12} # Monaco CompletionItemKind mapping
            results.append({
                "label": c.name,
                "kind": kind_map.get(c.type, 9), # 9 = Property
                "insertText": c.name,
                "detail": c.type,
                "documentation": c.docstring()
            })
        return {"status": "success", "completions": results}
    except Exception as e:
        return {"status": "error", "message": str(e), "completions": []}

def api_lang_definition(payload):
    try:
        import jedi
        code = payload.get('code', '')
        line = payload.get('line', 1)
        column = payload.get('column', 1) - 1
        
        script = jedi.Script(code)
        definitions = script.goto(line, column)
        
        if definitions:
            d = definitions[0]
            return {
                "status": "success", 
                "definition": {
                    "line": d.line,
                    "column": d.column + 1
                }
            }
        return {"status": "success", "definition": None}
    except Exception:
        return {"status": "error"}

def ns(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)

from deep.core.constants import DEEP_DIR # Keep this for now, as the new DEEP_DIR import is part of a larger block that's not fully replacing the old one.
from deep.core.refs import resolve_head, get_current_branch, list_branches, resolve_revision
from deep.core.repository import find_repo
from deep.storage.index import read_index, write_index
from deep.core.status import compute_status
from deep.core.errors import DeepError
from deep.core.pr import PRManager
from deep.core.issue import IssueManager
from deep.core.diff import diff_working_tree, diff_trees

from deep.commands.add_cmd import run as run_add
from deep.commands.commit_cmd import run as run_commit
from deep.commands.branch_cmd import run as run_branch
from deep.commands.checkout_cmd import run as run_checkout
from deep.commands.merge_cmd import run as run_merge


class DashboardService:
    def __init__(self, dg_dir: Path, repo_root: Path):
        self.dg_dir = dg_dir
        self.repo_root = repo_root
        self.pr_manager = PRManager(dg_dir)
        self.issue_manager = IssueManager(dg_dir)

    def _safe(self, fn: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Wrap all operations in a safety net for the UI."""
        try:
            res = fn(*args, **kwargs)
            return {"success": True, "data": res}
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    # --- File System ---

    def get_tree(self) -> Dict[str, Any]:
        return self._safe(self._get_tree_pinnacle)

    def _get_tree_pinnacle(self) -> Dict[str, Any]:
        tree_dict = {}
        exclude = {".git", "node_modules", DEEP_DIR}
        
        for root, dirs, files in os.walk(self.repo_root):
            dirs[:] = [d for d in dirs if d not in exclude and not d.startswith(".")]
            rel_root = Path(root).relative_to(self.repo_root)
            if str(rel_root) == '.':
                current_level = tree_dict
            else:
                current_level = tree_dict
                for part in rel_root.parts:
                    if part not in current_level:
                        current_level[part] = {"_type": "dir", "children": {}}
                    current_level = current_level[part]["children"]
            for d in dirs:
                if d not in current_level:
                    current_level[d] = {"_type": "dir", "children": {}}
            for f in files:
                current_level[f] = {"_type": "file", "path": (rel_root / f).as_posix()}
        return {"tree": tree_dict}

    def get_file_content(self, filepath: str) -> Dict[str, Any]:
        """Wrap bulletproof fetching in _safe envelope."""
        return self._safe(self._get_file_content_internal, filepath)

    def _get_file_content_internal(self, filepath: str) -> Dict[str, Any]:
        """Internal bulletproof logic."""
        # Prevent path traversal and resolve safely
        clean_path = filepath.lstrip('/').replace('\\', '/')
        full_path = (self.repo_root / clean_path).resolve()
        
        # Security: Ensure path is within repo
        if not str(full_path).startswith(str(self.repo_root)):
            raise ValueError("Path traversal denied")

        if not full_path.exists(): 
            raise FileNotFoundError(f"File not found on disk: {filepath}")
        
        if full_path.is_dir():
            raise IsADirectoryError("Cannot open a directory in the editor.")

        if full_path.stat().st_size > 2 * 1024 * 1024:
            return {"content": "File too large to display (>2MB).", "isBinary": True}

        with open(full_path, 'rb') as f: 
            raw = f.read()

        # Check for Windows BOMs
        is_utf16_le = raw.startswith(b'\xff\xfe')
        is_utf16_be = raw.startswith(b'\xfe\xff')
        is_utf8_bom = raw.startswith(b'\xef\xbb\xbf')

        # Heuristic for binary (contains null bytes and is not UTF-16)
        if b'\0' in raw[:1024] and not (is_utf16_le or is_utf16_be):
            return {"content": "Binary file cannot be displayed.", "isBinary": True}

        if is_utf16_le or is_utf16_be:
            content = raw.decode('utf-16', errors='replace')
        elif is_utf8_bom:
            content = raw[3:].decode('utf-8', errors='replace')
        else:
            content = raw.decode('utf-8', errors='replace')

        return {"content": content, "isBinary": False}

    def get_file(self, path: str) -> Dict[str, Any]:
        """Legacy wrapper for get_file_content."""
        return self.get_file_content(path)

    def save_file_only(self, path: str, content: str) -> Dict[str, Any]:
        """Independent file saving without committing (VSCode parity)."""
        return self._safe(self._save_file_internal, path.lstrip("/"), content)

    def _save_file_internal(self, path: str, content: str) -> Dict[str, Any]:
        if not path: raise ValueError("No file specified")
        full_path = self.repo_root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # Normalize CRLF to LF to prevent double-spacing on Windows
        normalized_content = content.replace('\r\n', '\n')
        full_path.write_text(normalized_content, encoding='utf-8')
        return {"path": path, "status": "success"}

    def create_item(self, path: str, item_type: str) -> Dict[str, Any]:
        """Context-aware item creation (file/folder)."""
        return self._safe(self._create_item_internal, path, item_type)

    def _create_item_internal(self, item_path: str, item_type: str) -> Dict[str, Any]:
        if not item_path: raise ValueError("Path required")
        
        # Security: Normalize path and prevent traversal
        clean_path = item_path.lstrip('/').replace('\\', '/')
        full_path = (self.repo_root / clean_path).resolve()
        
        # Ensure path is within repo
        if not str(full_path).startswith(str(self.repo_root)):
            raise ValueError("Path traversal denied")

        if full_path.exists():
            raise FileExistsError(f"Item already exists: {item_path}")

        if item_type == 'folder':
            # create parents implicitly to support 'sub/sub2/' input
            full_path.mkdir(parents=True, exist_ok=True) 
        elif item_type == 'file':
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            # Standard 'touch' behavior
            full_path.touch() 
        else:
            raise ValueError(f"Invalid item type: {item_type}")

        return {"success": True, "path": item_path}

    def rename_item(self, path: str, new_name: str) -> Dict[str, Any]:
        """Rename a file or folder in the repository."""
        return self._safe(self._rename_item_internal, path, new_name)

    def _rename_item_internal(self, item_path: str, new_name: str) -> Dict[str, Any]:
        if not item_path or not new_name: raise ValueError("Path and new name required")
        
        # Normalize paths
        old_path = (self.repo_root / item_path.lstrip('/').replace('\\', '/')).resolve()
        
        # Calculate new full path (keeping same parent)
        new_path = old_path.parent / new_name
        
        # Security: Ensure paths are within repo
        if not str(old_path).startswith(str(self.repo_root)) or not str(new_path).startswith(str(self.repo_root)):
            raise ValueError("Path traversal denied")

        if not old_path.exists(): raise FileNotFoundError(f"Source not found: {item_path}")
        if new_path.exists(): raise FileExistsError(f"Destination already exists: {new_name}")

        os.rename(str(old_path), str(new_path))
        return {"success": True, "old_path": item_path, "new_path": str(new_path.relative_to(self.repo_root))}

    def delete_item(self, path: str) -> Dict[str, Any]:
        """Delete a file or folder permanently."""
        return self._safe(self._delete_item_internal, path)

    def _delete_item_internal(self, item_path: str) -> Dict[str, Any]:
        if not item_path: raise ValueError("Path required")
        
        import shutil
        full_path = (self.repo_root / item_path.lstrip('/').replace('\\', '/')).resolve()
        
        # Security: Ensure path is within repo
        if not str(full_path).startswith(str(self.repo_root)):
            raise ValueError("Path traversal denied")

        if not full_path.exists(): return {"success": True} # Idempotent

        if full_path.is_dir():
            shutil.rmtree(str(full_path))
        else:
            os.remove(str(full_path))
            
        return {"success": True}

    # --- Git Operations ---

    def get_full_status(self) -> Dict[str, Any]:
        return self._safe(self._get_status_internal)

    def _get_status_internal(self) -> Dict[str, Any]:
        status = compute_status(self.repo_root)
        current = get_current_branch(self.dg_dir) or "DETACHED"
        staged_files = status.staged_new + status.staged_modified + status.staged_deleted
        return {
            "branch": current,
            "modified": status.modified,
            "untracked": status.untracked,
            "deleted": status.deleted,
            "staged": staged_files
        }

    # --- Git Operations ---
    def get_graph(self) -> Dict[str, Any]:
        return self._safe(self._get_graph_internal)

    def _get_graph_internal(self) -> Dict[str, Any]:
        from deep.storage.objects import read_object, Commit
        from deep.core.refs import list_branches, get_branch, list_tags, resolve_head, resolve_revision
        objects_dir = self.dg_dir / "objects"
        commits = []; refs = {}
        for b in list_branches(self.dg_dir):
            sha = get_branch(self.dg_dir, b)
            if sha: refs[f"branch:{b}"] = sha
        for t in list_tags(self.dg_dir):
            sha = resolve_revision(self.dg_dir, t)
            if sha: refs[f"tag:{t}"] = sha
        head = resolve_head(self.dg_dir)
        if head:
            refs["HEAD"] = head
            queue = [head]; visited = set()
            while queue and len(commits) < 100:
                sha = queue.pop(0)
                if sha in visited: continue
                visited.add(sha)
                try:
                    obj = read_object(objects_dir, sha)
                    if isinstance(obj, Commit):
                        commits.append({"sha": sha, "author": obj.author, "message": obj.message, "parents": obj.parent_shas, "timestamp": obj.timestamp})
                        queue.extend(obj.parent_shas)
                except: continue
        return {"commits": commits, "refs": refs}

    def get_graph_v2(self) -> Dict[str, Any]:
        """High-performance V2 graph retrieval from cache."""
        return self._safe(self._get_graph_v2_internal)

    def _get_graph_v2_internal(self) -> Dict[str, Any]:
        cm = CacheManager(self.dg_dir)
        graph = cm.get_commit_graph()
        
        # Get refs (Refs are always live)
        old_res = self._get_graph_internal()
        refs = old_res.get("refs", {})

        if graph:
            return {"commits": graph, "refs": refs, "v": 2, "source": "cache"}
        
        # If cache missing, use V1 but mark it as V2-attempted
        return {**old_res, "v": 2, "source": "v1_fallback"}

    def get_commit_details(self, sha: str) -> Dict[str, Any]:
        """Fetch full commit metadata and list of changed files."""
        return self._safe(self._get_commit_details_internal, sha)

    def _get_commit_details_internal(self, sha: str) -> Dict[str, Any]:
        from deep.storage.objects import read_object, Commit
        from deep.core.diff import diff_trees
        
        objs_dir = self.dg_dir / "objects"
        commit = read_object(objs_dir, sha)
        if not isinstance(commit, Commit):
            raise ValueError(f"Object {sha} is not a commit")
        
        # Compute files changed by diffing with first parent
        files_changed = []
        if commit.parent_shas:
            parent_sha = commit.parent_shas[0]
            diffs = diff_trees(self.dg_dir, parent_sha, sha)
            for path, diff_text in diffs:
                # Basic stats
                added = diff_text.count('\n+') - diff_text.count('\n+++')
                deleted = diff_text.count('\n-') - diff_text.count('\n---')
                files_changed.append({
                    "path": path,
                    "added": added,
                    "deleted": deleted,
                    "type": "modified"
                })
        else:
            # Initial commit: diff against empty tree
            from deep.core.diff import _get_tree_entries_recursive
            entries = _get_tree_entries_recursive(objs_dir, commit.tree_sha)
            for path in entries:
                files_changed.append({"path": path, "added": 0, "deleted": 0, "type": "added"})

        return {
            "sha": sha,
            "author": commit.author,
            "message": commit.message,
            "timestamp": commit.timestamp,
            "parents": commit.parent_shas,
            "files": files_changed
        }

    def get_commit_details_v2(self, sha: str) -> Dict[str, Any]:
        """Enhanced V2 commit details with semantic intelligence."""
        return self._safe(self._get_commit_details_v2_internal, sha)

    def _get_commit_details_v2_internal(self, sha: str) -> Dict[str, Any]:
        # Start with V1 data
        base = self._get_commit_details_internal(sha)
        
        from deep.storage.objects import read_object, Commit
        from deep.core.diff import diff_trees
        objs_dir = self.dg_dir / "objects"
        commit = read_object(objs_dir, sha)
        
        # Semantic Enrichment
        intents = set()
        total_complexity = 0.0
        is_breaking = False
        
        if commit.parent_shas:
            parent_sha = commit.parent_shas[0]
            diffs = diff_trees(self.dg_dir, parent_sha, sha)
        else:
            # Initial commit: diff against empty tree
            from deep.core.diff import _get_tree_entries_recursive, diff_blobs
            entries = _get_tree_entries_recursive(objs_dir, commit.tree_sha)
            diffs = []
            for path, blob_sha in entries.items():
                res = diff_blobs(objs_dir, None, blob_sha, path)
                if res: diffs.append((path, res))
        
        if diffs:
            all_diff_text = ""
            for path, diff_text in diffs:
                all_diff_text += diff_text
                # If Python, do deep AST analysis
                if path.endswith(".py"):
                    from deep.core.diff import _get_tree_entries_recursive
                    old_sha = None
                    if commit.parent_shas:
                        parent_commit = read_object(objs_dir, commit.parent_shas[0])
                        old_entries = _get_tree_entries_recursive(objs_dir, parent_commit.tree_sha)
                        old_sha = old_entries.get(path)
                    
                    new_entries = _get_tree_entries_recursive(objs_dir, commit.tree_sha)
                    new_sha = new_entries.get(path)
                    
                    old_src = read_object(objs_dir, old_sha).data.decode('utf-8') if old_sha else ""
                    new_src = read_object(objs_dir, new_sha).data.decode('utf-8') if new_sha else ""
                    
                    ast_data = analyzer.extract_ast_changes(old_src, new_src)
                    intents.update(ast_data.get("intents", []))
                    total_complexity = max(total_complexity, ast_data.get("complexity", 0.0))
            
            # General Classification
            files = [f["path"] for f in base.get("files", [])]
            primary_intent = analyzer.classify_change(files, all_diff_text)
            intents.add(primary_intent)
            
            # SemVer / Breaking Change check
            if "!" in base.get("message", "") or primary_intent == "security":
                is_breaking = True
            if any("breaking" in f.get("type", "").lower() for f in base.get("files", [])):
                is_breaking = True

        base["intent"] = ", ".join(sorted(list(intents))) if intents else "update"
        base["risk"] = total_complexity
        base["semver"] = "MAJOR" if is_breaking else ("MINOR" if "feat" in base["intent"] else "PATCH")
        base["v"] = 2
        return base

    def checkout_branch_forced(self, name: str) -> Dict[str, Any]:
        """Forced checkout to prevent UI stalls."""
        return self._safe(self._checkout_forced_internal, name)

    def _checkout_forced_internal(self, name: str) -> Dict[str, Any]:
        run_checkout(ns(target=name, force=True, branch=False, files=[]))
        return {"status": "success", "branch": name}

    def create_branch(self, name: str) -> Dict[str, Any]:
        return self._safe(self._create_branch_internal, name)

    def _create_branch_internal(self, name: str) -> Dict[str, Any]:
        run_branch(ns(name=name, start_point="HEAD", delete=False, files=[]))
        return {"status": "success", "branch": name}

    def merge_branch(self, branch: str) -> Dict[str, Any]:
        return self._safe(self._merge_internal, branch)

    def _merge_internal(self, branch: str) -> Dict[str, Any]:
        run_merge(ns(branch=branch, files=[]))
        return {"status": "success", "message": f"Merged {branch}"}

    def get_diff(self, sha: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
        return self._safe(self._get_diff_internal, sha, path)

    def _get_diff_internal(self, sha: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
        import sys
        import io
        import re
        from deep.storage.objects import read_object, Commit
        from deep.core.diff import diff_blobs, diff_trees, _get_tree_entries_recursive
        
        objs_dir = self.dg_dir / "objects"

        # 1. Specialized Commit-File Diff (for Graph Detail Panel)
        if sha and path:
            commit = read_object(objs_dir, sha)
            if not isinstance(commit, Commit): raise ValueError("Not a commit")
            
            s2 = None
            # Find SHA in this commit's tree
            entries2 = _get_tree_entries_recursive(objs_dir, commit.tree_sha)
            s2 = entries2.get(path)

            s1 = None
            if commit.parent_shas:
                parent = read_object(objs_dir, commit.parent_shas[0])
                if isinstance(parent, Commit):
                    entries1 = _get_tree_entries_recursive(objs_dir, parent.tree_sha)
                    s1 = entries1.get(path)
            
            diff_text = diff_blobs(objs_dir, s1, s2, path) or ""
            return {"diff": diff_text}

        # 2. Standard Working Tree / Staged Diff
        from deep.commands.diff_cmd import run as run_diff
        old_stdout = sys.stdout
        sys.stdout = mystdout = io.StringIO()
        try:
            # If a path is provided but no sha, diff working/staged for that path
            files = [path] if path else []
            run_diff(ns(cached=False, revisions=[], files=files))
            run_diff(ns(cached=True, revisions=[], files=files))
        except Exception:
            pass
        finally:
            sys.stdout = old_stdout
            
        diff_text = mystdout.getvalue()
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        diff_text = ansi_escape.sub('', diff_text)
        return {"diff": diff_text}

    def get_diff_v2(self, sha1: str, sha2: str) -> Dict[str, Any]:
        """High-performance V2 diff retrieval from cache."""
        return self._safe(self._get_diff_v2_internal, sha1, sha2)

    def _get_diff_v2_internal(self, sha1: str, sha2: str) -> Dict[str, Any]:
        cm = CacheManager(self.dg_dir)
        cached_diff = cm.get_diff(sha1, sha2)
        if cached_diff:
            return {"diff": cached_diff, "cached": True, "v": 2}
        
        # Fallback to diff_trees (v1 logic)
        from deep.core.diff import diff_trees
        diffs = diff_trees(self.dg_dir, sha1, sha2)
        combined = "\n".join(d[1] for d in diffs)
        return {"diff": combined, "cached": False, "v": 2, "source": "v1_fallback"}

    def get_branches_list(self) -> Dict[str, Any]:
        """Simple flat list of branch names for dropdowns."""
        return self._safe(self._get_branches_list_internal)

    def _get_branches_list_internal(self) -> List[str]:
        from deep.core.refs import list_branches
        return list_branches(self.dg_dir)

    def get_branches_v2(self) -> Dict[str, Any]:
        """V2 branch list via RepositorySnapshot."""
        return self._safe(self._get_branches_v2_internal)

    def _get_branches_v2_internal(self) -> List[str]:
        snap = RepositorySnapshot(self.repo_root)
        from deep.core.refs import list_branches
        return list_branches(snap.dg_dir)

    # --- Collaboration Hub ---

    def get_prs_local(self) -> Dict[str, Any]:
        return self._safe(self._get_prs_local_internal)

    def _get_prs_local_internal(self) -> Dict[str, Any]:
        prs = self.pr_manager.list_prs()
        return {"prs": [self._serialize_dc(p) for p in prs]}

    def get_issues_local(self) -> Dict[str, Any]:
        return self._safe(self._get_issues_local_internal)

    def _get_issues_local_internal(self) -> Dict[str, Any]:
        issues = self.issue_manager.list_issues()
        return {"issues": [self._serialize_dc(i) for i in issues]}

    def _serialize_dc(self, obj: Any) -> Dict[str, Any]:
        from dataclasses import asdict
        data = asdict(obj)
        # Normalize status -> state for frontend consistency
        if "status" in data:
            data["state"] = data["status"].upper() # VSCode style
        
        # Normalize PR description field
        if "body" in data and "desc" not in data:
            data["desc"] = data["body"]
        
        # Normalize PR reviews from Dict to List for easier frontend mapping
        if "reviews" in data and isinstance(data["reviews"], dict):
            review_list = []
            approvals = 0
            for author, r in data["reviews"].items():
                state = r.get("status", "COMMENTED").upper()
                if state == "APPROVED": approvals += 1
                review_list.append({
                    "reviewer": author,
                    "state": state,
                    "comment": r.get("comment", ""),
                    "timestamp": r.get("timestamp", "")
                })
            data["reviews"] = review_list
            data["isApproved"] = approvals >= data.get("approvals_required", 1)
            
        return data

    def create_pr_enhanced(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._create_pr_enhanced_internal, data)

    def _create_pr_enhanced_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rev_list = [r.strip() for r in data.get("reviewers", "").split(",")] if data.get("reviewers") else []
        pr = self.pr_manager.create_pr(
            title=data.get("title", "Untitled PR"),
            author=data.get("author", "Deep Studio"),
            head=data.get("head", ""),
            base=data.get("base", "main"),
            body=data.get("desc") or data.get("body", ""),
            linked_issue=data.get("issue_id"),
            requested_reviewers=rev_list
        )
        return {"status": "success", "id": pr.id}

    def review_pr(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._review_pr_internal, data)

    def _review_pr_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.pr_manager.add_review(int(data.get("pr_id")), "Deep Studio", data.get("state"), data.get("comment", ""))
        return {"status": "success"}

    def merge_local_pr(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._merge_local_pr_internal, data)

    def _merge_local_pr_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.pr_manager.merge_pr(int(data.get("pr_id")))
        return {"status": "success"}

    def add_pr_comment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._add_pr_comment_internal, data)

    def _add_pr_comment_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.pr_manager.add_thread(int(data.get("pr_id")), "Deep Studio", data.get("text"))
        return {"status": "success"}

    def add_pr_reply(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._add_pr_reply_internal, data)

    def _add_pr_reply_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.pr_manager.add_reply(int(data.get("pr_id")), int(data.get("thread_id")), "Deep Studio", data.get("text"))
        return {"status": "success"}

    def resolve_pr_thread(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._resolve_pr_thread_internal, data)

    def _resolve_pr_thread_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.pr_manager.resolve_thread(int(data.get("pr_id")), int(data.get("thread_id")))
        return {"status": "success"}

    def create_issue(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._create_issue_internal, data)

    def _create_issue_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        issue = self.issue_manager.create_issue(
            title=data.get("title", "Untitled"),
            description=data.get("body", ""),
            type=data.get("type", "task"),
            author=data.get("author", "Deep Studio"),
            priority=data.get("priority", "Medium")
        )
        return {"status": "success", "id": issue.id}

    def manage_issue(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._safe(self._manage_issue_internal, data)

    def _manage_issue_internal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        id = int(data.get("issue_id"))
        action = data.get("action")
        if action == "close": self.issue_manager.close_issue(id)
        elif action == "reopen": self.issue_manager.reopen_issue(id)
        return {"status": "success"}

# Global namespace helper is already defined at line 17.


def api_stage_file(data):
    try:
        from deep.commands import add_cmd

        filepath = data.get("filepath") or data.get("file")

        if not filepath:
            return {"success": False, "error": "Filepath required"}

        add_cmd.run(ns(files=[filepath]))
        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}

def api_unstage_file(data):
    try:
        from deep.core.repository import find_repo
        from deep.core.constants import DEEP_DIR
        from deep.storage.index import read_index, write_index, remove_multiple_from_index, DeepIndexEntry
        from deep.core.refs import resolve_head
        from deep.storage.objects import read_object, Commit
        
        import struct
        import hashlib

        filepath = data.get("filepath") or data.get("file")
        if not filepath: return {"error": "Filepath required"}
        clean_path = filepath.lstrip('/').replace('\\', '/')

        repo_root = find_repo()
        dg_dir = repo_root / DEEP_DIR

        head_sha = resolve_head(dg_dir)
        objects_dir = dg_dir / "objects"
        
        head_files = {}
        if head_sha:
            try:
                commit = read_object(objects_dir, head_sha)
                if isinstance(commit, Commit):
                    from deep.commands.reset_cmd import _get_tree_files
                    head_files = _get_tree_files(objects_dir, commit.tree_sha)
            except Exception: pass
            
        if clean_path in head_files:
            # File existed in HEAD. Restore the index entry to the HEAD version.
            sha = head_files[clean_path]
            idx = read_index(dg_dir)
            idx.entries[clean_path] = DeepIndexEntry(
                content_hash=sha,
                mtime_ns=0,  # Dummy value to force status recalculation
                size=0,
                path_hash=struct.unpack(">Q", hashlib.sha256(clean_path.encode()).digest()[:8])[0]
            )
            write_index(dg_dir, idx)
        else:
            # File is a new addition. Unstaging means dropping it from the index entirely.
            remove_multiple_from_index(dg_dir, [clean_path])
 
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def api_unstage_all():
    try:
        from deep.commands import reset_cmd
        # Native reset HEAD without paths unstages everything
        reset_cmd.run(ns(commit="HEAD", hard=False, soft=False, mixed=True))
        return {"success": True}
    except Exception as e: return {"success": False, "error": str(e)}

def api_discard_file(filepath):
    try:
        import os
        from deep.core.repository import find_repo
        from deep.commands import checkout_cmd
        from deep.core.status import compute_status
        
        if not filepath: return {"success": False, "error": "Filepath required"}
        
        repo_root = find_repo()
        full_path = repo_root / filepath
        clean_path = filepath.replace('\\', '/')

        # 1. Check if the file is completely untracked
        status = compute_status(repo_root)
        is_untracked = clean_path in status.untracked
        
        if is_untracked:
            # Discarding an untracked file means deleting it entirely (VSCode Parity)
            if full_path.exists():
                os.remove(full_path)
        else:
            # 2. For tracked files, restore them from HEAD
            try:
                checkout_cmd.run(ns(target="HEAD", paths=[filepath], force=True))
            except Exception:
                pass # Ignore internal CLI errors if restore fails
                
        return {"success": True}
    except Exception as e: 
        return {"success": False, "error": str(e)}

def api_discard_all():
    try:
        from deep.core.status import compute_status
        from deep.core.repository import find_repo
        from deep.commands import checkout_cmd
        import os, shutil

        repo_root = find_repo()
        status = compute_status(repo_root)

        # 1. Delete untracked files
        for f in status.untracked:
            p = repo_root / f
            if p.exists():
                if p.is_file():
                    os.remove(p)
                elif p.is_dir():
                    shutil.rmtree(p)

        # 2. Revert tracked changes to HEAD
        checkout_cmd.run(ns(target="HEAD", paths=["."], force=True))

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def api_ai_suggest():
    try:
        from deep.core.repository import find_repo
        from deep.ai.assistant import DeepAI
        
        repo_root = find_repo()
        ai = DeepAI(repo_root)
        suggestion = ai.suggest_commit_message()
        
        if suggestion:
            msg = suggestion.text # It's .text in assistant.py AISuggestion
            parts = msg.split('\n', 1)
            title = parts[0].strip()
            body = parts[1].strip() if len(parts) > 1 else ""
            return {"success": True, "data": {"title": title, "body": body}}
        else:
            return {"success": False, "error": "AI could not generate a suggestion."}
    except Exception as e: return {"success": False, "error": str(e)}

def api_stash_push(data=None):
    if data is None: data = {}
    try:
        from deep.commands import stash_cmd
        message = data.get("message", "Studio Stash")
        stash_cmd.run(ns(action="push", message=message))
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def api_stash_pop(data=None):
    if data is None: data = {}
    try:
        from deep.commands import stash_cmd
        stash_cmd.run(ns(action="pop"))
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def perform_commit(filepath, content, message, amend=False):
    try:
        from deep.commands import add_cmd, commit_cmd
        from deep.core.repository import find_repo

        repo_root = find_repo()

        if filepath and content is not None:
            with open(repo_root / filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            add_cmd.run(ns(files=[filepath]))

        commit_cmd.run(ns(
            message=message,
            ai=False,
            allow_empty=True,
            all=False,
            files=[],
            amend=amend
        ))
 
        return {"success": True}
 
    except Exception as e:
        return {"success": False, "error": str(e)}

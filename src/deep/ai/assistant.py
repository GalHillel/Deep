"""
deep.ai.assistant
~~~~~~~~~~~~~~~~~~~~~
Embedded AI Assistant for Deep.

Provides intelligent suggestions for commit messages, code quality,
merge conflict resolution, and branch naming using rule-based heuristics.
No external API dependency — fully self-contained.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from deep.storage.index import read_index
from deep.storage.objects import read_object, Blob, Commit
from deep.core.constants import DEEP_DIR
from deep.core.diff import diff_blob_vs_file
from deep.ai.analyzer import (
    analyze_diff_text,
    classify_change,
    extract_diff_semantics,
    score_complexity,
    ChangeStats,
)


def infer_scope_from_path(file_path: str) -> str:
    path = file_path.lower()

    if "test" in path:
        return "test"
    if "api" in path:
        return "api"
    if "db" in path:
        return "db"
    if "config" in path:
        return "config"
    if "ui" in path or "frontend" in path:
        return "ui"
    if "core" in path:
        return "core"

    return ""


def get_dominant_scope(files: list[str]) -> str:
    """
    Return the most frequent scope across all changed files.
    """
    if not files:
        return ""

    scopes = [infer_scope_from_path(f) for f in files]
    scopes = [s for s in scopes if s]

    if not scopes:
        return ""

    return max(set(scopes), key=scopes.count)


@dataclass
class AISuggestion:
    """A suggestion from the AI assistant."""
    suggestion_type: str  # "commit_msg", "quality", "branch_name", "merge_hint"
    text: str = ""
    confidence: float = 0.0  # 0.0 to 1.0
    details: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


class DeepAI:
    """Rule-based AI assistant for Deep."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        from deep.core.constants import DEEP_DIR
        self.dg_dir = repo_root / (DEEP_DIR or ".deep")
        self.metrics: dict = {
            "suggestions_made": 0,
            "avg_latency_ms": 0.0,
            "avg_confidence": 0.0,
        }
        self._latencies: list[float] = []

    def _record_metric(self, latency_ms: float, confidence: float):
        self._latencies.append(latency_ms)
        self.metrics["suggestions_made"] += 1
        self.metrics["avg_latency_ms"] = sum(self._latencies) / len(self._latencies)
        total_conf = self.metrics.get("_total_conf", 0.0) + confidence
        self.metrics["_total_conf"] = total_conf
        self.metrics["avg_confidence"] = total_conf / self.metrics["suggestions_made"]

    def _get_staged_diff(self) -> tuple[str, ChangeStats]:
        """Compute the diff between HEAD and Index."""
        from deep.core.refs import resolve_head
        from deep.core.diff import diff_blobs
        from deep.web.dashboard import _tree_entries_flat
        
        objects_dir = self.dg_dir / "objects"
        index = read_index(self.dg_dir)
        head_sha = resolve_head(self.dg_dir)
        head_entries = {}
        if head_sha:
            try:
                head_commit = read_object(objects_dir, head_sha)
                if isinstance(head_commit, Commit):
                    head_entries = _tree_entries_flat(objects_dir, head_commit.tree_sha)
            except Exception:
                pass

        all_diff = ""
        stats = ChangeStats()
        for rel_path, entry in index.entries.items():
            ext = Path(rel_path).suffix.lstrip(".")
            stats.file_types[ext] = stats.file_types.get(ext, 0) + 1
            
            old_sha = head_entries.get(rel_path, "")
            new_sha = entry.content_hash
            
            if old_sha == new_sha:
                continue
                
            try:
                diff_text = diff_blobs(objects_dir, old_sha, new_sha, rel_path)
                if diff_text:
                    added, removed = analyze_diff_text(diff_text)
                    stats.lines_added += added
                    stats.lines_removed += removed
                    
                    if not old_sha:
                        stats.files_added += 1
                    elif not new_sha:
                        stats.files_deleted += 1
                    else:
                        stats.files_modified += 1
                        
                    all_diff += diff_text + "\n"
                else:
                    # Likely a new file if old_sha is empty
                    if not old_sha:
                        stats.files_added += 1
                    else:
                        stats.files_modified += 1
            except Exception:
                stats.files_added += 1
                
        # Handle deleted files (in HEAD but not in Index)
        for rel_path in head_entries:
            if rel_path not in index.entries:
                stats.files_deleted += 1
                
        return all_diff, stats

    def suggest_commit_message(self) -> AISuggestion:
        """Generate a commit message suggestion from staged changes."""
        start = time.perf_counter()

        all_diff, stats = self._get_staged_diff()
        index = read_index(self.dg_dir)
        staged_files = list(index.entries.keys())

        if not stats.total_files and not all_diff:
            latency = (time.perf_counter() - start) * 1000
            self._record_metric(latency, 0.1)
            return AISuggestion("commit_msg", "chore: no changes staged", 0.1)

        # 1. Handle infrastructure files FIRST
        infra_map = {
            "requirements.txt": "chore(deps): update dependencies",
            "package.json": "chore(deps): update dependencies",
            "pipfile": "chore(deps): update dependencies",
            "poetry.lock": "chore(deps): update dependencies",
            ".gitignore": "chore(config): update ignore rules",
            ".dockerignore": "chore(config): update ignore rules",
        }
        
        for f in staged_files:
            base = Path(f).name.lower()
            if base in infra_map:
                latency = (time.perf_counter() - start) * 1000
                self._record_metric(latency, 0.95)
                return AISuggestion("commit_msg", infra_map[base], 0.95, [f"Detected infra file: {f}"], latency)

        # 2. Run semantic extraction
        semantics = extract_diff_semantics(all_diff)
        
        # 3. Change Magnitude Scoring (Phase 3)
        total_lines = stats.lines_added + stats.lines_removed
        if total_lines < 20:
            magnitude = "low"
        elif total_lines <= 100:
            magnitude = "medium"
        else:
            magnitude = "high"

        # 4. Infer Scope
        scope = get_dominant_scope(staged_files)
        scope_part = f"({scope})" if scope else ""

        # 5. Message Decision Tree (Phase 5)
        candidates = []

        if semantics["breaking_change"]:
            candidates.append((f"refactor!{scope_part}: breaking change in {scope or 'system'}", 0.90))
        if semantics["new_files"] and not any([semantics["logic_changes"], semantics["condition_changes"], semantics["deleted_files"]]):
            candidates.append((f"feat{scope_part}: add new functionality", 0.85))
        if semantics["deleted_files"] and not any([semantics["logic_changes"], semantics["condition_changes"], semantics["new_files"]]):
            candidates.append((f"refactor{scope_part}: remove obsolete components", 0.85))
        if semantics["exceptions_added"]:
            candidates.append((f"fix{scope_part}: improve error handling", 0.80))
        if semantics["logic_changes"] or semantics["condition_changes"]:
            if semantics["functions"]:
                func_name = semantics["functions"][0]
                candidates.append((f"fix{scope_part}: update {func_name} logic", 0.80))
            else:
                candidates.append((f"fix{scope_part}: adjust application logic", 0.80))
        if semantics["imports_added"]:
            candidates.append((f"chore{scope_part}: add required dependencies", 0.75))
        if semantics["classes"]:
            cls_name = semantics["classes"][0]
            candidates.append((f"refactor{scope_part}: update {cls_name} implementation", 0.85))

        # 10. Multi-file
        if len(staged_files) > 1:
            change_type = classify_change(staged_files, all_diff)
            candidates.append((f"{change_type}{scope_part}: update {len(staged_files)} files", 0.60))

        # 11. Fallback
        change_type = classify_change(staged_files, all_diff)
        candidates.append((f"{change_type}{scope_part}: update system components", 0.50))

        # Phase 8: Anti-Generic Guard
        vague_patterns = [
            "update files", "modify code", "update system components", 
            f"update {len(staged_files)} files", "update code"
        ]
        
        msg, confidence = candidates[-1]
        for cand_msg, cand_conf in candidates:
            if not any(v in cand_msg for v in vague_patterns):
                msg, confidence = cand_msg, cand_conf
                break

        # Adjust confidence based on magnitude for large refactors
        if magnitude == "high" and confidence > 0.7:
            confidence = min(0.99, confidence + 0.05)

        # 6. Formatting Rules
        msg = msg[:72].lower()

        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, confidence)
        
        details = [
            f"Magnitude: {magnitude} ({total_lines} lines)",
            f"Semantics: {semantics}",
            f"Files: {len(staged_files)}"
        ]

        return AISuggestion("commit_msg", msg, confidence, details, latency)


    def analyze_quality(self) -> AISuggestion:
        """Analyze staged files for code quality issues."""
        start = time.perf_counter()
        warnings: list[str] = []

        index = read_index(self.dg_dir)
        objects_dir = self.dg_dir / "objects"

        for rel_path, entry in index.entries.items():
            try:
                obj = read_object(objects_dir, entry.content_hash)
                if isinstance(obj, Blob):
                    content = obj.data.decode("utf-8", errors="replace")
                    complexity = score_complexity(content)
                    if complexity > 0.7:
                        warnings.append(f"⚠ High complexity ({complexity:.0%}): {rel_path}")

                    lines = content.splitlines()
                    if len(lines) > 500:
                        warnings.append(f"⚠ Large file ({len(lines)} lines): {rel_path}")

                    for i, line in enumerate(lines[:200], 1):
                        if line.rstrip() != line:
                            warnings.append(f"⚠ Trailing whitespace: {rel_path}:{i}")
                            break
            except Exception:
                pass

        if not warnings:
            text = "✅ All staged files pass quality checks"
            confidence = 0.95
        else:
            text = f"Found {len(warnings)} quality issue(s)"
            confidence = 0.8

        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, confidence)
        return AISuggestion("quality", text, confidence, warnings, latency)

    def suggest_branch_name(self, description: str = "") -> AISuggestion:
        """Suggest a branch name based on staged changes or a description."""
        start = time.perf_counter()

        if description:
            words = description.lower().split()
            slug = "-".join(w for w in words[:4] if w.isalnum())
            msg = f"feature/{slug}" if slug else "feature/new-branch"
            confidence = 0.7
        else:
            index = read_index(self.dg_dir)
            files = list(index.entries.keys())
            keywords = []
            for f in files[:5]:
                parts = Path(f).stem.split("_")
                keywords.extend(parts[:2])
            slug = "-".join(keywords[:3]).lower()
            msg = f"feature/{slug}" if slug else "feature/update"
            confidence = 0.5

        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, confidence)
        return AISuggestion("branch_name", msg, confidence, [], latency)

    def merge_hint(self, branch_a: str, branch_b: str) -> AISuggestion:
        print(f"DEBUG: merge_hint({branch_a}, {branch_b})")
        """Predict merge outcomes by simulating a merge between two branches."""
        start = time.perf_counter()
        details = [f"Simulating merge: {branch_a} into {branch_b}"]
        
        from deep.core.refs import get_branch, resolve_head
        from deep.storage.objects import read_object, Commit
        
        sha_a = get_branch(self.dg_dir, branch_a) or branch_a
        sha_b = get_branch(self.dg_dir, branch_b) or branch_b
        
        if len(sha_a) < 40: sha_a = resolve_head(self.dg_dir) # default
        
        # 1. Simplified Merge Base: Walk back from A and see if any parent is in B's history
        def get_history(sha):
            hist = set()
            q = [sha]
            while q:
                s = q.pop(0)
                if s in hist: continue
                hist.add(s)
                try:
                    c = read_object(self.dg_dir / "objects", s)
                    if isinstance(c, Commit): q.extend(c.parent_shas)
                except: pass
            return hist

        hist_b = get_history(sha_b)
        base_sha = None
        q = [sha_a]
        visited = set()
        while q:
            s = q.pop(0)
            if s in hist_b:
                base_sha = s
                break
            if s in visited: continue
            visited.add(s)
            try:
                c = read_object(self.dg_dir / "objects", s)
                if isinstance(c, Commit): q.extend(c.parent_shas)
            except: pass
            
        if not base_sha:
            return AISuggestion("merge_hint", "No common ancestor found.", 0.5, ["Check if branches belong to the same repository."], 0.0)

        # 2. Compare modified files
        from deep.web.dashboard import _tree_entries_flat
        def get_entries(sha):
            c = read_object(self.dg_dir / "objects", sha)
            return _tree_entries_flat(self.dg_dir / "objects", c.tree_sha) if isinstance(c, Commit) else {}
            
        entries_base = get_entries(base_sha)
        entries_a = get_entries(sha_a)
        entries_b = get_entries(sha_b)
        
        mod_a = {p for p, s in entries_a.items() if entries_base.get(p) != s}
        mod_b = {p for p, s in entries_b.items() if entries_base.get(p) != s}
        
        overlap = mod_a & mod_b
        if not overlap:
            latency = (time.perf_counter() - start) * 1000
            confidence = 0.95
            self._record_metric(latency, confidence)
            return AISuggestion(
                suggestion_type="merge_hint",
                text=f"✅ Merge of {branch_a} into {branch_b} looks clean (no overlapping file changes)",
                confidence=confidence,
                details=[
                    f"Simulating merge: {branch_a} into {branch_b}",
                    f"Merge base identified at {base_sha[:7]}",
                    "No overlapping file modifications detected."
                ],
                latency_ms=latency
            )
        else:
            text = f"⚠ Potential conflicts in {len(overlap)} file(s)"
            confidence = 0.8
            for p in list(overlap)[:3]:
                details.append(f"Conflict risk: {p}")
            if len(overlap) > 3:
                details.append(f"...and {len(overlap)-3} more")

        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, confidence)
        return AISuggestion("merge_hint", text, confidence, details, latency)

    def branch_recommendations(self) -> AISuggestion:
        """Suggest branch pruning and cleanup."""
        start = time.perf_counter()
        from deep.core.refs import list_branches, resolve_head
        branches = list_branches(self.dg_dir)
        head = resolve_head(self.dg_dir)
        
        details = []
        if len(branches) > 10:
            details.append(f"Tip: You have {len(branches)} branches. Consider pruning old ones.")
            
        # Implementation placeholder
        details.append("Tip: Use `deep branch -d` for merged branches")
        
        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, 0.7)
        return AISuggestion("branch_mgmt", "Branch Hygiene Recommendations", 0.7, details, latency)

    def review_changes(self) -> AISuggestion:
        """Perform a deep AI code review of STAGED changes (Index vs HEAD)."""
        start = time.perf_counter()
        
        all_diff, stats = self._get_staged_diff()
        
        findings: list[str] = []
        if all_diff:
            lower_diff = all_diff.lower()
            if "todo" in lower_diff:
                findings.append("✎ TODO found in changes")
            if "api_key" in lower_diff or "secret" in lower_diff or "password" in lower_diff:
                findings.append("🔒 Sensitive keyword found in changes")
            if "print(" in lower_diff:
                findings.append("✎ Debug print remains in changes")

        # Summary heuristics
        if stats.lines_removed > stats.lines_added + 100:
            findings.append(f"⚠ Large deletion alert (-{stats.lines_removed} lines)")
        
        if not findings:
            text = "✅ No critical issues found in staged changes"
            confidence = 0.9
        else:
            text = f"AI Review: Found {len(findings)} suggestions"
            confidence = 0.85

        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, confidence)
        return AISuggestion("review", text, confidence, findings, latency)

    def predict_conflicts_pre_push(self, target_branch: str = "main") -> AISuggestion:
        """Predict if pushing the current HEAD will cause conflicts on the remote."""
        start = time.perf_counter()
        # In Hyper Reality Mode, we simulate a 'p2p-push-dry-pass'
        hint = self.merge_hint("HEAD", target_branch)
        
        latency = (time.perf_counter() - start) * 1000
        # Metric is already recorded by self.merge_hint() above
        
        # Wrap the merge hint in push context
        text = f"Pre-push Prediction: {hint.text}"
        details = [f"Target: {target_branch}"] + hint.details
        return AISuggestion("predict_push", text, hint.confidence, details, latency)

    def cross_repo_analysis(self) -> AISuggestion:
        """Scan sibling repositories for dependency correlations and shared modules."""
        start = time.perf_counter()
        findings = []
        
        try:
            parent = self.repo_root.parent
            for path in parent.iterdir():
                if path.is_dir() and path != self.repo_root:
                    if (path / DEEP_DIR).exists():
                        findings.append(f"Dependency Correlation: Found sibling repo '{path.name}'")
                        # Heuristic: Check for common package files
                        if (path / "package.json").exists() and (self.repo_root / "package.json").exists():
                            findings.append(f"   Note: Both repos share 'package.json' - potential JS workspace linkage.")
                        if (path / "requirements.txt").exists() and (self.repo_root / "requirements.txt").exists():
                            findings.append(f"   Note: Both repos share 'requirements.txt' - potential Python dependency overlap.")
                        if (path / "pyproject.toml").exists() and (self.repo_root / "pyproject.toml").exists():
                            findings.append(f"   Note: Both repos share 'pyproject.toml'.")
        except Exception:
            pass
            
        if not findings:
            text = "✅ No immediate cross-repo dependency conflicts detected"
            confidence = 0.9
        else:
            text = f"Detected {len(findings)//2 + 1} cross-project linkages"
            confidence = 0.7
            
        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, confidence)
        return AISuggestion("cross_repo", text, confidence, findings, latency)

    def get_metrics(self) -> dict:
        """Return AI performance metrics."""
        return {k: v for k, v in self.metrics.items() if not k.startswith("_")}


    def suggest_refactors(self) -> list[AISuggestion]:
        """Analyze staged files and suggest specific refactorings (UI friendly)."""
        changes = self.suggest_refactor_changes()
        suggestions = []
        for c in changes:
            suggestions.append(AISuggestion(
                suggestion_type="refactor",
                text=f"Refactor ({c.type}): {c.file_path}",
                confidence=0.8,
                details=[c.description, f"Proposed: {c.replacement}"]
            ))
        return suggestions

    def suggest_refactor_changes(self) -> list[RefactorChange]:
        """Analyze staged files and return raw RefactorChange objects (mutation friendly)."""
        from deep.ai.refactor import RefactorEngine, RefactorChange
        engine = RefactorEngine()
        
        all_changes: list[RefactorChange] = []
        index = read_index(self.dg_dir)
        objects_dir = self.dg_dir / "objects"
        
        for rel_path, entry in index.entries.items():
            try:
                obj = read_object(objects_dir, entry.content_hash)
                if isinstance(obj, Blob):
                    content = obj.data.decode("utf-8", errors="replace")
                    file_changes = engine.suggest_fixes(content, rel_path)
                    all_changes.extend(file_changes)
            except Exception:
                pass
        return all_changes

    def handle_query(self, query: str) -> AISuggestion:
        """Process a natural language query about the repository."""
        query_lower = query.lower()
        start = time.perf_counter()
        
        if "commit" in query_lower or "suggest" in query_lower:
            res = self.suggest_commit_message()
            res.text = f"Suggested message: {res.text}"
            return res
        
        if "quality" in query_lower or "review" in query_lower:
            return self.review_changes()
            
        if "refactor" in query_lower:
            refs = self.suggest_refactors()
            if not refs:
                return AISuggestion("query", "No refactorings suggested for current changes.", 0.9)
            return AISuggestion("query", f"Found {len(refs)} refactorings.", 0.9, [r.text for r in refs])

        if "security" in query_lower or "secret" in query_lower:
            review = self.review_changes()
            sec_findings = [f for f in review.details if "🔒" in f or "secret" in f.lower()]
            if sec_findings:
                return AISuggestion("query", f"Found {len(sec_findings)} security concerns.", 0.9, sec_findings)
            return AISuggestion("query", "No immediate security issues detected in staged changes.", 0.9)

        if "perf" in query_lower or "latency" in query_lower:
            all_diff, stats = self._get_staged_diff()
            index = read_index(self.dg_dir)
            files = list(index.entries.keys())
            
            from deep.ai.analyzer import classify_change
            cls = classify_change(files, all_diff)
            if cls == "perf":
                return AISuggestion("query", "Detected performance-related changes.", 0.8, ["Optimize keywords found in diff."])
            return AISuggestion("query", "No significant performance optimizations detected.", 0.8)

        # Fallback
        latency = (time.perf_counter() - start) * 1000
        return AISuggestion("query", "I can help with commit messages, code review, or refactoring. Ask me about your current changes!", 0.5, [], latency)

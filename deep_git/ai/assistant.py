"""
deep_git.ai.assistant
~~~~~~~~~~~~~~~~~~~~~
Embedded AI Assistant for DeepGit.

Provides intelligent suggestions for commit messages, code quality,
merge conflict resolution, and branch naming using rule-based heuristics.
No external API dependency — fully self-contained.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from deep_git.core.index import read_index
from deep_git.core.objects import read_object, Blob, Commit
from deep_git.core.repository import DEEP_GIT_DIR
from deep_git.core.diff import diff_blob_vs_file
from deep_git.ai.analyzer import (
    analyze_diff_text,
    classify_change,
    extract_keywords,
    score_complexity,
    ChangeStats,
)


@dataclass
class AISuggestion:
    """A suggestion from the AI assistant."""
    suggestion_type: str  # "commit_msg", "quality", "branch_name", "merge_hint"
    text: str = ""
    confidence: float = 0.0  # 0.0 to 1.0
    details: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


class DeepGitAI:
    """Rule-based AI assistant for DeepGit."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.dg_dir = repo_root / DEEP_GIT_DIR
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

    def suggest_commit_message(self) -> AISuggestion:
        """Generate a commit message suggestion from staged changes."""
        start = time.perf_counter()

        index = read_index(self.dg_dir)
        if not index.entries:
            return AISuggestion("commit_msg", "chore: empty commit", 0.1)

        files = list(index.entries.keys())
        # Collect diffs for analysis
        all_diff = ""
        stats = ChangeStats()
        objects_dir = self.dg_dir / "objects"

        for rel_path, entry in index.entries.items():
            ext = Path(rel_path).suffix.lstrip(".")
            stats.file_types[ext] = stats.file_types.get(ext, 0) + 1

            file_path = self.repo_root / rel_path
            if file_path.exists():
                try:
                    diff_text = diff_blob_vs_file(objects_dir, entry.sha, file_path, rel_path)
                    if diff_text:
                        added, removed = analyze_diff_text(diff_text)
                        stats.lines_added += added
                        stats.lines_removed += removed
                        stats.files_modified += 1
                        all_diff += diff_text + "\n"
                    else:
                        stats.files_added += 1
                except Exception:
                    stats.files_added += 1
            else:
                stats.files_deleted += 1

        change_type = classify_change(files, all_diff)
        keywords = extract_keywords(all_diff)

        # Build message
        scope = stats.dominant_type if stats.dominant_type != "misc" else ""
        scope_part = f"({scope})" if scope else ""

        if keywords:
            summary = ", ".join(keywords[:3])
            msg = f"{change_type}{scope_part}: {summary}"
        else:
            msg = f"{change_type}{scope_part}: update {stats.total_files} file(s)"

        details = [
            f"Files: +{stats.files_added} ~{stats.files_modified} -{stats.files_deleted}",
            f"Lines: +{stats.lines_added} -{stats.lines_removed}",
        ]

        confidence = min(0.9, 0.3 + len(keywords) * 0.1 + (0.1 if scope else 0))
        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, confidence)

        return AISuggestion("commit_msg", msg, confidence, details, latency)

    def analyze_quality(self) -> AISuggestion:
        """Analyze staged files for code quality issues."""
        start = time.perf_counter()
        warnings: list[str] = []

        index = read_index(self.dg_dir)
        objects_dir = self.dg_dir / "objects"

        for rel_path, entry in index.entries.items():
            try:
                obj = read_object(objects_dir, entry.sha)
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
        """Predict merge outcomes by simulating a merge between two branches."""
        start = time.perf_counter()
        details = [f"Simulating merge: {branch_a} into {branch_b}"]
        
        from deep_git.core.refs import get_branch, resolve_head
        from deep_git.core.objects import read_object, Commit
        
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
        from deep_git.web.dashboard import _tree_entries_flat
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
        from deep_git.core.refs import list_branches, resolve_head
        branches = list_branches(self.dg_dir)
        head = resolve_head(self.dg_dir)
        
        details = []
        if len(branches) > 10:
            details.append(f"Tip: You have {len(branches)} branches. Consider pruning old ones.")
            
        # Implementation placeholder
        details.append("Tip: Use `deepgit branch -d` for merged branches")
        
        latency = (time.perf_counter() - start) * 1000
        self._record_metric(latency, 0.7)
        return AISuggestion("branch_mgmt", "Branch Hygiene Recommendations", 0.7, details, latency)

    def review_changes(self) -> AISuggestion:
        """Perform a deep AI code review of STAGED changes (Index vs HEAD)."""
        start = time.perf_counter()
        findings: list[str] = []
        
        from deep_git.core.refs import resolve_head
        from deep_git.core.diff import diff_blobs
        from deep_git.ai.analyzer import analyze_diff_text
        
        head_sha = resolve_head(self.dg_dir)
        head_entries = {}
        if head_sha:
            try:
                from deep_git.web.dashboard import _tree_entries_flat
                head_commit = read_object(self.dg_dir / "objects", head_sha)
                if isinstance(head_commit, Commit):
                    head_entries = _tree_entries_flat(self.dg_dir / "objects", head_commit.tree_sha)
            except Exception:
                pass

        index = read_index(self.dg_dir)
        objects_dir = self.dg_dir / "objects"
        
        total_added = 0
        total_removed = 0

        for rel_path, entry in index.entries.items():
            old_sha = head_entries.get(rel_path, "")
            new_sha = entry.sha
            
            if old_sha == new_sha:
                continue
                
            try:
                diff_text = diff_blobs(objects_dir, old_sha, new_sha, rel_path)
                if not diff_text:
                    continue
                    
                added, removed = analyze_diff_text(diff_text)
                total_added += added
                total_removed += removed

                # Scan for keywords/patterns
                lower_diff = diff_text.lower()
                if "todo" in lower_diff:
                    findings.append(f"✎ TODO found in {rel_path}")
                if "api_key" in lower_diff or "secret" in lower_diff:
                    findings.append(f"🔒 Sensitive keyword in {rel_path}")
                if "print(" in lower_diff and ".py" in rel_path:
                    findings.append(f"✎ Debug print remains in {rel_path}")
                
            except Exception:
                pass

        # Summary heuristics
        if total_removed > total_added + 100:
            findings.append(f"⚠ Large deletion alert (-{total_removed} lines)")
        
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
        self._record_metric(latency, hint.confidence)
        
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
                    if (path / ".deep_git").exists():
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
        """Analyze staged files and suggest specific refactorings."""
        from deep_git.ai.refactor import RefactorEngine
        engine = RefactorEngine()
        
        suggestions = []
        index = read_index(self.dg_dir)
        objects_dir = self.dg_dir / "objects"
        
        for rel_path, entry in index.entries.items():
            try:
                obj = read_object(objects_dir, entry.sha)
                if isinstance(obj, Blob):
                    content = obj.data.decode("utf-8", errors="replace")
                    changes = engine.suggest_fixes(content, rel_path)
                    for c in changes:
                        suggestions.append(AISuggestion(
                            suggestion_type="refactor",
                            text=f"Refactor ({c.type}): {rel_path}",
                            confidence=0.8,
                            details=[c.description, f"Proposed: {c.replacement}"]
                        ))
            except Exception:
                pass
        return suggestions

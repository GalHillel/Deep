"""
deep.ai.analyzer
~~~~~~~~~~~~~~~~~~~~
Diff and code quality analysis engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ChangeStats:
    """Statistics about a set of staged changes."""
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    file_types: dict[str, int] = field(default_factory=dict)
    large_files: list[str] = field(default_factory=list)
    binary_files: list[str] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return self.files_added + self.files_modified + self.files_deleted

    @property
    def dominant_type(self) -> str:
        if not self.file_types:
            return "misc"
        return max(self.file_types, key=self.file_types.get)


def analyze_diff_text(diff_text: str) -> tuple[int, int]:
    """Count added/removed lines in a unified diff string."""
    added = removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def classify_change(files: list[str], diff_text: str = "") -> str:
    """Classify a set of changes as feat/fix/refactor/docs/chore/security/perf."""
    lower_diff = diff_text.lower()
    lower_files = " ".join(f.lower() for f in files)

    if any(f.endswith((".md", ".txt", ".rst")) for f in files) and len(files) <= 2:
        return "docs"
    if "test" in lower_files:
        return "test"
    if any(kw in lower_diff for kw in ["security", "vulnerability", "leak", "secret", "auth", "encrypt"]):
        return "security"
    if any(kw in lower_diff for kw in ["performance", "speed", "latency", "memory", "optimize", "fast"]):
        return "perf"
    if "fix" in lower_diff or "bug" in lower_diff or "error" in lower_diff:
        return "fix"
    if "refactor" in lower_diff or "rename" in lower_diff or "move" in lower_diff:
        return "refactor"
    if any(kw in lower_diff for kw in ["config", ".yml", ".toml", ".json", ".ini"]):
        return "chore"
    return "feat"


def extract_keywords(diff_text: str, max_keywords: int = 5) -> list[str]:
    """Extract meaningful keywords from diff content."""
    words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', diff_text)
    # Filter common noise
    noise = {"self", "return", "import", "from", "None", "True", "False",
             "class", "func", "print", "else", "elif", "with", "pass",
             "lambda", "yield", "async", "await", "def", "for", "while",
             "break", "continue", "raise", "except", "finally", "try",
             "assert", "global", "nonlocal", "del", "not", "and", "is", "in"}
    filtered = [w for w in words if w.lower() not in noise and not w.startswith("__")]
    # Count frequency
    freq: dict[str, int] = {}
    for w in filtered:
        freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_words[:max_keywords]]


def score_complexity(content: str) -> float:
    """Score file complexity (0.0 = trivial, 1.0 = very complex)."""
    lines = content.splitlines()
    if not lines:
        return 0.0
    line_count = len(lines)
    indent_depths = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    avg_indent = sum(indent_depths) / max(len(indent_depths), 1)
    func_count = sum(1 for l in lines if l.strip().startswith("def "))
    class_count = sum(1 for l in lines if l.strip().startswith("class "))
    # Heuristic: combine metrics
    score = min(1.0, (line_count / 500) * 0.3 + (avg_indent / 16) * 0.3 +
                (func_count / 20) * 0.2 + (class_count / 10) * 0.2)
    return round(score, 2)

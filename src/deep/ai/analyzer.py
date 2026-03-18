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


def extract_diff_semantics(diff_text: str) -> dict:
    """
    Deterministically analyze unified diff and extract structural intent.
    """

    import re

    semantics = {
        "functions": [],
        "classes": [],
        "imports_added": False,
        "exceptions_added": False,
        "logic_changes": False,
        "condition_changes": False,
        "returns_changed": False,
        "breaking_change": False,
        "new_files": False,
        "deleted_files": False,
        "renamed": False
    }

    for line in diff_text.splitlines():

        # Detect new/deleted files
        if line.startswith("+++ /dev/null"):
            semantics["deleted_files"] = True
        if line.startswith("--- /dev/null"):
            semantics["new_files"] = True

        # Hunk context extraction OR definition in added/context lines
        if line.startswith("@@") or line.startswith("+") or line.startswith(" "):

            func = re.search(r"(def|function)\s+([a-zA-Z0-9_]+)", line)
            cls = re.search(r"(class)\s+([a-zA-Z0-9_]+)", line)

            if func and func.group(2) not in semantics["functions"]:
                semantics["functions"].append(func.group(2))

            if cls and cls.group(2) not in semantics["classes"]:
                semantics["classes"].append(cls.group(2))


        # Added lines analysis
        if line.startswith("+"):
            code = line[1:].strip()

            if re.match(r"(import |from .* import)", code):
                semantics["imports_added"] = True

            if re.match(r"(raise |throw )", code):
                semantics["exceptions_added"] = True

            if "return" in code:
                semantics["returns_changed"] = True

            if any(op in code for op in ["==", "!=", ">", "<"]):
                semantics["logic_changes"] = True

            if any(k in code for k in ["if ", "elif ", "switch", "case"]):
                semantics["condition_changes"] = True

            # Breaking change heuristic
            if any(k in code for k in ["remove", "delete", "drop"]):
                semantics["breaking_change"] = True

    return semantics



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

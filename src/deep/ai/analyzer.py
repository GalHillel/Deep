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
    State-machine based parser.
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

    current_func = None
    current_class = None

    for line in diff_text.splitlines():
        if line.startswith("+++ /dev/null"):
            semantics["deleted_files"] = True
            semantics["breaking_change"] = True
            continue
        if line.startswith("--- /dev/null"):
            semantics["new_files"] = True
            continue

        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        # Extract context from hunk headers
        if line.startswith("@@"):
            match = re.search(r"@@.*@@\s*(def|class)\s+([a-zA-Z0-9_]+)", line)
            if match:
                kind, name = match.groups()
                if kind == "def":
                    current_func = name
                elif kind == "class":
                    current_class = name
            continue

        if len(line) == 0:
            continue

        prefix = line[0]
        if prefix not in ("+", "-", " "):
            continue

        clean_line = line[1:].strip()

        # Update context based on context lines or additions
        if prefix in (" ", "+"):
            func_match = re.match(r"def\s+([a-zA-Z0-9_]+)", clean_line)
            cls_match = re.match(r"class\s+([a-zA-Z0-9_]+)", clean_line)
            if func_match:
                current_func = func_match.group(1)
            elif cls_match:
                current_class = cls_match.group(1)

        if prefix == "+":
            if current_func and current_func not in semantics["functions"]:
                semantics["functions"].append(current_func)
            if current_class and current_class not in semantics["classes"]:
                semantics["classes"].append(current_class)

            if re.match(r"^(import |from .* import )", clean_line):
                semantics["imports_added"] = True

            if clean_line.startswith("raise ") or clean_line.startswith("throw "):
                semantics["exceptions_added"] = True

            if "return " in clean_line or clean_line == "return":
                semantics["returns_changed"] = True

            if any(op in clean_line for op in ["==", "!=", " > ", " < ", ">=", "<="]):
                semantics["logic_changes"] = True

            if any(clean_line.startswith(k) for k in ["if ", "elif ", "switch ", "case ", "while "]):
                semantics["condition_changes"] = True

            if "@deprecated" in clean_line.lower() or "deprecated(" in clean_line.lower():
                semantics["breaking_change"] = True

        if prefix == "-":
            # Strict breaking change: Removal of exported function/class (no leading underscore)
            func_remove = re.match(r"def\s+([a-zA-Z0-9][a-zA-Z0-9_]*)", clean_line)
            if func_remove:
                semantics["breaking_change"] = True
                
            cls_remove = re.match(r"class\s+([a-zA-Z0-9][a-zA-Z0-9_]*)", clean_line)
            if cls_remove:
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

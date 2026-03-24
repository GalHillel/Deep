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


def extract_diff_symbols(diff_text: str) -> dict[str, list[str]]:
    """
    Extract modified function and class names from a unified diff.
    Returns: {'functions': [], 'classes': []}
    """
    symbols = {"functions": [], "classes": []}
    current_func = None
    current_class = None

    for line in diff_text.splitlines():
        # Hunk header often contains the function/class context
        if line.startswith("@@"):
            match = re.search(r"@@.*@@\s*(def|class)\s+([a-zA-Z0-9_]+)", line)
            if match:
                kind, name = match.groups()
                if kind == "def":
                    if name not in symbols["functions"]: symbols["functions"].append(name)
                elif kind == "class":
                    if name not in symbols["classes"]: symbols["classes"].append(name)
            continue

        # Context or Addition
        clean = line[1:].strip()
        f_match = re.match(r"def\s+([a-zA-Z0-9_]+)", clean)
        c_match = re.match(r"class\s+([a-zA-Z0-9_]+)", clean)
        
        if f_match:
            current_func = f_match.group(1)
        if c_match:
            current_class = c_match.group(1)

        if line.startswith("+") and not line.startswith("+++"):
            if current_func and current_func not in symbols["functions"]:
                symbols["functions"].append(current_func)
            if current_class and current_class not in symbols["classes"]:
                symbols["classes"].append(current_class)
                
    return symbols

def extract_lexical_tokens(diff_text: str) -> list[str]:
    """
    Extract interesting keywords/variables from diff additions.
    Exclude common keywords and short tokens.
    """
    tokens = []
    stopwords = {"self", "cls", "import", "from", "return", "def", "class", "if", "else", "elif", "for", "while", "try", "except", "finally", "with", "as", "pass", "none", "true", "false", "and", "or", "not", "in", "is", "lambda"}
    
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            # Extract words
            words = re.findall(r"[a-zA-Z0-9_]{4,}", line[1:])
            for w in words:
                w_lower = w.lower()
                if w_lower not in stopwords and not w[0].isdigit():
                    if w_lower not in tokens:
                        tokens.append(w_lower)
    
    return tokens[:10] # Limit to top 10 tokens

def extract_diff_semantics(diff_text: str) -> dict:
    """ Legacy wrapper for backward compatibility, enhanced with symbols. """
    symbols = extract_diff_symbols(diff_text)
    semantics = {
        "functions": symbols["functions"],
        "classes": symbols["classes"],
        "imports_added": "import " in diff_text or "from " in diff_text,
        "exceptions_added": "raise " in diff_text or "throw " in diff_text,
        "logic_changes": any(op in diff_text for op in ["==", "!=", " > ", " < ", ">=", "<="]),
        "condition_changes": any(k in diff_text for k in ["if ", "elif ", "switch ", "case ", "while "]),
        "returns_changed": "return " in diff_text,
        "breaking_change": "+++" in diff_text and "/dev/null" in diff_text, # Handled better elsewhere
        "new_files": "--- /dev/null" in diff_text,
        "deleted_files": "+++ /dev/null" in diff_text,
        "renamed": False
    }
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

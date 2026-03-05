"""
deep.core.ignore
~~~~~~~~~~~~~~~~~~~~~
``.deepignore`` parsing and glob matching engine.

Supports:
- Blank lines and comments (``#``)
- Directory patterns (trailing ``/``)
- Wildcards (``*``, ``?``, ``[abc]``)
- Negation patterns (leading ``!``)
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path


class IgnoreEngine:
    """Parses .deepignore and evaluates path matches."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        # Each rule: (is_negation, regex_pattern)
        self.rules: list[tuple[bool, re.Pattern]] = []
        self._load_ignores()

    def _compile_pattern(self, pattern: str) -> tuple[bool, re.Pattern]:
        is_negation = False
        if pattern.startswith("!"):
            is_negation = True
            pattern = pattern[1:]

        ends_with_slash = pattern.endswith("/")
        has_slash = "/" in pattern[:-1] if ends_with_slash else "/" in pattern
        is_absolute = False
        if pattern.startswith("/"):
            is_absolute = True
            pattern = pattern[1:]
        elif has_slash and not pattern.startswith("**/"):
            is_absolute = True

        res = []
        if is_absolute:
            res.append("^")
        else:
            res.append("(^|/)")

        i = 0
        n = len(pattern)
        while i < n:
            c = pattern[i]
            if c == "*":
                if i + 1 < n and pattern[i+1] == "*":
                    i += 1
                    if i + 1 < n and pattern[i+1] == "/":
                        i += 1
                        res.append(r"(.*\/)?")
                    else:
                        res.append(".*")
                else:
                    res.append("[^/]*")
            elif c == "?":
                res.append("[^/]")
            elif c == "[":
                j = i + 1
                if j < n and pattern[j] in ("!", "^"):
                    j += 1
                while j < n and pattern[j] != "]":
                    j += 1
                if j < n:
                    res.append(pattern[i:j+1].replace("!", "^"))
                    i = j
                else:
                    res.append(re.escape(c))
            else:
                res.append(re.escape(c))
            i += 1

        if not ends_with_slash:
            res.append("($|/)")

        return is_negation, re.compile("".join(res))

    def _load_ignores(self) -> None:
        ignore_file = self.repo_root / ".deepignore"
        # Always ignore .deep_git
        self.rules.append(self._compile_pattern(".deep_git/"))

        if not ignore_file.exists():
            return

        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                self.rules.append(self._compile_pattern(line))
            except Exception:
                pass  # Ignore invalid regex

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Return True if the relative path should be ignored.
        
        Evaluates rules in order. A matching rule sets the ignored state.
        A matching negation rule un-sets the ignored state.
        """
        rel_path = rel_path.replace("\\", "/")
        if is_dir and not rel_path.endswith("/"):
            test_path = rel_path + "/"
        else:
            test_path = rel_path
            
        ignored = False
        for is_neg, pat in self.rules:
            if pat.search(test_path):
                ignored = not is_neg

        return ignored

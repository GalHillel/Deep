"""
deep_git.core.ignore
~~~~~~~~~~~~~~~~~~~~~
``.deepgitignore`` parsing and glob matching engine.

Supports:
- Blank lines and comments (``#``)
- Directory patterns (trailing ``/``)
- Wildcards (``*``, ``?``, ``[abc]``)
- Negation patterns (leading ``!``)
"""

from __future__ import annotations

import fnmatch
from pathlib import Path


class IgnoreEngine:
    """Parses .deepgitignore and evaluates path matches."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.rules: list[tuple[bool, str, bool]] = []  # (is_negation, pattern, only_dir)
        self._load_ignores()

    def _load_ignores(self) -> None:
        ignore_file = self.repo_root / ".deepgitignore"
        # Always ignore .deep_git
        self.rules.append((False, ".deep_git", True))
        self.rules.append((False, ".deep_git/*", False))

        if not ignore_file.exists():
            return

        for line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            is_negation = False
            if line.startswith("!"):
                is_negation = True
                line = line[1:]
                if not line:
                    continue

            only_dir = False
            if line.endswith("/"):
                only_dir = True
                line = line[:-1]

            # If no slash (except trailing), it matches anywhere in the tree.
            # So a pattern like "foo" should match "foo" or "a/foo" or "a/b/foo".
            # We normalize this by prepend * if there's no slash, but let `is_ignored` 
            # handle the exact mechanics.
            
            self.rules.append((is_negation, line, only_dir))

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Return True if the relative path should be ignored.
        
        Evaluates rules in order. A matching rule sets the ignored state.
        A matching negation rule un-sets the ignored state.
        """
        ignored = False
        path_parts = rel_path.split("/")

        for is_neg, pattern, only_dir in self.rules:
            match = False
            
            if "/" not in pattern:
                # Matches the basename or any directory part of the path
                if not only_dir or is_dir:
                    if fnmatch.fnmatch(path_parts[-1], pattern):
                        match = True
                if not match:
                    # Any parent directory in the path is a directory, so only_dir doesn't restrict it here
                    for part in path_parts[:-1]:
                        if fnmatch.fnmatch(part, pattern):
                            match = True
                            break
            else:
                pat = pattern.lstrip("/")
                if not only_dir or is_dir:
                    if fnmatch.fnmatch(rel_path, pat):
                        match = True
                if not match:
                    # Any prefix of the path is a directory
                    for i in range(1, len(path_parts)):
                        prefix = "/".join(path_parts[:i])
                        if fnmatch.fnmatch(prefix, pat):
                            match = True
                            break

            if match:
                ignored = not is_neg

        return ignored


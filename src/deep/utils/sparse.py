import fnmatch
from pathlib import Path
from typing import List

def load_sparse_patterns(dg_dir: Path) -> List[str]:
    """Load sparse-checkout patterns from .deep/info/sparse-checkout."""
    pattern_file = dg_dir / "info" / "sparse-checkout"
    if not pattern_file.exists():
        return ["*"] # Default: match everything
    
    patterns = []
    with open(pattern_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns

def matches_sparse_patterns(path: str, patterns: List[str]) -> bool:
    """Check if a path matches any of the sparse-checkout patterns."""
    # If patterns is ["*"], everything matches.
    # We use fnmatch for glob-style matching.
    # Note: Deep's sparse-checkout uses pattern-based filtering, 
    # but we'll start with simple glob matching.
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        # Also match if the path is inside a matched directory
        if pattern.endswith("/") and path.startswith(pattern):
            return True
        if fnmatch.fnmatch(path, f"{pattern}/*"):
            return True
    return False

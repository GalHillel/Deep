# Deep VCS Developer Guide

Welcome to the contributor's guide for Deep VCS. This document outlines the technical architecture, coding standards, and workflows required to extend the project.

## Core Philosophy

Deep VCS is built on three pillars:
1. **Crash-Safety**: Every write must be atomic. Never leave the repository in a half-written state.
2. **Speed**: Use optimized binary formats (Index V1) and memory mapping where possible.
3. **Simplicity**: The codebase should be readable and modular. High complexity should be isolated in specific subsystems (e.g., CDC chunking).

## Project Structure

```text
src/deep/
  ├── cli/       # CLI entry point and dispatching
  ├── core/      # High-level repository logic (refs, ignore, mirror)
  ├── storage/   # Low-level data layer (objects, index, pack, delta)
  ├── network/   # Distrubted logic (p2p, daemon, remote)
  ├── platform/  # Enterprise features (pr, issue, pipeline)
  ├── utils/     # Shared helpers (ux formatting, atomic writes)
  └── ai/        # AI-powered assistance (Voodoo engine)
```

## Implementation Standards

### 1. Atomic Writes
Always use `deep.utils.utils.AtomicWriter` for persistent data:
```python
from deep.utils.utils import AtomicWriter
with AtomicWriter(path) as aw:
    aw.write(data)
```

### 2. Concurrency
Use `filelock` when modifying shared refs (branches, HEAD) or the index.
```python
from filelock import FileLock
lock = FileLock(str(path) + ".lock")
with lock:
    # Perform modification
```

### 3. UX Consistency
Use the consolidated `deep.utils.ux` layer for all terminal output:
```python
from deep.utils.ux import Color, print_success
print_success(Color.wrap(Color.BOLD, "Operation complete."))
```

## Adding a New Command

1. Create a new module in `src/deep/commands/<name>_cmd.py`.
2. Implement a `run(args)` function.
3. Register the command and its `argparse` configuration in `src/deep/cli/main.py`.

## Git Compatibility

While Deep VCS is a next-gen tool, we maintain header compatibility with Git for objects (`<type> <size>\0<content>`). This allows for future interoperability and leverage of existing tools.

---

*For information on testing, see the [Testing Guide](testing.md).*

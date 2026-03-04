# Deep Git 🔱

A **robust, concurrency-safe, Git-like version control system** built from scratch in Python 3.

Deep Git implements the core fundamentals of Git — content-addressable storage, a directed acyclic graph (DAG) of commits, an index-based staging area, and branch management — with a focus on **atomicity**, **crash recovery**, and **concurrency safety**.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Content-Addressable Storage** | Every object (Blob, Tree, Commit) is identified by its SHA-1 hash. Duplicate content is stored only once. |
| **Advanced Operations** | Full support for branching, merging (fast-forward and 3-way), checkouts, repository status, diffing, and resets. |
| **Atomic Writes** | All file writes go through `AtomicWriter` — data is written to a temp file and atomically renamed via `os.replace`. A crash mid-write will never corrupt your repository. |
| **Concurrency Safety** | The index and all ref updates are protected by cross-platform file locks (`filelock`). 20 threads can write to the index simultaneously without data corruption. |
| **DAG Integrity** | Commits point to valid Trees and parent Commits, forming a verifiable directed acyclic graph. |
| **Zlib Compression** | Stored objects are compressed with zlib, just like Git. |
| **Git-Compatible Serialisation** | Objects use Git's `<type> <size>\0<content>` wire format. |

---

## 🏗️ Architecture

```
.deep_git/
├── HEAD                  # Symbolic ref (e.g. "ref: refs/heads/main") or detached SHA
├── index                 # JSON staging area (locked for concurrent access)
├── objects/              # Content-addressable object store
│   └── ab/               #   First 2 hex chars of SHA
│       └── cdef1234...   #   Remaining 38 hex chars
└── refs/
    └── heads/            # Branch tips
        ├── main
        └── feature
```

### Object Model

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Commit  │────▶│   Tree   │────▶│   Blob   │
│  (SHA-1) │     │  (SHA-1) │     │  (SHA-1) │
│          │     │          │     │          │
│ tree_sha │     │ entries[]│     │ data     │
│ parents[]│     │  mode    │     └──────────┘
│ author   │     │  name    │
│ message  │     │  sha     │
└──────────┘     └──────────┘
      │
      ▼
┌──────────┐
│  Parent  │
│  Commit  │ ─── ▶ ...  (DAG)
└──────────┘
```

### Core Modules

| Module | Responsibility |
|---|---|
| `core/utils.py` | SHA-1 hashing (`hash_bytes`) and `AtomicWriter` for crash-safe file I/O |
| `core/repository.py` | Repository initialisation (`init_repo`) and discovery (`find_repo`) |
| `core/objects.py` | `Blob`, `Tree`, `Commit` — serialisation, hashing, read/write to disk |
| `core/index.py` | Staging area with `filelock`-based concurrency protection |
| `core/refs.py` | HEAD resolution, branch CRUD, and `log_history` DAG traversal |
| `commands/` | CLI command implementations (`init`, `add`, `commit`, `log`, `branch`) |
| `main.py` | `argparse`-based CLI entry point |

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit

# Create a virtual environment and install
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -e ".[dev]"
```

### CLI Usage

```bash
# Initialize a new repository
deepgit init

# Create and track files
echo "Hello, Deep Git!" > hello.txt
deepgit add hello.txt

# Commit your changes
deepgit commit -m "Initial commit"

# View the log
deepgit log
# commit 3a7f2b1...
# Author: Deep Git User <user@deepgit>
# Date:   1709546000 +0000
#
#     Initial commit

# Check repository status
deepgit status

# View unstaged changes
deepgit diff

# Create a branch and checkout
deepgit branch feature
deepgit checkout feature

# Merge branches
deepgit checkout main
deepgit merge feature

# Remove and reset
deepgit rm hello.txt
deepgit reset --hard HEAD
```

---

## 🧪 Running the Test Suite

```bash
# Run all tests with verbose output
pytest -v

# Run a specific phase's tests
pytest tests/test_utils.py -v          # Phase 1: Utilities
pytest tests/test_repository.py -v     # Phase 1: Repository
pytest tests/test_objects.py -v        # Phase 2: Object Model
pytest tests/test_index_concurrency.py -v  # Phase 3: Index & Concurrency
pytest tests/test_refs.py -v           # Phase 4: Refs & Branches
pytest tests/test_cli.py -v            # Phase 5: CLI Integration

# Run concurrency stress tests only
pytest tests/test_index_concurrency.py::TestIndexConcurrency -v
```

### Test Coverage Summary

| Test File | Tests | What It Covers |
|---|---|---|
| `test_utils.py` | 13 | SHA-1 hashing, atomic writes, crash simulation, concurrent writes |
| `test_repository.py` | 8 | Repo init, directory structure, duplicate detection, repo discovery |
| `test_objects.py` | 13 | Blob/Tree/Commit serialisation, round-trips, DAG chain integrity |
| `test_index_concurrency.py` | 8 | Index CRUD, JSON round-trip, 20-thread stress tests |
| `test_refs.py` | 17 | HEAD resolution, branch lifecycle, detached HEAD, log traversal |
| `test_cli.py` | 16 | End-to-end workflows: init→add→commit→log→branch |
| `test_status.py` | 11 | 3-way status comparisons, untracked/staged/modified states |
| `test_diff.py` | 10 | Unified diff generation, working tree comparisons |
| `test_checkout.py` | 6 | Branch switching, detached HEAD, safe tree restoration |
| `test_merge.py` | 8 | LCA detection, fast-forward, 3-way merge, conflict aborts |
| `test_rm_reset.py` | 8 | File removal, soft/hard resets |
| **Total** | **110** | |

---

## 🔒 Engineering Principles

### Atomicity & Crash Recovery
Every file write uses `AtomicWriter`:
1. Data is written to a temp file in the **same directory** (guaranteeing same-filesystem atomic rename).
2. The file is `fsync`'d to disk.
3. `os.replace()` atomically swaps it into place.
4. If an exception occurs, the temp file is cleaned up and the target is untouched.

### Concurrency Safety
Critical shared state is protected by `filelock`:
- **Index**: Reads and writes acquire an exclusive lock on `.deep_git/index.lock`.
- **Branch refs**: Each branch ref has its own `.lock` file.
- **HEAD**: Updates acquire `HEAD.lock`.

The concurrency stress tests spawn **20 concurrent threads** all writing to the index simultaneously, then verify zero data corruption.

### Content-Addressable Storage
Objects are stored at `objects/<xx>/<yy…>` where `xx` = first 2 hex chars of the SHA-1, `yy…` = remaining 38. This mirrors Git's layout and provides natural filesystem sharding.

---

## 📁 Project Structure

```
DeepGit/
├── deep_git/
│   ├── __init__.py
│   ├── main.py              # CLI entry point
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── init_cmd.py
│   │   ├── add_cmd.py
│   │   ├── commit_cmd.py
│   │   ├── log_cmd.py
│   │   └── branch_cmd.py
│   └── core/
│       ├── __init__.py
│       ├── utils.py          # AtomicWriter, hash_bytes
│       ├── repository.py     # init_repo, find_repo
│       ├── objects.py         # Blob, Tree, Commit, read_object
│       ├── index.py           # Staging area with file locking
│       └── refs.py            # HEAD, branches, log_history
├── tests/
│   ├── test_utils.py
│   ├── test_repository.py
│   ├── test_objects.py
│   ├── test_index_concurrency.py
│   ├── test_refs.py
│   └── test_cli.py
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
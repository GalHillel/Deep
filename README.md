# Deep Git 🔱

A **robust, concurrency-safe, Git-like version control system** built from scratch in Python 3.

Deep Git implements the core fundamentals of Git — content-addressable storage, a directed acyclic graph (DAG) of commits, an index-based staging area, and branch management — with a focus on **atomicity**, **crash recovery**, and **concurrency safety**.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Content-Addressable Storage** | SHA-1 based object model (Blob, Tree, Commit, Tag). |
| **Distributed Mode** | `daemon`, `clone`, `push`, and `fetch` support via PKT-LINE wire protocol. |
| **Packfiles & Compression** | Efficient object bundling with Deep Pack format and transparent `zlib` compression. |
| **Web Dashboard** | Interactive DAG explorer at `deepgit web` with REST API. |
| **AI Assistant** | Commit message suggestions, quality analysis, branch naming via `deepgit ai`. |
| **Enterprise Security** | RBAC (admin/write/read), per-branch permissions, append-only audit log. |
| **Crash Recovery** | Write-ahead transaction log with auto-recovery and `deepgit doctor` integration. |
| **Telemetry** | Performance metrics collection, `Timer` context manager, dashboard integration. |
| **Multi-User Sync** | Event broadcasting, divergent push detection, real-time conflict resolution. |
| **Atomic Writes** | `AtomicWriter` ensures crash-safe repository state. |
| **Concurrency Safety** | `filelock` protection for cross-process index and ref updates. |
| **Advanced CLI** | `merge` (FF & 3-way), `rebase`, `stash`, `tag`, `config`, and `ignore` support. |
| **Integrity & GC** | `gc` for mark-and-sweep cleanup and `doctor` for full graph validation. |

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
| `core/objects.py` | `Blob`, `Tree`, `Commit`, `Tag` — serialisation and disk I/O |
| `core/index.py` | Staging area with `filelock`-based concurrency protection |
| `core/refs.py` | HEAD resolution, branch CRUD, and DAG traversal |
| `core/pack.py` | **Deep Pack** creation and unpacking logic |
| `network/` | Wire protocol implementation and Distributed Daemon |
| `commands/` | CLI implementations (including `gc`, `doctor`, `stash`, `rebase`) |
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

## 🌐 Distributed Workflow

Deep Git supports distributed collaboration using a built-in TCP daemon and a PKT-LINE based wire protocol.

### 1. Start the Daemon (Server)
Host your repository on the network:
```bash
deepgit daemon --port 8888
```

### 2. Clone (Client)
Copy a remote repository:
```bash
deepgit clone 127.0.0.1:8888 my-repo
```

### 3. Push & Fetch
Synchronize changes:
```bash
# Push local branch to remote
deepgit push 127.0.0.1:8888 main

# Fetch specific SHA from remote
deepgit fetch 127.0.0.1:8888 <sha-1>
```

---

## 📡 Wire Protocol v1

Deep Git uses a structured binary protocol for networking:
- **Framing**: [PKT-LINE](https://git-scm.com/docs/protocol-common#_pkt_line_format) (4-byte hex length + payload).
- **Handshake**: Capability negotiation (`push`, `fetch`, `packfile-v1`).
- **Object Transfer**: Compressed **Deep Pack** files with CRC-32 integrity and SHA-1 trailers.
- **Push Safety**: Objects are first received into a `quarantine/` directory and only moved into the main store if the transfer is complete and valid.


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
| `test_utils.py` | 13 | SHA-1, atomicity, crash recovery |
| `test_index_concurrency.py` | 8 | 20-thread index stress tests |
| `test_merge.py` | 10 | FF and 3-way merge logic |
| `test_rebase.py` | 6 | Commit transplanting and history rewriting |
| `test_daemon.py` | 5 | Distributed server & connectivity |
| `test_remote_cli.py` | 3 | End-to-end `clone`/`push`/`fetch` |
| `test_gc_doctor.py` | 8 | Garbage collection and graph validation |
| **Total** | **177** | **Full Feature Coverage** |

---

## 🔒 Engineering Principles

### Atomicity & Crash Recovery
Every file write uses `AtomicWriter`:
1. Data is written to a temp file in the **same directory** (guaranteeing same-filesystem atomic rename).
2. The file is `fsync`'d to disk.
3. `os.replace()` atomically swaps it into place.

### Content-Addressable Storage
Deep Git uses Git's core object model. Objects are stored under `.deep_git/objects/<xx>/<yy...>` and are transparently compressed with `zlib`.

### Concurrency Safety
Critical shared state (Index, Refs, HEAD) is protected by `filelock`. The system is safe for high-concurrency environments, supporting simultaneous writes from multiple processes.

### Distributed Security (Quarantine)
When pushing to a remote daemon, objects are first unbundled into a `quarantine/` directory. Only after the entire packfile is received and validated are the objects moved to the permanent store and refs updated atomically.


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
# Deep Architecture

This document explains how Deep works under the hood. If you want to contribute, debug a weird edge case, or just understand what happens when you run `deep commit`, this is where to start.

## Layer Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│                  src/deep/cli/main.py                            │
│         argparse registration → command dispatch                 │
├──────────────────────────────────────────────────────────────────┤
│                       Command Layer                              │
│                  src/deep/commands/*_cmd.py                      │
│       Each file exposes run(args). Thin wrappers over core.      │
├──────────────────────────────────────────────────────────────────┤
│                        Core Engine                               │
│                     src/deep/core/                               │
│   refs · merge · diff · status · graph · stash · hooks · gc     │
├───────────────┬──────────────────┬───────────────────────────────┤
│    Storage    │     Network      │          Platform             │
│ src/deep/     │ src/deep/        │ src/deep/core/                │
│ storage/      │ network/         │ pr.py · issue.py · pipeline   │
│               │                  │ src/deep/server/ · web/       │
├───────────────┴──────────────────┴───────────────────────────────┤
│                       Object Model                               │
│                    src/deep/objects/                              │
│              Blob · Tree · Commit · Tag                          │
└──────────────────────────────────────────────────────────────────┘
```

**Hard rule:** Commands import from Core. Core imports from Storage and Objects. Commands never import from Storage directly. This keeps the dependency graph acyclic and testable.

---

## 1. CLI Layer (`src/deep/cli/main.py`)

The CLI is a single `argparse` parser with ~55 subcommands registered as subparsers. When you run `deep commit -m "fix"`, here's what happens:

1. `build_parser()` constructs the full argument parser tree
2. `main()` calls `parser.parse_args()` to get a `Namespace` object
3. A long `if/elif` chain maps `args.command` to the correct `run(args)` function via dynamic imports
4. The command's `run(args)` function executes

We intentionally use lazy imports (`from deep.commands.X import run` inside the elif) to keep CLI startup fast — only the invoked command's module is loaded.

### Error Handling

The `main()` function wraps every `run(args)` call in a try/except:

- `DeepError` → clean user-facing error message to stderr
- `DeepCLIException` → exit with a specific code (like `SystemExit`)
- Any other `Exception` → "internal error" message (unless `DEEP_DEBUG=1` is set, which re-raises for a full traceback)

---

## 2. Content-Addressable Storage (`src/deep/storage/`)

This is the foundation. Every piece of data (file content, directory structure, commit metadata) is stored as an **object** identified by its SHA-1 hash.

### Object Types

| Type | What it stores | Typical size |
|---|---|---|
| **Blob** | Raw file content | Varies (bytes to megabytes) |
| **Tree** | Directory listing: `(mode, name, child_sha)` tuples | Small |
| **Commit** | Tree SHA + parent SHAs + author + message + timestamp | < 1 KB |
| **Tag** | Target SHA + tagger + message | < 1 KB |

### On-Disk Layout

```
.deep/
├── objects/
│   ├── ab/
│   │   └── cdef1234...   ← SHA prefix as directory, rest as filename
│   └── ...
├── refs/
│   ├── heads/
│   │   ├── main          ← contains the SHA of the branch tip
│   │   └── feature
│   └── tags/
│       └── v1.0.0
├── HEAD                   ← "ref: refs/heads/main" or a raw SHA
├── index                  ← binary staging area
└── txlog/                 ← Write-Ahead Log entries
```

### How a Commit Works (Internally)

1. `deep add file.txt` → hash the file content → store as blob → update the index
2. `deep commit -m "msg"` → read the index → build a tree hierarchy → hash each tree → create a commit object pointing to the root tree + parent commit → update the branch ref

Every step produces a new immutable object. Nothing is ever overwritten — only new objects are appended and refs are updated atomically.

### The Index (Staging Area)

The index (``.deep/index``) is a binary file mapping `(path, mode)` → `sha`. When you run `deep add`, we hash your file and write the mapping. When you run `deep commit`, we walk the index to build tree objects.

The index is designed for speed: it's read into memory in one pass and uses sorted entries for fast lookup.

---

## 3. Write-Ahead Log (WAL) & Transactions (`src/deep/storage/txlog.py`)

This is what makes Deep crash-proof. Before any destructive operation (commit, merge, checkout), we:

1. **Log the intent** — write the planned changes to `.deep/txlog/`
2. **Execute the changes** — modify refs, index, working tree
3. **Mark complete** — clear the log entry

If the process crashes between steps 1 and 2, the next `deep` invocation detects the incomplete transaction and automatically recovers:

- If changes weren't applied → discard the log (no-op)
- If changes were partially applied → roll forward to completion

The `TransactionManager` context manager makes this transparent to command authors:

```python
with TransactionManager(dg_dir) as tm:
    tm.begin("commit")
    # ... do work ...
    tm.commit()
# If an exception fires before tm.commit(), changes are rolled back
```

---

## 4. Reference Management (`src/deep/core/refs.py`)

Refs map human-readable names to SHA hashes. The ref system supports:

- **Branches** — `refs/heads/<name>` → SHA of the tip commit
- **Tags** — `refs/tags/<name>` → SHA of a commit or tag object
- **Remote refs** — `refs/remotes/<remote>/<branch>` → last known SHA from a remote
- **HEAD** — either a symbolic ref (`ref: refs/heads/main`) or a detached SHA

### Key Operations

| Function | What it does |
|---|---|
| `resolve_head(dg_dir)` | Follow HEAD → branch → SHA |
| `update_branch(dg_dir, name, sha)` | Write a new SHA to a branch ref |
| `log_history(dg_dir)` | Walk parent pointers from HEAD to build commit history |
| `get_commit_decorations(dg_dir)` | Map SHAs to their branch/tag labels for `log` display |

---

## 5. Merge Engine (`src/deep/core/merge.py`)

Deep supports both fast-forward and three-way merges:

1. **Find the merge base** — the common ancestor of the two branch tips (using BFS over the commit graph)
2. **If the merge base equals one tip** → fast-forward (just move the ref pointer)
3. **Otherwise** → three-way merge:
   - Diff base↔ours and base↔theirs
   - Apply non-conflicting changes automatically
   - Mark conflicts with `<<<<<<<` / `=======` / `>>>>>>>` markers
   - Create a merge commit with two parents

---

## 6. Network Layer (`src/deep/network/`)

### HTTP Sync (Clone / Push / Pull / Fetch)

Uses a simple pack-based protocol:

1. Client sends a ref advertisement request
2. Server responds with all ref names and SHAs
3. Client determines which objects it's missing
4. Server packs and sends the missing objects
5. Client stores them and updates remote-tracking refs

### P2P Discovery

The P2P layer uses UDP broadcast for local network discovery and TCP for object transfer. Peers announce themselves periodically; `deep p2p discover` listens for announcements and returns a list of available peers.

---

## 7. Platform Features (`src/deep/core/pr.py`, `issue.py`, `pipeline.py`)

Pull Requests, Issues, and Pipelines are stored as JSON metadata files inside `.deep/platform/`. They travel with the repository — clone a repo and you get the full PR history.

### CI/CD Pipeline

The pipeline runner reads `.deepci.yml`, parses job definitions, and executes them in-process (or in a sandboxed subprocess). Pipeline runs are stored as metadata and can be queried with `deep pipeline list`.

---

## 8. Plugin System (`src/deep/plugins/`)

Plugins are discovered at startup from `.deep/plugins/`. Each plugin can register custom commands that appear in `deep -h` and are dispatched through the same `run(args)` pattern as built-in commands.

---

## Testing

Tests mirror the source structure:

```
tests/
├── cli/          # Command-level integration tests
├── core/         # Unit tests for core engine
├── storage/      # Object store, index, WAL tests
├── network/      # Sync protocol tests
├── integration/  # Multi-command workflow tests
├── security/     # Auth, signing, RBAC tests
└── web/          # Dashboard and API tests
```

Run with `pytest -n auto` for parallel execution. The test suite creates temporary `.deep` repositories in `tmp/` — no real repository is ever modified.

# Deep Architecture

This document describes the internal architecture of Deep VCS. Read this before touching any code.

## Layer Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                            CLI Layer                                 │
│                     src/deep/cli/main.py                             │
│          argparse registration  →  lazy import  →  dispatch          │
├──────────────────────────────────────────────────────────────────────┤
│                          Command Layer                                │
│                     src/deep/commands/*_cmd.py                        │
│          Each file exports run(args). Thin wrappers over Core.        │
├──────────────────────────────────────────────────────────────────────┤
│                           Core Engine                                 │
│                        src/deep/core/                                 │
│     refs · merge · diff · status · graph · stash · rebase · gc       │
│     config · hooks · blame · search · security · pipeline · pr       │
├────────────────┬──────────────────┬──────────────────────────────────┤
│    Storage     │     Network      │           Platform               │
│  src/deep/     │  src/deep/       │  src/deep/core/                  │
│  storage/      │  network/        │  pr.py · issue.py · pipeline.py  │
│  objects.py    │  daemon.py       │  src/deep/server/                │
│  txlog.py      │  p2p.py          │  src/deep/web/                   │
│  pack.py       │  smart_protocol  │                                  │
│  index.py      │  transport.py    │                                  │
│  chunking.py   │  pkt_line.py     │                                  │
│  delta.py      │  client.py       │                                  │
├────────────────┴──────────────────┴──────────────────────────────────┤
│                         Object Model                                  │
│                      src/deep/objects/                                 │
│               packfile.py · fsck.py · hash_object.py                  │
└──────────────────────────────────────────────────────────────────────┘
```

**Hard rule:** Commands import Core. Core imports Storage and Objects. Commands never touch Storage directly. This keeps the dependency graph acyclic and every layer independently testable.

---

## 1. CLI Layer

**File:** `src/deep/cli/main.py` (single file, ~1500 lines)

The CLI is one `argparse.ArgumentParser` with 55+ subcommands. When you type `deep commit -m "fix"`:

1. `build_parser()` constructs the full argument tree (subparsers, flags, epilogs)
2. `main()` calls `parser.parse_args()` → `Namespace` object
3. A long `if/elif` chain maps `args.command` to the correct `run(args)` function
4. The target module is imported lazily — only the invoked command's code is loaded

**Why lazy imports?** Startup latency. Importing the entire codebase on every `deep status` would be slow. Each command module is loaded only when called.

### Error Handling

The `main()` function wraps every `run(args)` call:

| Exception type | Behavior |
|---|---|
| `DeepError` | Clean message to stderr |
| `DeepCLIException` | Exit with specific code |
| Any other `Exception` | "internal error" message (full traceback if `DEEP_DEBUG=1`) |

### Post-Command Hooks

After certain commands (`commit`, `merge`, `rollback`), `main()` runs a state consistency check. After mutation commands (`commit`, `push`, `pull`, `merge`, `add`), it triggers background auto-maintenance (GC + repack if enough time has elapsed).

---

## 2. Content-Addressable Storage

**Directory:** `src/deep/storage/`

This is the foundation. Every piece of data — file content, directory structure, commit metadata — is stored as an **object** identified by its SHA-1 hash.

### Object Types

| Type | Class | What it stores |
|---|---|---|
| `blob` | `Blob` | Raw file content |
| `tree` | `Tree` | Directory listing: `(mode, name, child_sha)` tuples |
| `commit` | `Commit` | Tree SHA + parent SHAs + author/committer + timestamp + message |
| `tag` | `Tag` | Target SHA + tagger + message |
| `delta` | `DeltaObject` | Base SHA + delta instruction stream |
| `chunk` | `Chunk` | Sub-file content block |
| `chunked_blob` | `ChunkedBlob` | Manifest of chunk SHAs |

All objects share a common wire format: `<type> <size>\0<content>`. Objects are zlib-compressed before writing to disk.

### On-Disk Layout

```
.deep/
├── objects/
│   ├── ab/cd/ef1234...     ← Level-2 fan-out (xx/yy/zzzz...)
│   ├── pack/
│   │   ├── pack-<sha>.pack ← Packed objects with delta compression
│   │   └── pack-<sha>.idx  ← DIDX fan-out index for fast lookup
│   └── vault/
│       └── *.dvpf          ← Vault packfiles (format v2)
├── refs/
│   ├── heads/main          ← SHA of the branch tip
│   ├── tags/v1.0.0
│   └── remotes/origin/main
├── HEAD                     ← "ref: refs/heads/main" or detached SHA
├── index                    ← Binary staging area (v2 format)
├── txlog                    ← Write-Ahead Log entries (JSON lines)
├── config                   ← Repository configuration (JSON)
└── platform/                ← PRs, issues, pipeline runs (JSON)
```

### Read Pipeline

When `read_object(objects_dir, sha)` is called:

1. Check Level-2 fan-out path (`objects/xx/yy/zzzz...`)
2. Fall back to Level-1 path (`objects/xx/yyyy...`) for legacy repos
3. Check the global object index cache (`object_index.json`)
4. Search packfiles via DIDX index fan-out tables
5. Search vault files (`.dvpf`)
6. Attempt lazy fetch from promisor remote (partial clone support)
7. If all fail → `FileNotFoundError`

Results are cached in an LRU cache (10,240 entries) for hot-path performance.

### Write Pipeline

1. Compute full serialization: `<type> <size>\0<content>`
2. SHA-1 hash the full serialization
3. Check if object already exists (dedup)
4. zlib compress
5. Write atomically via `AtomicWriter` (write to temp → `os.replace`)

### Index (Staging Area)

The index (`.deep/index`) is a binary file using a custom v2 format:

- Magic bytes: `DIDX`
- Version byte: `2`
- Entries: sorted by path, each containing `(content_hash, mtime_ns, size, path_hash)`
- SHA-256 integrity trailer

The index maps filesystem paths to object SHAs. `deep add` updates the index; `deep commit` reads it to build tree objects.

---

## 3. Write-Ahead Log & Transactions

**Files:** `src/deep/storage/txlog.py`, `src/deep/storage/transaction.py`

This is what makes Deep crash-proof.

### Transaction Lifecycle

```
TransactionManager.__enter__()
    ├── Acquire locks: Repository → Branch → Index (hierarchical order)
    └── Recover stale index backups from previous crashes
        
    tm.begin("commit")
    ├── Create index backup (undo-log pattern)
    └── Write BEGIN record to txlog (JSON line)

    ... do work ...

    tm.commit()
    ├── Flush index to disk (fsync + atomic replace)
    ├── Invalidate all caches (disk + LRU RAM)
    └── Write COMMIT record to txlog

TransactionManager.__exit__()
    ├── If tm.commit() was never called → rollback
    │   ├── Write ROLLBACK record to txlog
    │   └── Restore index from backup (atomic replace)
    └── Release all locks in reverse order
```

### WAL Record Fields

Each `TxRecord` stores: `tx_id`, `operation`, `status`, `timestamp`, `target_object_id`, `branch_ref`, `previous_commit_sha`. Optionally, records can be HMAC-signed for tamper detection during recovery.

### Crash Recovery

On startup, if `txlog.needs_recovery()` returns `True`:

1. Find all incomplete transactions (BEGIN without COMMIT/ROLLBACK)
2. For each: verify signature (if signed), check if target object exists on disk
3. If target object exists → roll forward (update ref, restore working directory)
4. If target object is missing → roll back (restore ref to `previous_commit_sha`)

---

## 4. Reference Management

**File:** `src/deep/core/refs.py`

| Ref type | Path | Content |
|---|---|---|
| Branch | `refs/heads/<name>` | 40-char SHA hex |
| Tag | `refs/tags/<name>` | 40-char SHA hex |
| Remote | `refs/remotes/<remote>/<branch>` | 40-char SHA hex |
| HEAD | `HEAD` | `ref: refs/heads/main` (symbolic) or raw SHA (detached) |

Key functions:

| Function | Purpose |
|---|---|
| `resolve_head(dg_dir)` | Follow HEAD → branch → SHA |
| `update_branch(dg_dir, name, sha)` | Atomically write new SHA to branch ref |
| `log_history(dg_dir)` | BFS parent traversal from HEAD |
| `get_commit_decorations(dg_dir)` | Map SHAs → branch/tag labels for `deep log` |

---

## 5. Merge Engine

**File:** `src/deep/core/merge.py`

### Lowest Common Ancestor (LCA)

`find_all_lcas()` computes all LCAs of two commits using BFS ancestor set intersection. If a binary commit-graph file (`.deep/commit_graph`, format `DHGX`) exists, traversal uses indexed lookups instead of reading loose objects.

If multiple LCAs exist (criss-cross merge), `find_lca()` recursively merges them into a virtual base commit.

### Three-Way Merge

`three_way_merge(objects_dir, base, ours, theirs)` walks the tree entries:

1. If `ours == theirs` → take either (identical change)
2. If `ours == base` → take theirs (only they changed it)
3. If `theirs == base` → take ours (only we changed it)
4. If both are trees → recurse
5. Otherwise → conflict (default to ours, report path)

Returns `(merged_tree_sha, conflict_paths)`.

---

## 6. Network Layer

**Directory:** `src/deep/network/`

### Smart Protocol (`smart_protocol.py`)

Full implementation of upload-pack (fetch/clone) and receive-pack (push):

- SSH and HTTPS transports
- `multi_ack_detailed` negotiation
- `side-band-64k` progress demuxing
- Thin pack resolution
- Capability negotiation (`agent=deep-vcs/1.0`)

The client auto-detects remote type: external Git servers (GitHub, GitLab) get `git-upload-pack`/`git-receive-pack`; Deep daemons get `deep-upload-pack`/`deep-receive-pack`.

### Daemon (`daemon.py`)

`DeepDaemon` is an asyncio TCP server handling push/fetch over PKT-LINE framing. Features:

- Streaming pack reception with 500MB size limit
- Transactional unpack (temporary directory → atomic move)
- Post-push CI/CD pipeline trigger
- RBAC-based access control
- Repository selection for multi-repo hosting

### P2P Engine (`p2p.py`)

Peer discovery via UDP multicast (`239.255.255.250:5007`):

- 5-second beacon interval
- HMAC-signed payloads to prevent spoofing
- Rate limiting (10 packets/second per IP)
- 30-second peer timeout
- Zero-trust commit verification — unsigned commits from peers are rejected

---

## 7. Platform Features

Pull Requests, Issues, and CI/CD Pipelines are stored as JSON in `.deep/platform/`. They replicate with your objects — clone a repo and get the full history.

### CI/CD

The pipeline runner reads `.deepci.yml`, parses job definitions, and executes them in sandboxed subprocesses. Pipeline runs are stored as metadata and queryable via `deep pipeline list`.

---

## 8. Plugin System

Plugins are discovered at startup from `.deep/plugins/`. Each plugin registers custom commands that appear in `deep -h` and are dispatched through the same `run(args)` pattern as built-in commands.

---

## Testing

```
tests/
├── cli/          # Command-level integration tests
├── core/         # Unit tests for core engine
├── storage/      # Object store, index, WAL tests
├── network/      # Sync protocol, daemon tests
├── integration/  # Multi-command workflow tests
├── security/     # Auth, signing, RBAC tests
├── scenarios/    # Edge cases (crash recovery, concurrent writes)
├── e2e_cli/      # End-to-end CLI matrix tests
└── web/          # Dashboard and API tests
```

Run with `pytest -n auto`. The suite creates temporary `.deep` repositories in memory — no real repo is ever modified.

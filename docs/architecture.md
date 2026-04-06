# Deep Architecture

Technical architecture of Deep VCS. Read this before modifying any subsystem.

---

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

**File:** `src/deep/cli/main.py` (~1,500 lines)

The CLI is one `argparse.ArgumentParser` with 55+ subcommands. Execution flow:

1. `build_parser()` constructs the full argument tree (subparsers, flags, epilogs)
2. `main()` calls `parser.parse_args()` → `Namespace` object
3. An `if/elif` chain maps `args.command` to the correct `run(args)` function
4. The target module is imported lazily — only the invoked command's code is loaded

**Why lazy imports?** Startup latency. Importing the entire codebase on every `deep status` would add measurable overhead. Each command module loads only when called.

### Error Handling

| Exception type | Behavior |
|---|---|
| `DeepError` | Clean message to stderr, exit code 1 |
| `DeepCLIException` | Exit with the exception's specific code |
| Any other `Exception` | "internal error" message (full traceback if `DEEP_DEBUG=1`) |

### Post-Command Hooks

After certain commands, `main()` runs additional logic:

- **State consistency check** (`commit`, `merge`, `rollback`): Verifies HEAD, INDEX, and WORKING TREE are consistent. Exits non-zero if they diverge.
- **Auto-maintenance** (`commit`, `push`, `pull`, `merge`, `add`): Triggers background GC + repack if enough time has elapsed since the last maintenance run.
- **WAL recovery** (`commit`, `merge`, `push`, `pull`, `rollback`, `checkout`, `status`): If incomplete transactions exist in the WAL, recovery runs before the command executes.

---

## 2. Content-Addressable Storage

**Directory:** `src/deep/storage/`

Every piece of data — file content, directory structure, commit metadata — is stored as an **object** identified by its SHA-1 hash.

### Object Types

| Type | Class | What it stores |
|---|---|---|
| `blob` | `Blob` | Raw file content |
| `tree` | `Tree` | Directory listing: `(mode, name, child_sha)` tuples |
| `commit` | `Commit` | Tree SHA + parent SHAs + author/committer + timestamp + message |
| `tag` | `Tag` | Target SHA + tagger + message |
| `delta` | `DeltaObject` | Base SHA + delta instruction stream |
| `chunk` | `Chunk` | Sub-file content block (Content-Defined Chunking) |
| `chunked_blob` | `ChunkedBlob` | Manifest of chunk SHAs |

All objects share a common wire format:

```
<type> <size>\0<content>
```

Objects are zlib-compressed before writing to disk.

### On-Disk Layout

```
.deep/
├── objects/
│   ├── ab/cd/ef1234...     ← Level-2 fan-out (xx/yy/zzzz...)
│   ├── pack/
│   │   ├── pack-<sha>.pack ← Packed objects with delta compression
│   │   └── pack-<sha>.idx  ← DIDX fan-out index for O(1) lookup
│   └── vault/
│       └── *.dvpf          ← Vault packfiles (v2 format)
├── refs/
│   ├── heads/main          ← SHA of the branch tip
│   ├── tags/v1.0.0
│   └── remotes/origin/main
├── HEAD                     ← "ref: refs/heads/main" or detached SHA
├── index                    ← Binary staging area (v2 format, DIDX magic)
├── txlog                    ← Write-Ahead Log entries (JSON lines)
├── config                   ← Repository configuration (INI format)
├── keys/
│   └── keyring.enc          ← Encrypted signing keys (HMAC-SHA256)
├── hooks/                   ← pre-commit, pre-push, post-merge scripts
├── plugins/                 ← Runtime-discovered plugin modules (*.py)
└── platform/                ← PRs, issues, pipeline runs (JSON)
```

### Read Pipeline (`read_object`)

When `read_object(objects_dir, sha)` is called:

1. Check Level-2 fan-out path (`objects/xx/yy/zzzz...`)
2. Fall back to Level-1 path (`objects/xx/yyyy...`) for legacy repos
3. Check the global object index cache (`object_index.json`)
4. Search vault files (`.dvpf`)
5. Search packfiles via DIDX index fan-out tables
6. Attempt lazy fetch from promisor remote (partial clone support)
7. If all fail → `FileNotFoundError`

Results are cached in a `functools.lru_cache` (10,240 entries) for hot-path performance. Delta objects are reconstructed transparently with a max chain depth of 50 to prevent pathological recursion.

### Write Pipeline

1. Compute full serialization: `<type> <size>\0<content>`
2. SHA-1 hash the full serialization
3. Check if object already exists (content-addressable dedup)
4. zlib compress the full serialization
5. Write atomically via `AtomicWriter` (write to temp file → `os.replace`)

### Index (Staging Area)

The index (`.deep/index`) is a binary file using a custom v2 format:

- **Magic bytes:** `DIDX`
- **Version byte:** `2`
- **Entries:** sorted by path, each containing `(content_hash, mtime_ns, size, path_hash)`
- **Integrity trailer:** SHA-256 checksum

The index maps filesystem paths to object SHAs. `deep add` updates the index; `deep commit` reads it to construct the tree hierarchy.

### Why WAL + CAS Makes Deep Safer Than Traditional VCS

Traditional VCS implementations update refs and the working tree as independent, non-atomic operations. If the process is killed between updating the ref pointer and writing the tree objects, the repository can be left in a corrupted state that requires manual intervention.

Deep's approach:

1. **Write-Ahead Log records intent before any mutation.** The WAL entry captures the operation type, target object, branch ref, and previous commit SHA. If the process crashes, the WAL tells recovery exactly what was in progress.
2. **Content-addressable objects are immutable and self-verifying.** Once written, an object's SHA-1 hash guarantees its integrity forever. There's no partial-write corruption risk — either the object matches its hash or it doesn't exist.
3. **Recovery is deterministic.** On startup, if incomplete transactions exist: (a) if the target object was fully written, roll forward; (b) if not, roll back to the previous commit SHA. No heuristics, no data loss.

This combination means you can safely `kill -9` a `deep commit` mid-flight and resume seamlessly.

---

## 3. Write-Ahead Log & Transactions

**Files:** `src/deep/storage/txlog.py`, `src/deep/storage/transaction.py`

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

Each `TxRecord` contains:

| Field | Purpose |
|---|---|
| `tx_id` | Unique ID: `<operation>_<timestamp_ms>_<uuid_suffix>` |
| `operation` | `commit`, `checkout`, `merge`, `merge-ff`, `merge-3way`, `reset-hard`, etc. |
| `status` | `BEGIN`, `COMMIT`, `ROLLBACK` |
| `timestamp` | Unix timestamp (float) |
| `target_object_id` | SHA of the new commit/object being created |
| `branch_ref` | The ref being updated (e.g. `refs/heads/main`) |
| `previous_commit_sha` | SHA of the ref before the operation (rollback target) |
| `signature` | Optional HMAC-SHA256 signature for tamper detection |
| `signing_key_id` | Key ID used for the signature |

### Crash Recovery Algorithm

On startup, if `txlog.needs_recovery()` returns `True`:

1. Find all incomplete transactions (BEGIN without matching COMMIT/ROLLBACK)
2. For each incomplete transaction:
   - If signed: verify HMAC signature. Reject tampered records.
   - If `target_object_id` exists on disk → **roll forward** (update ref, restore working directory if needed)
   - If `target_object_id` is missing → **roll back** (restore ref to `previous_commit_sha`)
   - If neither is possible → abort the transaction with a ROLLBACK record
3. For operations that modify the working directory (`checkout`, `reset-hard`, `merge`), recovery also restores file contents from the target commit's tree.

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
| `resolve_revision(dg_dir, rev)` | Resolve branch name, tag name, or partial SHA to full SHA |

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

`DeepDaemon` is an asyncio TCP server handling push/fetch over PKT-LINE framing:

- Streaming pack reception with 500MB size limit
- Transactional unpack (temporary directory → atomic move)
- Post-push CI/CD pipeline trigger
- RBAC-based access control
- Repository selection for multi-repo hosting

### P2P Engine (`p2p.py`)

Zero-config peer discovery via UDP multicast (`239.255.255.250:5007`):

| Property | Value |
|---|---|
| Beacon interval | 5 seconds |
| Payload signing | HMAC-SHA256 (per-repository signing key) |
| Rate limiting | 10 packets/second per source IP |
| Peer timeout | 30 seconds |
| Packet size limit | 4,000 bytes |
| Commit policy | Zero-trust — unsigned commits from peers are rejected |

Discovery flow:

1. Node broadcasts its `node_id`, `repo_name`, branch states, and presence info on the multicast group
2. Listener receives beacon, verifies HMAC signature, rejects unsigned or tampered payloads
3. Peers are tracked with a 30-second expiry window
4. `discover_conflicts()` compares local branch state with peer branch state to identify divergent histories

### Offline Queue (`offline_queue.py`)

Operations that fail due to network unavailability are queued and replayed when connectivity returns.

---

## 7. Security Architecture

**File:** `src/deep/core/security.py`

### Key Management

Keys are stored in `.deep/keys/keyring.enc`, encrypted with a passphrase-derived key (SHA-256 of passphrase → XOR stream cipher). Operations:

| Operation | Method |
|---|---|
| Generate a key | `KeyManager.generate_key()` → 32-byte HMAC-SHA256 secret |
| Get active key | `KeyManager.get_active_key()` → most recent non-revoked key |
| Revoke a key | `KeyManager.revoke_key(key_id)` → marks as revoked, re-encrypts keyring |
| Rotate keys | `KeyManager.rotate_key()` → revoke old + generate new |

### Commit Signing

`CommitSigner.sign(data)` produces an HMAC-SHA256 signature stored in the commit's `gpgsig` header. Signature format: `SIG:<key_id>:<hex_signature>`.

Verification rejects signatures from revoked keys.

### Merkle Audit Chain

`MerkleAuditChain` builds SHA-256 hash chains over audit log entries. Each entry's hash is `SHA-256(prev_hash | entry_data)`. Verification walks the chain and detects any tampering.

### Sandbox Execution

`SandboxRunner` executes scripts in isolated subprocesses with:

- Minimal environment variables (no `PYTHONPATH`)
- Filesystem write restrictions to allowlisted paths only
- Configurable timeout (default: 30 seconds)
- Full operation logging

---

## 8. Platform Features

Pull Requests, Issues, and CI/CD Pipelines are stored as JSON in `.deep/platform/`. They replicate with your objects — clone a repo and get the full project history.

### CI/CD

The pipeline runner reads `.deepci.yml`, parses job definitions (name + command pairs), and executes them in sandboxed subprocesses. Pipeline runs are stored as metadata and queryable via `deep pipeline list`.

---

## 9. Configuration System

**File:** `src/deep/core/config.py`

Configuration uses INI format (not JSON) with a two-level hierarchy:

1. **Local:** `.deep/config` — overrides global settings for this repository
2. **Global:** `~/.deepconfig` — user-wide defaults

Key format: `section.key` (e.g. `user.name`, `core.editor`, `remote.origin.url`).

---

## 10. Hook System

**File:** `src/deep/core/hooks.py`

Hooks are executable scripts in `.deep/hooks/`. Supported hooks:

| Hook name | Triggered by |
|---|---|
| `pre-commit` | Before creating a commit object |
| `pre-push` | Before uploading objects to a remote |
| `post-merge` | After a successful merge |

On Windows, the hook runner searches for `<name>`, `<name>.bat`, `<name>.exe`, `<name>.py`, and `<name>.cmd`. Python scripts are invoked via `sys.executable`.

The hook's exit code determines behavior: non-zero aborts the operation and prints stderr.

Environment variable `DEEP_DIR` is set to the `.deep` directory path for hooks to locate repository internals.

---

## 11. Plugin System

**File:** `src/deep/plugins/plugin.py`

Plugins are discovered at startup from `.deep/plugins/*.py`. Each plugin module receives a `__plugin_manager__` attribute pointing to the `PluginManager` instance. It can call:

- `manager.register_command(name, handler)` — Add a CLI subcommand
- `manager.register_hook(hook_name, callback)` — Register a lifecycle hook (`pre-commit`, `post-commit`, `pre-push`)

Registered commands appear in `deep -h` and are dispatched through the same `run(args)` pattern as built-in commands.

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

```bash
pytest -n auto tests/
```

The suite creates temporary `.deep` repositories in memory — no real repo is ever modified. All 991 tests run in parallel by default.

---

**Next:** [Internals](INTERNALS.md) · [CLI Reference](CLI_REFERENCE.md) · [User Guide](USER_GUIDE.md)

# Deep Internals

This document is for people who want to understand Deep at the byte level. Object encoding, delta compression mechanics, packfile binary format, WAL guarantees, and the P2P gossip protocol.

If you just want to use Deep, read the [User Guide](USER_GUIDE.md). If you want to understand the layer boundaries, read [Architecture](ARCHITECTURE.md). This document assumes you've read both.

---

## 1. The Deep Object Model

Every object in Deep follows one wire format:

```
<type> <size>\0<content>
```

Where:
- `<type>` is an ASCII string: `blob`, `tree`, `commit`, `tag`, `delta`, `chunk`, `chunked_blob`
- `<size>` is the decimal byte length of `<content>`, encoded as ASCII
- `\0` is a single null byte separator
- `<content>` is the raw payload (format depends on type)

The SHA-1 hash is computed over the entire `<type> <size>\0<content>` byte string. This hash is the object's identity.

### Blob

```
blob <N>\0<raw file bytes>
```

No internal structure. The content is the file exactly as it appeared on disk.

### Tree

```
tree <N>\0<entry><entry>...
```

Each entry is:

```
<mode> <name>\0<20-byte raw SHA-1>
```

- `<mode>`: ASCII decimal file mode (`100644` for regular files, `40000` for directories, `100755` for executables, `120000` for symlinks)
- `<name>`: UTF-8 filename (no path separators, no null bytes)
- SHA-1: 20 raw bytes (not hex-encoded)

Entries are sorted: directories sort with a trailing `/` appended for comparison (e.g., `dir/` sorts after `dir.txt`). This matches Git's tree sorting algorithm for byte-compatible migrations.

**Mode normalization:** `040000` is canonicalized to `40000` on read. Tree validation enforces that directory-mode entries point to tree objects and blob-mode entries point to blob objects (via `TreeEntry.validate()`).

### Commit

```
commit <N>\0tree <tree_sha>\n
parent <parent_sha>\n        (zero or more)
author <name> <timestamp> <tz>\n
committer <name> <timestamp> <tz>\n
x-deep-sequence <int>\n      (optional, Deep-specific)
gpgsig -----BEGIN PGP SIGNATURE-----\n
 <sig lines>\n                (optional)
 -----END PGP SIGNATURE-----\n
\n
<message>
```

Timestamps are Unix epoch integers. Timezone is `±HHMM` format. The `x-deep-sequence` header is a Deep-specific monotonically increasing counter used for CRDT-style conflict ordering.

### Tag

```
tag <N>\0object <target_sha>\n
type <target_type>\n
tag <tag_name>\n
tagger <name> <timestamp> <tz>\n
\n
<message>
```

### DeltaObject

```
delta <N>\0<base_sha_hex>\n<delta_instruction_bytes>
```

Delta objects reference a base object and store a compact instruction stream to reconstruct the target. See Section 2 for the instruction format.

### Chunk and ChunkedBlob

Large files can be split into content-defined chunks:

- `chunk`: `chunk <N>\0<raw bytes>` — one piece of a larger file
- `chunked_blob`: `chunked_blob <N>\0<sha1>\n<sha2>\n...` — a manifest listing chunk SHAs in order

---

## 2. Delta Compression

**File:** `src/deep/storage/delta.py`

Deep uses instruction-based deltas with two opcodes: COPY and INSERT.

### Delta Wire Format

```
[8 bytes: target_size (big-endian uint64)]
[instruction]*
```

Each instruction:

| Byte | Meaning | Payload |
|---|---|---|
| `0x80` | COPY from source | `<8B offset><8B length>` (big-endian) |
| `0x00` | INSERT literal data | `<8B length><data>` (big-endian) |

### Delta Creation (`create_delta`)

Uses a Rabin-Karp rolling hash with parameters:

- Block size: 16 bytes
- Hash base: 257
- Hash modulus: 10⁹ + 7

Algorithm:

1. Build a hash index over the source, mapping hash → list of offsets
2. Roll through the target with the same hash function
3. On hash match, verify the block byte-for-byte and greedily extend the match
4. Emit a COPY instruction for matches ≥ 16 bytes
5. Accumulate unmatched bytes and emit INSERT instructions

The delta is only used if it saves >30% over storing the raw content (`len(delta) + 41 < len(target)`).

### Delta Application (`apply_delta`)

1. Read `target_size` from the first 8 bytes
2. Walk instructions: COPY reads from source at the given offset; INSERT appends literal data
3. Verify final output length matches `target_size`

Safety: target size is capped at 500MB. Delta chain depth is tracked per-thread and capped at 50 to prevent cycles.

---

## 3. Packfile Format

**File:** `src/deep/storage/pack.py`

### Pack Structure

```
[4B: "PACK" signature]
[4B: version (uint32 big-endian, currently 1)]
[4B: object count (uint32 big-endian)]
[object entries...]
[20B: SHA-1 trailer of all preceding bytes]
```

Each object entry:

```
[1B: type_id]
[8B: compressed_size (uint64 big-endian)]
[20B: base_sha (only for type_id 7 / delta)]
[compressed_size bytes: zlib-compressed payload]
```

Type IDs:

| ID | Type |
|---|---|
| 1 | blob |
| 2 | tree |
| 3 | commit |
| 4 | tag |
| 5 | chunk |
| 6 | chunked_blob |
| 7 | in-pack delta |

### Pack Creation (`PackWriter.create_pack`)

1. Sort objects by `(type, size)` for optimal delta windows
2. Maintain a sliding window of 10 recent objects
3. For each object, attempt delta compression against window entries
4. Only store as delta if savings exceed 30% (`len(delta) < len(raw) * 0.7`)
5. Append SHA-1 trailer for integrity verification
6. Write DIDX index file alongside the pack

### DIDX Index Format

```
[4B: "DIDX" signature]
[4B: version (uint32 big-endian, currently 1)]
[256 × 4B: cumulative fan-out table]
[N × 20B: sorted SHA-1 hashes]
[N × 8B: pack offsets (uint64 big-endian)]
```

The fan-out table enables O(1) bucket lookup: `fanout[first_byte_of_sha]` gives the count of objects with first byte ≤ that value. Binary search within the bucket locates the exact SHA.

### Unpack (`unpack()`)

1. Validate signature and version
2. Stream-decompress each entry using `zlib.decompressobj()` (prevents zip bombs, caps at 50MB per object)
3. Resolve in-pack deltas using a local cache (`sha → full_serialize`)
4. Validate SHA-1 trailer
5. Write loose objects in parallel using `ThreadPoolExecutor`

---

## 4. Content-Defined Chunking

**File:** `src/deep/storage/chunking.py`

For files larger than 256KB, Deep splits them at content-dependent boundaries using a FastCDC-style algorithm.

### Parameters

| Parameter | Value |
|---|---|
| Minimum chunk | 16 KB |
| Average chunk | 64 KB |
| Maximum chunk | 256 KB |
| Boundary mask | `(1 << log2(avg_chunk)) - 1` = `0xFFFF` |

### Algorithm

1. Start scanning at `min_chunk` offset
2. At each byte position, read a 4-byte window as a big-endian integer
3. If `window_value & mask == 0`, split here
4. If `max_chunk` is reached without a boundary, force-split
5. Each chunk is stored as a `Chunk` object; a `ChunkedBlob` manifest lists the chunk SHAs

This means: insert bytes at the start of a 10MB file, and only the first chunk changes. The remaining chunks are identical and deduplicated automatically.

---

## 5. Write-Ahead Log Guarantees

**File:** `src/deep/storage/txlog.py`

### WAL Protocol

The WAL follows a strict protocol:

```
BEGIN  →  (mutations)  →  COMMIT
BEGIN  →  (crash)      →  RECOVERY (next startup)
BEGIN  →  (error)      →  ROLLBACK
```

Each WAL record is a single JSON line appended atomically to `.deep/txlog`. The atomic append uses `AtomicWriter` with file locking.

### HMAC Signing

WAL records can be HMAC-signed using the repository's key management system (`KeyManager`). During recovery, signed records are verified before applying — if the HMAC doesn't match, the transaction is rolled back instead of rolled forward. This prevents a corrupted WAL from applying bad state.

### Recovery Decision Matrix

| Target object exists? | Previous commit known? | Action |
|---|---|---|
| Yes | — | Roll forward (update ref to target) |
| No | Yes | Roll back (restore ref to previous) |
| No | No | Abort (mark as rolled back) |

For operations that modify the working directory (`checkout`, `reset --hard`, `merge`), recovery also restores the working directory by walking the target commit's tree and writing files to disk.

---

## 6. Index Binary Format

**File:** `src/deep/storage/index.py`

### V2 Format

```
[4B: "DIDX" magic]
[1B: version = 2]
[entries...]
[32B: SHA-256 integrity hash]
```

Each entry:

```
[8B: path_hash (uint64, SHA-256 of path truncated to 8 bytes)]
[40B: content_hash (hex-encoded SHA-1)]
[8B: mtime_ns (uint64)]
[8B: size (uint64)]
[2B: path_length (uint16)]
[path_length bytes: UTF-8 path string]
```

Entries are sorted by path for binary search. The SHA-256 trailer covers all preceding bytes and is verified on every read.

---

## 7. P2P Gossip Protocol

**File:** `src/deep/network/p2p.py`

### Discovery

Peers announce themselves via UDP multicast to `239.255.255.250:5007` every 5 seconds.

Beacon payload (JSON):

```json
{
  "node_id": "<hostname>_<8-char-uuid>",
  "repo_name": "<directory name>",
  "port": 9090,
  "branches": {"main": "<sha>", "feature": "<sha>"},
  "presence": {"user": "<hostname>", "file": "src/main.py", "line": 42},
  "timestamp": 1712345678.123,
  "signature": "<hmac_hex>",
  "key_id": "<key_id>"
}
```

### Security

- Beacons are HMAC-signed using the repository's active signing key
- Unsigned or malformed beacons are silently dropped
- Rate limiting: max 10 packets/second per source IP
- Peers time out after 30 seconds of silence

### Conflict Detection

`discover_conflicts()` compares local branch SHAs against all known peers. Any branch where `local_sha != peer_sha` is flagged as divergent with the peer's identity and address.

### Zero-Trust Commit Verification

When receiving commits from a peer, `verify_peer_commit()` checks the commit's cryptographic signature against the known key store. Unsigned commits are rejected — `_reject_unsigned_commit()` returns `True` for any commit without a valid signature.

### Object Transfer

`request_tunnel_data()` opens a direct TCP connection to a peer and requests a specific object by SHA. The peer returns the full serialization if the object exists. The requesting node verifies the SHA-1 hash before storing.

---

## 8. Smart Protocol Wire Format

**File:** `src/deep/network/smart_protocol.py`

Deep's smart protocol is wire-compatible with Git's smart HTTP and SSH protocols.

### PKT-LINE Framing

Each line is prefixed with a 4-character hex length (including the 4 bytes):

```
003eref: refs/heads/main abc123...\n
0000                                  ← flush packet
```

### Upload-Pack (Fetch/Clone)

```
Client                                Server
  │                                      │
  │── GET /info/refs?service=... ──────→│
  │←── ref advertisement + caps ────────│
  │                                      │
  │── POST: want <sha> <caps> ────────→│
  │── POST: have <sha> ──────────────→│
  │── POST: done ─────────────────────→│
  │                                      │
  │←── ACK/NAK ────────────────────────│
  │←── sideband-64k packfile ──────────│
```

Supported capabilities: `multi_ack_detailed`, `side-band-64k`, `thin-pack`, `ofs-delta`, `no-progress`.

### Receive-Pack (Push)

```
Client                                Server
  │                                      │
  │── GET /info/refs?service=... ──────→│
  │←── ref advertisement + caps ────────│
  │                                      │
  │── <old-sha> <new-sha> <ref>\0caps ─→│
  │── flush ──────────────────────────→│
  │── packfile data ──────────────────→│
  │                                      │
  │←── report-status ──────────────────│
```

### Transport Auto-Detection

`SmartTransportClient._detect_remote_type()` determines whether the remote is an external Git server or a Deep daemon:

- HTTPS/HTTP → always `external` (use `git-upload-pack`/`git-receive-pack`)
- SSH to non-localhost → `external`
- SSH to localhost → `deep` (use `deep-upload-pack`/`deep-receive-pack`)

This means `deep push origin main` works against GitHub, GitLab, or a Deep daemon — the client figures out the protocol automatically.

---

## 9. Commit Graph Acceleration

**File:** `src/deep/storage/commit_graph.py`

### DHGX Binary Format

```
[4B: "DHGX" signature]
[1B: version = 1]
[1B: hash version = 1 (SHA-1)]
[4B: commit count (uint32)]
[N × 20B: OID table (raw SHA-1 hashes)]
[N × variable: parent index lists]
[N × 8B: timestamps (uint64)]
[N × 4B: generation numbers (uint32)]
```

The commit graph enables O(1) commit lookup by index and O(parents) traversal without reading any loose objects. This accelerates `find_all_lcas()`, `log_history()`, and reachability queries by orders of magnitude on large repositories.

Rebuild with `deep commit-graph write`. Verify integrity with `deep commit-graph verify`.

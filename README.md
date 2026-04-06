<p align="center">
  <h1 align="center">⚓️ Deep</h1>
  <p align="center">
    <strong>A version control system that doesn't need a server. Or Git.</strong><br>
    Pure Python. P2P-native. Crash-proof. 55+ commands. Zero external dependencies.
  </p>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-3776AB.svg?logo=python&logoColor=white" alt="Python 3.9+"></a>
  <a href="https://github.com/GalHillel/DeepGit/actions"><img src="https://img.shields.io/badge/build-passing-brightgreen.svg" alt="Build passing"></a>
  <a href="https://github.com/GalHillel/DeepGit/releases"><img src="https://img.shields.io/badge/version-1.0.0-orange.svg" alt="Version 1.0.0"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-ff69b4.svg" alt="PRs Welcome"></a>
  <img src="https://img.shields.io/badge/tests-991%2F991-brightgreen.svg" alt="Tests 991/991">
</p>

---

## Why Deep?

Git shipped in 2005. It assumed you'd always have a central server. It assumed no one would want CI/CD baked into their VCS. It assumed content-addressable storage was exotic. Twenty years later, those assumptions are wrong.

**Deep** is a ground-up rewrite. Not a wrapper. Not a shim. A standalone DVCS and developer platform that ships as a single `pip install`. No C extensions. No `libgit2`. No shelling out to `git`.

### What you get

| Capability | How it works |
|---|---|
| **ACID-compliant storage** | Every write passes through a Write-Ahead Log. Kill the process mid-commit — Deep recovers the index on the next invocation. Zero data loss. |
| **Native P2P sync** | No GitHub required. `deep p2p discover` finds peers on your LAN via UDP multicast. `deep p2p sync` pulls branches directly. Cryptographically signed beacons prevent spoofing. |
| **Content-Addressable Object Store** | Blobs, Trees, Commits, and Tags stored as `<type> <size>\0<content>` — the same header format as Git. Migrations are byte-compatible. |
| **Delta compression** | Rabin-Karp rolling hash identifies shared blocks between object versions. Only diffs are stored. Packfiles use a sliding window of 10 objects for optimal compression ratios. |
| **Content-Defined Chunking** | Large files are split at content-dependent boundaries (FastCDC-style) for sub-file deduplication. Move a function between files and Deep stores the chunk once. |
| **Smart Protocol** | Full upload-pack / receive-pack implementation over SSH and HTTPS. `multi_ack_detailed`, `side-band-64k`, thin packs. Push to GitHub without Git installed. |
| **Embedded platform** | Pull Requests, Issues, CI/CD pipelines — stored as JSON inside `.deep/platform/` and replicated with your objects. `deep pr create`, `deep issue list`, `deep pipeline run` all work offline. |
| **AI-assisted workflows** | `deep ai suggest` generates commit messages from diffs. `deep ai predict-merge` forecasts conflicts. `deep ai review` runs automated code review. |
| **55+ CLI commands** | From `deep init` to `deep ultra` — a complete VCS experience with categorized help, ANSI-colored output, and `argparse`-based discoverability. |

---

## Quickstart

```bash
# Install
pip install -e .

# Create a repository
mkdir my-project && cd my-project
deep init

# Do work
echo "hello" > README.md
deep add .
deep commit -m "first commit"

# Check your history
deep log --oneline
```

For system-wide installation via `pipx`, see [docs/INSTALL.md](docs/INSTALL.md).

---

## Architecture (30-second version)

```
CLI (main.py)  ──→  Commands (*_cmd.py)  ──→  Core Engine (core/)
                                                    │
                                        ┌───────────┼───────────┐
                                    Storage/     Network/     Platform/
                                    objects.py   daemon.py    pr.py
                                    txlog.py     p2p.py       pipeline.py
                                    pack.py      smart_protocol.py
                                    index.py     transport.py
```

**Hard rule:** Commands → Core → Storage. Never skip a layer.

For the real deep-dive, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/INTERNALS.md](docs/INTERNALS.md).

---

## Project Layout

```
src/deep/
├── cli/main.py           # 55+ subcommands, single-file argparse dispatcher
├── commands/             # One file per command (*_cmd.py → run(args))
├── core/                 # Business logic: merge, diff, refs, status, graph, stash, gc
├── storage/              # CAS objects, WAL, packfiles, delta compression, index
│   ├── objects.py        # Blob/Tree/Commit/Tag + read/write pipeline
│   ├── txlog.py          # Write-Ahead Log with HMAC-signed entries
│   ├── pack.py           # PACK/DIDX packfile format (delta-compressed)
│   ├── chunking.py       # Content-Defined Chunking (FastCDC-style)
│   └── transaction.py    # ACID transaction manager with lock hierarchy
├── network/              # P2P, daemon, smart protocol, SSH/HTTPS transport
├── objects/              # Low-level packfile parser, fsck, hash_object
├── ai/                   # LLM integration for commit/review/predict
├── plugins/              # Runtime plugin discovery and dispatch
├── server/               # Platform HTTP API
└── web/                  # Deep Studio dashboard (HTML/JS)
```

---

## Documentation

| Document | What it covers |
|---|---|
| [**Architecture**](docs/ARCHITECTURE.md) | Layer diagram, object model, WAL mechanics, ref system |
| [**Internals**](docs/INTERNALS.md) | Byte-level object format, delta encoding, packfile structure, P2P gossip |
| [**User Guide**](docs/USER_GUIDE.md) | Branching, merging, remote sync, stash, rebase |
| [**CLI Reference**](docs/CLI_REFERENCE.md) | Exhaustive list of all 55+ commands with flags and examples |
| [**Contributing**](CONTRIBUTING.md) | Setup, architecture rules, PR checklist, commit conventions |
| [**Installation**](docs/INSTALL.md) | pipx, pip, editable installs, troubleshooting |

---

## Testing

991 tests. Zero tolerance for regressions.

```bash
# Full parallel run
pytest -n auto

# By area
pytest tests/core/
pytest tests/storage/
pytest tests/network/
pytest tests/cli/
```

The test suite creates temporary `.deep` repositories — no real data is ever touched.

---

## License

MIT — do whatever you want with it. See [LICENSE](LICENSE).

<p align="center">
  <sub>Built by <a href="https://github.com/GalHillel">@GalHillel</a> and contributors.</sub>
</p>
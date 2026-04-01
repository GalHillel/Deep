<p align="center">
  <h1 align="center">⚓ Deep</h1>
  <p align="center">
    A version control system that doesn't need a server.<br>
    Built from scratch in Python. P2P-native. AI-optional. Crash-proof.
  </p>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8+-3776AB.svg?logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="https://github.com/GalHillel/DeepGit/actions"><img src="https://img.shields.io/badge/tests-passing-brightgreen.svg" alt="Tests"></a>
  <a href="https://github.com/GalHillel/DeepGit"><img src="https://img.shields.io/badge/version-1.0.0-orange.svg" alt="Version"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-ff69b4.svg" alt="PRs Welcome"></a>
</p>

---

## Why Deep?

Git changed the world. But it was designed in 2005 for the Linux kernel — before P2P protocols matured, before content-addressable storage was mainstream, before anyone thought a VCS should ship with its own CI runner.

**Deep** is what happens when you start over with modern assumptions:

| | Git | Deep |
|---|---|---|
| **Sync model** | Central remote required | P2P-native, works offline & serverless |
| **Crash safety** | Loose files, hope for the best | Write-Ahead Log with atomic transactions |
| **Code review** | Needs GitHub/GitLab | Built-in Pull Requests & Issues |
| **CI/CD** | External service | `.deepci.yml` runs locally |
| **AI tooling** | Third-party plugins | Native commit suggestions, conflict prediction |
| **Object integrity** | Trust the filesystem | Cryptographic verification + `fsck` + `doctor` |

Deep is a **single `pip install`**. No daemon. No config. Just `deep init` and go.

---

## Quick Start

```bash
# Install
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit && pip install -e .

# Create a repo
deep init my-project
cd my-project

# Work like you already know how
deep add .
deep commit -m "first commit"
deep status
deep log --oneline
```

### Terminal Output

```
$ deep status
On branch main

Changes to be committed:
  new file:   README.md
  new file:   src/app.py

Changes not staged for commit:
  modified:   config.yaml

nothing to commit, working tree clean
```

---

## Feature Highlights

### 🔗 P2P Synchronization
No GitHub required. Discover peers on your local network and sync directly.
```bash
deep p2p discover          # Find peers
deep p2p sync <peer-id>    # Sync with a specific peer
deep daemon --port 9090    # Serve your repo over the network
```

### 🧠 AI-Powered Workflows
Let the machine write the boring stuff.
```bash
deep commit --ai -a                # AI-generated commit message
deep ai review                     # Automated code review
deep ai predict-merge feature      # Will this merge cleanly?
```

### 🛡️ Crash-Proof Storage
Every write goes through a Write-Ahead Log. If your process dies mid-commit, Deep recovers automatically on the next operation. Zero data loss.

### 📋 Built-in Code Review
Pull Requests and Issues live inside your repository. No external platform needed.
```bash
deep pr create --title "Add auth" --base main
deep pr list
deep issue create -t "Fix login bug" --type bug
```

### 🔬 Diagnostics Toolkit
When things go wrong (they will), Deep gives you real tools.
```bash
deep doctor --fix       # Health check + auto-repair
deep fsck               # Full object connectivity check
deep verify --all       # Cryptographic integrity scan
deep gc                 # Clean up unreachable objects
```

---

## Architecture

Deep has a strict layered architecture. Commands never touch storage directly — everything flows through the core engine.

```
┌─────────────────────────────────────────────────────┐
│                    CLI Layer                         │
│         (argparse → command dispatch)               │
├─────────────────────────────────────────────────────┤
│                  Core Engine                        │
│    refs · status · merge · diff · graph · hooks     │
├──────────────┬──────────────┬───────────────────────┤
│   Storage    │   Network    │     Platform          │
│  CAS + WAL   │  P2P + HTTP  │  PRs · Issues · CI   │
│  Index/Stage │  Daemon      │  Auth · RBAC          │
└──────────────┴──────────────┴───────────────────────┘
```

[Full architecture deep-dive →](docs/ARCHITECTURE.md)

---

## Command Reference

Deep ships with 55+ commands grouped by workflow:

| Category | Commands |
|---|---|
| **Getting Started** | `init`, `clone`, `config` |
| **Staging & Commits** | `add`, `rm`, `mv`, `commit`, `reset`, `stash` |
| **Branching** | `branch`, `checkout`, `merge`, `rebase`, `tag` |
| **History** | `log`, `diff`, `show`, `status`, `graph`, `search`, `ls-tree` |
| **Collaboration** | `push`, `pull`, `fetch`, `remote`, `p2p`, `sync`, `mirror`, `daemon` |
| **Platform** | `pr`, `issue`, `pipeline`, `studio`, `server`, `repo`, `user`, `auth` |
| **AI** | `ai suggest`, `ai review`, `ai predict-merge`, `ultra`, `batch` |
| **Diagnostics** | `doctor`, `fsck`, `gc`, `verify`, `repack`, `benchmark`, `audit`, `rollback` |

Every command has detailed help: `deep <command> --help`

---

## Development

```bash
# Install in dev mode
pip install -e .

# Run full test suite (parallel)
pytest -n auto tests/

# Run a specific test category
pytest tests/core/
pytest tests/cli/
pytest tests/storage/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor workflow.

---

## Project Structure

```
src/deep/
├── cli/          # Argument parsing and command dispatch
├── commands/     # One file per command (add_cmd.py, commit_cmd.py, ...)
├── core/         # VCS engine: refs, merge, diff, status, graph
├── storage/      # CAS object store, index, WAL, transactions
├── network/      # HTTP sync, P2P discovery, daemon
├── objects/      # Blob, Tree, Commit, Tag object definitions
├── platform/     # PR, Issue, Pipeline platform features
├── plugins/      # Runtime plugin discovery and loading
├── server/       # Platform API server
├── web/          # Web dashboard (Studio)
└── utils/        # Colors, progress bars, logging
```

---

## License

MIT — do whatever you want with it. See [LICENSE](LICENSE).

---

<p align="center">
  <sub>Built by <a href="https://github.com/GalHillel">@GalHillel</a> and contributors.</sub>
</p>
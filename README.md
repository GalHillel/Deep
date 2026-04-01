<p align="center">
  <h1 align="center">⚓️ Deep</h1>
  <p align="center">
    <strong>A next-generation version control system that doesn't need a server.</strong><br>
    Built from scratch in Python. P2P-native. Crash-proof. AI-assisted.
  </p>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-3776AB.svg?logo=python&logoColor=white" alt="Python 3.9+"></a>
  <a href="https://github.com/GalHillel/DeepGit/actions"><img src="https://img.shields.io/badge/build-passing-brightgreen.svg" alt="Build passing"></a>
  <a href="https://github.com/GalHillel/DeepGit/releases"><img src="https://img.shields.io/badge/version-1.0.0-orange.svg" alt="Version 1.0.0"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-ff69b4.svg" alt="PRs Welcome"></a>
</p>

---

## Why Deep?

Git changed the world in 2005. But it was designed before peer-to-peer protocols matured, before content-addressable storage was ubiquitous, and before anyone thought a VCS should ship with its own CI runner.

**Deep** is what happens when you start over with modern assumptions. It is a completely independent, `pipx`-installable monolith that replaces Git, GitHub, and your CI provider simultaneously—running securely on your own hardware. 

### Elite Features

*   **🌐 P2P Synchronization**: No central server required. Discover peers on your local network and pull branches directly over the `deep p2p` protocol.
*   **🛡️ Crash-Proof WAL Storage**: Every write goes through a strict Write-Ahead Log. If your machine loses power mid-commit, Deep recovers the index automatically. 
*   **🧠 AI Native**: Built-in `deep ai` workflows automatically analyze diffs, generate optimal commit messages, and aggressively forecast merge conflicts.
*   **📦 Embedded Platform**: Pull Requests, Issues, and CI/CD pipelines (`.deepci.yml`) operate locally and travel seamlessly with your fetched objects.
*   **📸 CAS Architecture**: Compatible header format with Git (`<type> <size>\0<content>`), meaning migrations and cross-system integrations are natively possible.

---

## 🚀 3-Step Quick Start

Deep is a system-level CLI tool. It is recommended to install it globally via `pipx`.

**1. Install**
```bash
pipx install git+https://github.com/GalHillel/DeepGit.git
```

**2. Initialize**
```bash
mkdir my-project && cd my-project
deep init
```

**3. Commit**
```bash
# Add some files and commit
deep add .
deep commit -m "Initial commit to Deep VCS"

# Check your history
deep log --oneline
```

---

## 📚 Documentation 

Deep is extensive. For deep-dives into the architecture, commands, and workflows, consult the official documentation:

*   📖 **[The Deep User Guide](docs/USER_GUIDE.md)** — Step-by-step from branching to remote synching.
*   ⚙️ **[Installation & Setup](docs/INSTALL.md)** — Global installs, shell completion, and developer environments.
*   🛠️ **[CLI Reference](docs/CLI_REFERENCE.md)** — Exhaustive documentation for all 55+ `deep` commands.
*   🏗️ **[Architecture Deep-Dive](docs/ARCHITECTURE.md)** — Understand the internal CAS, WAL, and protocol layers.
*   💻 **[Contributing Guidelines](CONTRIBUTING.md)** — How to write code for Deep VCS.
*   🧪 **[Developer Guide](docs/development.md)** — Implementation standards and testing workflows.

---

## License

MIT — do whatever you want with it. See [LICENSE](LICENSE).

<p align="center">
  <sub>Built by <a href="https://github.com/GalHillel">@GalHillel</a> and contributors.</sub>
</p>
# DeepGit User Guide: Next-Generation Development

Welcome to the future of version control. DeepGit is more than just a VCS—it is a comprehensive developer platform that integrates decentralized storage, AI-powered assistance, and built-in project management.

---

## 🚀 Getting Started

### 1. Initializing Your First Repository
To transform any directory into a Deep-managed workspace:
```bash
deep init
```
This creates a `.deep` folder, setting up the local object database, index, and write-ahead log (WAL).

### 2. The Core Workflow: Add, Commit, Push
Tracking changes in Deep is designed to be familiar yet more robust:
```bash
# Stage your changes
deep add .

# Record a signed transaction
deep commit -m "feat: implement core storage layer"

# Direct synchronization with a remote or peer
deep push origin main
```

---

## 🌿 Branching & History

### Visualizing the DAG
Deep includes a built-in high-fidelity history visualizer:
```bash
deep graph --all
```
This renders your commit graph (Directed Acyclic Graph) in ASCII, perfectly showing merges, forks, and references.

### Switching Contexts
Switch between features or experiments instantly:
```bash
deep checkout -b feature-ai
```

---

## 🧠 AI-Powered Development

Deep is the first VCS with a native AI engine. Use it directly from your terminal:
```bash
# Explain what has changed in the last 3 commits
deep ai explain HEAD~3

# Generate a commit message based on your staged changes
deep ai commit
```

---

## 🌐 Collaboration (P2P & Remote)

DeepGit supports standard server-based remotes (Gitea, GitHub, Deep Platform) but also features a revolutionary P2P synchronization mode:
```bash
# Start the peer discovery daemon
deep p2p discover

# Synchronize with a specific peer
deep p2p sync <peer-id>
```

---

## 🛠️ Maintenance & Safety

Deep maintains repository health automatically, but you can trigger "God Mode" optimizations:
```bash
# The absolute cleanup and optimization suite
deep ultra

# Need to undo something? Roll back the last transaction safely.
deep rollback
```

---

## 📚 Further Reading
- [Full CLI Reference](../CLI_REFERENCE.md)
- [Architecture Overview](../architecture.md)
- [Contributing to DeepGit](../CONTRIBUTING.md)

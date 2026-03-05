# Remote Operations & P2P Sync

DeepGit is designed for the modern, distributed era. It supports traditional client-server workflows while introducing powerful new Peer-to-Peer (P2P) capabilities.

## 1. Managing Remotes

Just like Git, you can track remote repositories:

```bash
# Add a new remote
deep remote add origin https://github.com/username/repo.git

# List all tracked remotes
deep remote list
```

## 2. Pushing and Pulling

Share your work and stay up to date:

```bash
# Push your local changes to origin
deep push origin main

# Pull the latest changes from origin
deep pull origin main
```

## 3. P2P Synchronization (Next-Gen)

One of DeepGit's most powerful features is its ability to sync directly with peers on your local network or via a known peer ID.

### Discovering Peers
To see who is available for synchronization on your local network:

```bash
deep p2p discover
```

### Direct Peer Sync
If you have a peer ID, you can sync directly without any central server:

```bash
deep p2p sync <peer-id>
```

## 4. Starting a Daemon

To allow others to sync from your repository over the network, you can start the DeepGit daemon:

```bash
deep daemon --port 9090
```

This transforms your local project into a shareable node on the DeepGit network.

## 5. Cloning Repositories

To create a local copy of an existing repository:

```bash
# Clone from a URL
deep clone https://github.com/username/repo.git

# Clone from a local path
deep clone /path/to/other/repo
```

Next, discover how to harness AI in your workflow in the [Deep AI Features](ai_features.md) guide.

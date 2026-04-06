# Deep User Guide

A practical guide to everyday Deep workflows. This covers the operations you'll use daily — branching, merging, syncing with remotes, stashing, and recovering from mistakes.

For the architecture behind these operations, see [ARCHITECTURE.md](ARCHITECTURE.md). For byte-level details, see [INTERNALS.md](INTERNALS.md).

---

## Getting Started

### Initialize a Repository

```bash
mkdir my-project && cd my-project
deep init
```

This creates a `.deep/` directory with the object store, refs, index, and configuration.

### Your First Commit

```bash
echo "# My Project" > README.md
deep add README.md
deep commit -m "Initial commit"
```

`deep add` hashes the file, stores it as a blob, and updates the staging index. `deep commit` reads the index, builds a tree hierarchy, creates a commit object, and advances the branch pointer.

### Check Status

```bash
deep status
```

Shows three categories: staged changes (green), unstaged modifications (red), and untracked files.

For scripts, use `deep status --porcelain` — the output format is stable and machine-parseable.

---

## Branching

### Create and Switch

```bash
# Create a branch
deep branch feature

# Switch to it
deep checkout feature

# Or do both at once
deep checkout -b feature
```

A branch is just a file in `.deep/refs/heads/` containing a 40-character SHA. Creating one is instantaneous.

### List Branches

```bash
deep branch          # Local branches
deep branch -a       # Include remote-tracking branches
deep branch -v       # Show SHA and upstream info
```

### Delete a Branch

```bash
deep branch -d feature
```

---

## Merging

### Fast-Forward Merge

If the target branch has all your current commits as ancestors, Deep moves the pointer forward. No merge commit is created.

```bash
deep checkout main
deep merge feature    # Fast-forward if possible
```

### Three-Way Merge

If both branches have diverged, Deep finds the Lowest Common Ancestor (LCA), diffs `base→ours` and `base→theirs`, and combines the changes:

```bash
deep merge feature
# Auto-resolves non-conflicting changes
# Marks conflicts with <<<<<<< / ======= / >>>>>>> markers
```

If there are conflicts, edit the files, `deep add` them, and `deep commit`.

### Force a Merge Commit

```bash
deep merge --no-ff feature
```

Always creates a merge commit even if fast-forward is possible.

### Abort a Merge

```bash
deep merge --abort
```

---

## Rebasing

Rebase replays your commits on top of another branch, producing a linear history.

```bash
deep checkout feature
deep rebase main
```

If conflicts arise:

```bash
# Edit conflicting files
deep add <resolved-files>
deep rebase --continue

# Or give up
deep rebase --abort
```

### Interactive Rebase

```bash
deep rebase -i HEAD~3
```

---

## Working with Remotes

### Add a Remote

```bash
deep remote add origin https://github.com/user/repo.git
```

### Push

```bash
deep push origin main

# Set upstream tracking
deep push -u origin main

# Push tags
deep push --tags origin

# Force push (overwrites remote history)
deep push --force origin main
```

### Pull

```bash
deep pull origin main

# Rebase instead of merge
deep pull --rebase origin main
```

### Fetch

```bash
deep fetch origin        # Download without merging
deep fetch --all         # All remotes
```

### Clone

```bash
deep clone https://github.com/user/repo.git
deep clone https://github.com/user/repo.git my-folder

# Shallow clone
deep clone --depth 1 https://github.com/user/repo.git

# Partial clone (skip blobs)
deep clone --filter blob:none https://github.com/user/repo.git
```

---

## P2P Synchronization

Deep can sync directly between machines on your local network with no server.

### Discover Peers

```bash
deep p2p discover
```

Lists all Deep repositories broadcasting on the local network via UDP multicast.

### Sync with a Peer

```bash
deep p2p sync <peer-id>
```

### Start the P2P Listener

```bash
deep p2p start --port 5007
```

---

## Stashing

Temporarily save uncommitted changes.

```bash
# Save current changes
deep stash save "work in progress"

# List stashes
deep stash list

# Restore and remove
deep stash pop

# Restore without removing
deep stash apply

# Drop a stash
deep stash drop

# Clear all stashes
deep stash clear
```

---

## Undoing Things

### Unstage a File

```bash
deep reset HEAD file.txt
```

### Discard Working Tree Changes

```bash
deep checkout -- file.txt
```

### Undo the Last Commit (Keep Changes)

```bash
deep reset --soft HEAD~1
```

### Undo the Last Commit (Discard Everything)

```bash
deep reset --hard HEAD~1
```

### WAL Rollback

If something went wrong and you need to revert the entire last transaction:

```bash
deep rollback
deep rollback --verify    # Check WAL integrity first
```

---

## Tagging

### Lightweight Tag

```bash
deep tag v1.0.0
```

### Annotated Tag

```bash
deep tag -a v1.0.0 -m "Release 1.0.0"
```

### Delete a Tag

```bash
deep tag -d v1.0.0
```

---

## Inspecting History

### Log

```bash
deep log                  # Full details
deep log --oneline        # Compact view
deep log -n 10            # Last 10 commits
deep log --graph          # ASCII graph
deep log main..feature    # Commits on feature not on main
```

### Diff

```bash
deep diff                 # Working tree vs index
deep diff --cached        # Index vs last commit
deep diff HEAD~3 HEAD     # Between two commits
deep diff --stat          # Summary only
```

### Show

```bash
deep show HEAD            # Last commit details
deep show abc1234         # Specific object
```

### Graph

```bash
deep graph                # Current branch
deep graph --all          # All branches
deep graph -n 50          # Limit to 50 commits
```

### Search

```bash
deep search "TODO"        # Find across all history
```

---

## AI-Assisted Workflows

### Generate a Commit Message

```bash
deep commit --ai -a       # Auto-stage + AI message
deep ai suggest           # Preview without committing
```

### Code Review

```bash
deep ai review            # Automated review of staged changes
```

### Predict Merge Conflicts

```bash
deep ai predict-merge --source feature --branch main
```

---

## Repository Maintenance

### Health Check

```bash
deep doctor               # Diagnose problems
deep doctor --fix         # Auto-repair
```

### Garbage Collection

```bash
deep gc                   # Clean up unreachable objects
deep gc --dry-run         # Preview what would be removed
```

### Full Optimization

```bash
deep ultra                # GC + repack + commit-graph rebuild
```

### Integrity Verification

```bash
deep fsck                 # Check object connectivity
deep verify --all         # Cryptographic hash verification
```

---

## Configuration

```bash
deep config user.name "Alice"
deep config user.email "alice@example.com"
deep config --global core.editor vim
```

Configuration is stored in `.deep/config` (local) or `~/.deepconfig` (global) as JSON.

---

## Next Steps

- [CLI Reference](CLI_REFERENCE.md) — every command, every flag
- [Architecture](ARCHITECTURE.md) — how the layers fit together
- [Internals](INTERNALS.md) — byte-level object format and algorithms
- [Contributing](../CONTRIBUTING.md) — how to add features and fix bugs

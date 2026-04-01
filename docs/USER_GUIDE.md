# Deep User Guide

This guide covers everything you need to go from `deep init` to a productive workflow. Every command shown here is copy-pasteable.

## 1. Creating a Repository

```bash
# Initialize in the current directory
deep init

# Or create a new project directory
deep init my-project
cd my-project
```

This creates a `.deep/` directory containing the object database, refs, index, and transaction log.

## 2. Tracking Files

```bash
# Stage a specific file
deep add README.md

# Stage everything in the current directory
deep add .

# Check what's staged
deep status
```

### Understanding Status Output

```
On branch main

Changes to be committed:
  new file:   README.md
  modified:   src/app.py

Changes not staged for commit:
  modified:   config.yaml

Untracked files:
  notes.txt
```

- **Changes to be committed** — these will be included in your next `deep commit`
- **Changes not staged** — modified files that haven't been `deep add`ed yet
- **Untracked files** — new files Deep doesn't know about

## 3. Committing

```bash
# Standard commit
deep commit -m "Add user authentication module"

# Auto-stage all tracked changes + commit
deep commit -a -m "Fix login timeout"

# Let AI write the message for you
deep commit --ai -a

# Sign the commit cryptographically
deep commit -S -m "Security patch"
```

## 4. Viewing History

```bash
# Full log
deep log

# One-line summary
deep log --oneline

# Last 5 commits
deep log -n 5

# Visual graph
deep log --graph

# Show a specific commit's details
deep show HEAD
deep show abc1234
```

## 5. Branching

```bash
# List branches
deep branch

# Create a branch
deep branch feature/auth

# Switch to it
deep checkout feature/auth

# Create and switch in one step
deep checkout -b feature/auth

# Delete a branch
deep branch -d feature/auth
```

## 6. Merging

```bash
# Merge feature branch into current branch
deep merge feature/auth

# If there are conflicts, resolve them manually, then:
deep add .
deep commit -m "Resolve merge conflicts"

# Abort a merge
deep merge --abort
```

## 7. Diffing

```bash
# Working tree vs staging area
deep diff

# Staged changes (what will be committed)
deep diff --cached

# Between two commits
deep diff abc1234 def5678
```

## 8. Stashing

```bash
# Save current changes temporarily
deep stash save

# View stashed changes
deep stash list

# Restore the latest stash
deep stash pop

# Apply without removing from stash
deep stash apply
```

## 9. Tags

```bash
# Create a lightweight tag
deep tag v1.0.0

# Create an annotated tag
deep tag -a v1.0.0 -m "First stable release"

# List all tags
deep tag

# Delete a tag
deep tag -d v1.0.0
```

## 10. Remote Collaboration

### Setting Up Remotes

```bash
# Add a remote
deep remote add origin https://example.com/repo

# List remotes
deep remote list

# Remove a remote
deep remote remove origin
```

### Push, Pull, Fetch

```bash
# Push your branch
deep push origin main

# Pull changes
deep pull origin main

# Fetch without merging
deep fetch origin
```

### Cloning

```bash
# Clone a repository
deep clone https://example.com/repo

# Shallow clone (last N commits only)
deep clone https://example.com/repo --depth 10
```

## 11. Pull Requests (Local)

```bash
# Create a PR
deep pr create --title "Add JWT auth" --base main --head feature/auth

# List open PRs
deep pr list

# Show PR details
deep pr show 1

# Merge a PR
deep pr merge 1

# Add a comment
deep pr comment 1 -m "Looks good"
```

## 12. Issue Tracking

```bash
# Create an issue
deep issue create -t "Login page broken" --type bug --priority high

# List issues
deep issue list

# Close an issue
deep issue close 5
```

## 13. P2P Synchronization

```bash
# Discover peers on your network
deep p2p discover

# Sync with a specific peer
deep p2p sync <peer-id>

# Start the P2P listener
deep p2p start
```

## 14. AI Tools

```bash
# Generate a commit message from staged changes
deep ai suggest

# AI code review
deep ai review

# Predict if a merge will conflict
deep ai predict-merge --source feature --branch main

# Generate a branch name from a description
deep ai branch-name --description "fix the login timeout bug"
```

## 15. Diagnostics

```bash
# Full health check
deep doctor

# Auto-repair common issues
deep doctor --fix

# Object integrity verification
deep fsck

# Cryptographic verification of all objects
deep verify --all

# Garbage collection
deep gc

# Performance benchmark
deep benchmark
```

## 16. Configuration

```bash
# Set your name (local to this repo)
deep config user.name "Alice"

# Set your email globally
deep config --global user.email "alice@example.com"

# Set preferred editor
deep config core.editor vim
```

## Getting Help

Every command supports `--help`:

```bash
deep status --help
deep merge --help
deep ai --help
```

For the top-level command list:

```bash
deep -h
```

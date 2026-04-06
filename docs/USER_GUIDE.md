# Deep User Guide

Practical, day-in-the-life workflows for Deep. This covers the operations you'll use daily — from first commit to merge conflict resolution to P2P sync.

For command-level details, see [CLI Reference](CLI_REFERENCE.md). For architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Getting Started

### Initialize a Repository

```bash
mkdir my-project && cd my-project
```

```bash
deep init
```

This creates a `.deep/` directory with the object store, refs, index, WAL, and configuration.

### Your First Commit

```bash
echo "# My Project" > README.md
```

```bash
deep add README.md
```

```bash
deep commit -m "Initial commit"
```

What happens under the hood:

1. `deep add` hashes the file content, stores it as a blob in the CAS, and updates the staging index
2. `deep commit` reads the index, builds a tree hierarchy, creates a commit object, writes a WAL entry, and advances the branch pointer — all atomically

### Check Status

```bash
deep status
```

Shows three categories:
- **Staged changes** (green) — ready to commit
- **Unstaged modifications** (red) — changed but not staged
- **Untracked files** — new files not yet tracked

For scripts, use:

```bash
deep status --porcelain
```

The output format is stable and machine-parseable.

### Set Your Identity

```bash
deep config user.name "Alice"
```

```bash
deep config user.email "alice@example.com"
```

Global (applies to all repositories):

```bash
deep config --global user.name "Alice"
```

---

## Branching

### Create and Switch

```bash
deep branch feature
```

```bash
deep checkout feature
```

Or do both at once:

```bash
deep checkout -b feature
```

A branch is a file in `.deep/refs/heads/` containing a 40-character SHA. Creating one is instantaneous.

### List Branches

```bash
deep branch
```

```bash
deep branch -a
```

```bash
deep branch -v
```

### Delete a Branch

```bash
deep branch -d feature
```

---

## Merging

### Fast-Forward Merge

If the target branch has all your current commits as ancestors, Deep moves the pointer forward without creating a merge commit.

```bash
deep checkout main
```

```bash
deep merge feature
```

### Three-Way Merge

If both branches have diverged, Deep finds the Lowest Common Ancestor (LCA), diffs `base→ours` and `base→theirs`, and combines:

```bash
deep merge feature
```

Conflicts produce standard `<<<<<<<` / `=======` / `>>>>>>>` markers. To resolve:

```bash
# 1. Edit conflicting files
# 2. Stage resolved files
deep add resolved_file.py
# 3. Commit
deep commit -m "Resolve merge conflicts"
```

### Force a Merge Commit

```bash
deep merge --no-ff feature
```

### Abort a Merge

```bash
deep merge --abort
```

---

## Rebasing

Replay your commits on top of another branch for a clean linear history.

```bash
deep checkout feature
```

```bash
deep rebase main
```

If conflicts arise:

```bash
deep add <resolved-files>
```

```bash
deep rebase --continue
```

Or cancel:

```bash
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
```

Set upstream tracking:

```bash
deep push -u origin main
```

Push tags:

```bash
deep push --tags origin
```

Force push (overwrites remote history):

```bash
deep push --force origin main
```

### Pull

```bash
deep pull origin main
```

Rebase instead of merge:

```bash
deep pull --rebase origin main
```

### Fetch

```bash
deep fetch origin
```

```bash
deep fetch --all
```

### Clone

```bash
deep clone https://github.com/user/repo.git
```

```bash
deep clone --depth 1 https://github.com/user/repo.git
```

```bash
deep clone --filter blob:none https://github.com/user/repo.git
```

---

## P2P Synchronization

Deep syncs directly between machines on your local network. No server. No accounts. No configuration.

### Discover Peers

```bash
deep p2p discover
```

Lists all Deep repositories broadcasting on the LAN via UDP multicast.

### Sync with a Peer

```bash
deep p2p sync <peer-id>
```

### Start the P2P Listener

```bash
deep p2p start --port 5007
```

### Check P2P Status

```bash
deep p2p status
```

---

## Stashing

Temporarily shelve uncommitted changes to work on something else.

```bash
deep stash save "work in progress"
```

```bash
deep stash list
```

```bash
deep stash pop
```

```bash
deep stash apply
```

```bash
deep stash drop
```

```bash
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

### Undo the Last Commit (Keep Changes Staged)

```bash
deep reset --soft HEAD~1
```

### Undo the Last Commit (Discard Everything)

```bash
deep reset --hard HEAD~1
```

### WAL Rollback

Revert the entire last transaction using the Write-Ahead Log:

```bash
deep rollback
```

Verify WAL integrity before rolling back:

```bash
deep rollback --verify
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

### List Tags

```bash
deep tag
```

---

## Inspecting History

### Log

```bash
deep log
```

```bash
deep log --oneline
```

```bash
deep log -n 10
```

```bash
deep log --graph
```

```bash
deep log main..feature
```

### Diff

```bash
deep diff
```

```bash
deep diff --cached
```

```bash
deep diff HEAD~3 HEAD
```

```bash
deep diff --stat
```

### Show

```bash
deep show HEAD
```

```bash
deep show abc1234
```

### Graph

```bash
deep graph
```

```bash
deep graph --all
```

```bash
deep graph -n 50
```

### Search

```bash
deep search "TODO"
```

---

## AI-Assisted Workflows

### Generate a Commit Message

```bash
deep commit --ai -a
```

Preview without committing:

```bash
deep ai suggest
```

### Code Review

```bash
deep ai review
```

### Predict Merge Conflicts

```bash
deep ai predict-merge --source feature --branch main
```

### Suggest a Branch Name

```bash
deep ai branch-name --description "add caching to storage"
```

### Automated Refactoring

```bash
deep ai refactor
```

---

## Platform Features (Offline PR/Issue/CI)

Deep stores Pull Requests, Issues, and CI/CD pipeline runs as JSON inside `.deep/platform/`. They replicate with your objects — clone a repo and get the full project management history.

### Pull Requests

```bash
deep pr create --title "Add caching" --head feature --base main
```

```bash
deep pr list
```

```bash
deep pr show 1
```

```bash
deep pr merge 1
```

### Issues

```bash
deep issue create --title "Fix login crash" --type bug --priority high
```

```bash
deep issue list
```

```bash
deep issue close 1
```

### CI/CD Pipelines

Define jobs in `.deepci.yml`:

```yaml
jobs:
  - name: "Lint"
    command: "flake8 src/"
  - name: "Test"
    command: "pytest tests/ -q"
```

```bash
deep pipeline run
```

```bash
deep pipeline list
```

```bash
deep pipeline status 1
```

---

## Deep Studio (Visual Dashboard)

Launch the browser-based dashboard:

```bash
deep studio
```

Opens at `http://127.0.0.1:9000`. Features:

- Interactive commit DAG visualization
- File explorer with built-in editor
- Staging, committing, and discarding from the UI
- Branch management and merging
- PR and Issue management panels
- AI commit message suggestions

Custom port:

```bash
deep studio --port 8080
```

For full API documentation, see [STUDIO.md](STUDIO.md).

---

## Repository Maintenance

### Health Check

```bash
deep doctor
```

```bash
deep doctor --fix
```

### Garbage Collection

```bash
deep gc
```

```bash
deep gc --dry-run
```

### Full Optimization

```bash
deep ultra
```

Runs GC + repack + commit-graph rebuild in one pass.

### Integrity Verification

```bash
deep fsck
```

```bash
deep verify --all
```

---

## Hooks

Deep supports repository hooks stored in `.deep/hooks/`. Supported hooks:

| Hook | Trigger |
|---|---|
| `pre-commit` | Before a commit is created |
| `pre-push` | Before objects are uploaded |
| `post-merge` | After a successful merge |

Create a hook:

```bash
mkdir -p .deep/hooks
```

```bash
echo '#!/bin/sh
echo "Running pre-commit checks..."
flake8 src/' > .deep/hooks/pre-commit
```

```bash
chmod +x .deep/hooks/pre-commit
```

On Windows, use `.bat`, `.cmd`, `.exe`, or `.py` extensions. Python hooks are invoked automatically via the interpreter.

Non-zero exit codes abort the operation.

---

## Plugins

Extend Deep with custom CLI commands by dropping Python files into `.deep/plugins/`.

Example plugin (`.deep/plugins/hello.py`):

```python
manager = __plugin_manager__
def hello_handler(args):
    print("Hello from plugin!")
manager.register_command("hello", hello_handler)
```

After saving, `deep hello` is available as a first-class command.

Plugins can also register lifecycle hooks:

```python
def my_pre_commit(*args, **kwargs):
    print("Plugin pre-commit hook running!")
manager.register_hook("pre-commit", my_pre_commit)
```

---

## Configuration Reference

Configuration is stored in INI format. Local config (`.deep/config`) overrides global (`~/.deepconfig`).

| Key | Description | Example |
|---|---|---|
| `user.name` | Author name for commits | `"Alice"` |
| `user.email` | Author email for commits | `"alice@example.com"` |
| `core.editor` | Preferred text editor | `"vim"` |
| `core.promisor` | Promisor remote URL (partial clone) | `"https://..."` |
| `remote.<name>.url` | Remote repository URL | `"https://github.com/..."` |

---

## Environment Variables

| Variable | Description |
|---|---|
| `DEEP_DEBUG` | Set to `1` to enable full stack traces on errors |
| `DEEP_PASSPHRASE` | Passphrase for the encrypted signing keyring |
| `DEEP_SANDBOX` | Set to `1` inside sandboxed script execution |
| `DEEP_DIR` | Set by hooks to the `.deep` directory path |
| `DEEP_TEST_TIMEOUT` | Override timeout for network-related tests (seconds) |

---

## Next Steps

- [CLI Reference](CLI_REFERENCE.md) — every command, every flag
- [Architecture](ARCHITECTURE.md) — how the layers fit together
- [Internals](INTERNALS.md) — byte-level object format and algorithms
- [Deep Studio](STUDIO.md) — visual dashboard documentation
- [AI Features](AI_FEATURES.md) — smart commit messages, code review, merge prediction
- [Contributing](../CONTRIBUTING.md) — how to add features and fix bugs

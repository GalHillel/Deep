# Deep CLI Reference

Complete reference for all `deep` commands. Every command is copy-pasteable. Run `deep <command> --help` for full inline documentation.

---

## Core Workflow

### `deep init`

Initialize a new Deep repository.

```bash
deep init
```

```bash
deep init my-project
```

```bash
deep init --bare
```

| Flag | Description |
|---|---|
| `[path]` | Target directory (default: current directory) |
| `--bare` | Create a bare repository without a working tree |

### `deep clone`

Clone an existing repository with full history.

```bash
deep clone https://github.com/user/repo.git
```

```bash
deep clone https://github.com/user/repo.git my-folder
```

```bash
deep clone --depth 1 https://github.com/user/repo.git
```

```bash
deep clone --filter blob:none https://github.com/user/repo.git
```

```bash
deep clone --mirror https://github.com/user/repo.git
```

| Flag | Description |
|---|---|
| `<url>` | Repository URL or local path |
| `[dir]` | Target directory name |
| `--depth <N>` | Create a shallow clone with N commits of history |
| `--filter <spec>` | Partial clone object filter (e.g. `blob:none`) |
| `--shallow-since <date>` | Shallow clone after a date |
| `--mirror` | Bare clone with 1:1 ref mapping |

### `deep config`

Get and set repository or global configuration.

```bash
deep config user.name "Alice"
```

```bash
deep config user.email "alice@example.com"
```

```bash
deep config --global core.editor vim
```

| Flag | Description |
|---|---|
| `<key>` | Configuration key (e.g. `user.name`, `remote.origin.url`) |
| `[value]` | Value to set (omit to read current value) |
| `--global` | Target global config (`~/.deepconfig`) instead of local |

---

## Changes

### `deep add`

Stage file contents for the next commit.

```bash
deep add file.txt
```

```bash
deep add .
```

```bash
deep add src/*.py
```

```bash
deep add -u
```

| Flag | Description |
|---|---|
| `<files...>` | Files or directories to stage |
| `-u`, `--update` | Stage only tracked files (skip new/untracked) |

### `deep commit`

Record staged changes to the repository history.

```bash
deep commit -m "Fix null pointer in parser"
```

```bash
deep commit -a -m "Update all modules"
```

```bash
deep commit --ai -a
```

```bash
deep commit -S -m "Signed release commit"
```

```bash
deep commit --amend -m "Corrected message"
```

```bash
deep commit --allow-empty -m "Trigger CI"
```

| Flag | Description |
|---|---|
| `-m`, `--message` | Commit message |
| `-a`, `--all` | Auto-stage modified and deleted tracked files |
| `--ai` | Generate commit message using Deep AI |
| `-S`, `--sign` | Cryptographically sign the commit (HMAC-SHA256) |
| `--amend` | Rewrite the last commit |
| `--allow-empty` | Create a commit even with no staged changes |

### `deep rm`

Remove files from the working tree and the index.

```bash
deep rm file.txt
```

```bash
deep rm -r folder/
```

```bash
deep rm --cached file.txt
```

| Flag | Description |
|---|---|
| `<files...>` | Files or directories to remove |
| `-r`, `--recursive` | Remove directories recursively |
| `--cached` | Remove from index only, keep file on disk |

### `deep mv`

Move or rename a file and update the index.

```bash
deep mv old.txt new.txt
```

```bash
deep mv file.txt docs/
```

| Flag | Description |
|---|---|
| `<source>` | Source path |
| `<destination>` | Destination path |

### `deep reset`

Reset current HEAD to a specified state.

```bash
deep reset HEAD~1
```

```bash
deep reset --hard HEAD
```

```bash
deep reset --soft HEAD~2
```

| Flag | Description |
|---|---|
| `[commit]` | Target commit (default: HEAD) |
| `--hard` | Reset index + working tree (destructive) |
| `--soft` | Keep everything staged |

### `deep stash`

Save and restore work-in-progress changes.

```bash
deep stash save "work in progress"
```

```bash
deep stash pop
```

```bash
deep stash list
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

| Flag | Description |
|---|---|
| `<action>` | `save`, `push`, `pop`, `apply`, `list`, `drop`, `clear` |
| `[message]` | Optional stash description (for save/push) |

---

## History & Inspection

### `deep status`

Show the working tree and index state.

```bash
deep status
```

```bash
deep status --porcelain
```

```bash
deep status -v
```

| Flag | Description |
|---|---|
| `--porcelain` | Machine-readable output format |
| `-v`, `--verbose` | Detailed tracking information |

### `deep log`

Display commit history.

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

| Flag | Description |
|---|---|
| `--oneline` | Compact one-line-per-commit format |
| `-n`, `--max-count <N>` | Limit output to N commits |
| `--graph` | ASCII graph visualization |
| `[revisions]` | Revision range (e.g. `main..feature`) |

### `deep diff`

Show changes between commits or the working tree.

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

| Flag | Description |
|---|---|
| `--cached`, `--staged` | Show staged changes (index vs HEAD) |
| `--stat` | Summary of changes instead of full diff |
| `[revisions]` | Revision pair to compare |

### `deep show`

Display commit or object details.

```bash
deep show HEAD
```

```bash
deep show abc1234
```

| Flag | Description |
|---|---|
| `[object]` | Object identifier (default: HEAD) |

### `deep graph`

ASCII visualization of the commit DAG.

```bash
deep graph
```

```bash
deep graph --all
```

```bash
deep graph -n 20
```

| Flag | Description |
|---|---|
| `--all` | Include all branches and tags |
| `-n`, `--max-count <N>` | Limit to N commits (default: 100) |

### `deep search`

Search text across all historical versions.

```bash
deep search "TODO"
```

```bash
deep search "^fixed:"
```

| Flag | Description |
|---|---|
| `<query>` | Text string or regular expression |

### `deep ls-tree`

List the contents of a tree object.

```bash
deep ls-tree HEAD
```

```bash
deep ls-tree -r abc1234
```

| Flag | Description |
|---|---|
| `<treeish>` | Tree or commit identifier |
| `-r`, `--recursive` | Recurse into sub-trees |

---

## Branching & Merging

### `deep branch`

Manage repository branches.

```bash
deep branch
```

```bash
deep branch feature
```

```bash
deep branch -d feature
```

```bash
deep branch -a
```

```bash
deep branch -v
```

| Flag | Description |
|---|---|
| `[name]` | Branch to create |
| `-d`, `--delete` | Delete the named branch |
| `-a`, `--all` | List local + remote branches |
| `-v`, `--verbose` | Show SHA and tracking info |
| `-vv` | Extended tracking detail |
| `[start_point]` | Base commit or branch (default: HEAD) |

### `deep checkout`

Switch branches or restore files.

```bash
deep checkout main
```

```bash
deep checkout -b feature
```

```bash
deep checkout abc1234
```

```bash
deep checkout -- file.txt
```

```bash
deep checkout -f main
```

| Flag | Description |
|---|---|
| `<target>` | Branch name or commit SHA |
| `-b`, `--branch` | Create a new branch and switch to it |
| `-f`, `--force` | Force switch even with uncommitted changes |
| `[paths]` | Restore specific files from the target |

### `deep merge`

Join two development histories.

```bash
deep merge feature
```

```bash
deep merge --no-ff dev
```

```bash
deep merge --abort
```

| Flag | Description |
|---|---|
| `<branch>` | Branch to merge into HEAD |
| `--no-ff` | Force a merge commit (no fast-forward) |
| `--abort` | Cancel a merge in progress |

### `deep rebase`

Reapply commits on top of another base.

```bash
deep rebase main
```

```bash
deep rebase --continue
```

```bash
deep rebase --abort
```

```bash
deep rebase -i HEAD~3
```

| Flag | Description |
|---|---|
| `[branch]` | Branch or commit to rebase onto |
| `--continue` | Resume after resolving conflicts |
| `--abort` | Cancel and restore original state |
| `-i`, `--interactive` | Interactive rebase |

### `deep tag`

Create or manage release tags.

```bash
deep tag v1.0.0
```

```bash
deep tag -a v1.0.0 -m "Release 1.0.0"
```

```bash
deep tag -d v1.0.0
```

```bash
deep tag
```

| Flag | Description |
|---|---|
| `[name]` | Tag name (omit to list all) |
| `-a`, `--annotate` | Create an annotated tag object |
| `-m`, `--message` | Tag message (requires `-a`) |
| `-d`, `--delete` | Delete the tag |

---

## Collaboration

### `deep remote`

Manage tracked remote repositories.

```bash
deep remote add origin https://github.com/user/repo.git
```

```bash
deep remote remove origin
```

```bash
deep remote list
```

| Flag | Description |
|---|---|
| `<action>` | `add`, `remove`, `list` |
| `[name]` | Remote name |
| `[url]` | Remote URL |

### `deep push`

Upload local changes to a remote.

```bash
deep push origin main
```

```bash
deep push -u origin main
```

```bash
deep push --tags origin
```

```bash
deep push --force origin main
```

| Flag | Description |
|---|---|
| `[url]` | Remote name or URL |
| `[branch]` | Branch to push |
| `-u`, `--set-upstream` | Set upstream tracking |
| `--tags` | Push all local tags |
| `--force` | Force non-fast-forward push |

### `deep pull`

Fetch and integrate changes from a remote.

```bash
deep pull origin main
```

```bash
deep pull --rebase origin main
```

| Flag | Description |
|---|---|
| `[url]` | Remote name or URL |
| `[branch]` | Branch to integrate |
| `--rebase` | Rebase instead of merge |

### `deep fetch`

Download objects and refs without merging.

```bash
deep fetch origin
```

```bash
deep fetch --all
```

| Flag | Description |
|---|---|
| `[url]` | Remote name or URL |
| `[sha]` | Specific commit SHA to fetch |
| `--all` | Fetch from all remotes |

### `deep p2p`

P2P discovery and direct synchronization.

```bash
deep p2p discover
```

```bash
deep p2p list
```

```bash
deep p2p start --port 5007
```

```bash
deep p2p sync <peer-id>
```

```bash
deep p2p status
```

| Flag | Description |
|---|---|
| `<action>` | `discover`, `list`, `start`, `sync`, `status` |
| `[target]` | Peer ID for sync |
| `--peer` | Manual peer address (`host:port`) |
| `--port` | Listener port |

### `deep sync`

Smart fetch + integrate with upstream.

```bash
deep sync
```

```bash
deep sync --peer /path/to/peer/repo
```

| Flag | Description |
|---|---|
| `--peer` | Manual peer address or path |

### `deep ls-remote`

List references in a remote repository.

```bash
deep ls-remote origin
```

```bash
deep ls-remote https://github.com/user/repo.git
```

### `deep daemon`

Start the Deep network daemon.

```bash
deep daemon --port 9090
```

| Flag | Description |
|---|---|
| `--port` | Network port (default: 9090) |

### `deep mirror`

Create a bare mirror of a repository.

```bash
deep mirror https://github.com/user/repo.git /local/mirror
```

| Flag | Description |
|---|---|
| `<url>` | Source repository URL |
| `<path>` | Local mirror directory |

---

## Platform & AI

### `deep pr`

Manage local Pull Requests.

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

```bash
deep pr close 1
```

```bash
deep pr review 1
```

```bash
deep pr comment 1
```

```bash
deep pr reply 1 2
```

```bash
deep pr resolve 1 2
```

| Flag | Description |
|---|---|
| `<action>` | `create`, `list`, `show`, `merge`, `close`, `reopen`, `sync`, `comment`, `reply`, `resolve`, `review` |
| `[id]` | PR number |
| `[thread]` | Thread number (for reply/resolve) |
| `-t`, `--title` | PR title |
| `-d`, `--description` | PR description |
| `--head` | Source branch |
| `--base` | Target branch |

### `deep issue`

Manage repository issues.

```bash
deep issue create --title "Fix login bug" --type bug --priority high
```

```bash
deep issue list
```

```bash
deep issue show 1
```

```bash
deep issue close 1
```

| Flag | Description |
|---|---|
| `<action>` | `create`, `list`, `show`, `close`, `reopen`, `sync` |
| `[id]` | Issue number |
| `-t`, `--title` | Issue title |
| `-d`, `--description` | Issue description |
| `--type` | Issue type (`bug`, `feature`, `task`) |
| `--priority` | Issue priority (`high`, `medium`, `low`) |

### `deep pipeline`

CI/CD pipeline management.

```bash
deep pipeline run
```

```bash
deep pipeline list
```

```bash
deep pipeline status 1
```

```bash
deep pipeline trigger --commit abc1234
```

| Flag | Description |
|---|---|
| `<action>` | `run`, `trigger`, `list`, `status`, `sync` |
| `[id]` | Pipeline run ID |
| `--commit` | Target commit SHA |

### `deep studio`

Launch the Deep Studio visual dashboard.

```bash
deep studio
```

```bash
deep studio --port 8080
```

| Flag | Description |
|---|---|
| `--port` | Network port (default: 9000) |

### `deep server`

Manage the Deep platform server.

```bash
deep server start
```

```bash
deep server stop
```

```bash
deep server status
```

```bash
deep server restart
```

| Flag | Description |
|---|---|
| `<action>` | `start`, `stop`, `status`, `restart` |

### `deep repo`

Manage platform-hosted repositories.

```bash
deep repo create my-app
```

```bash
deep repo list
```

```bash
deep repo permit --user bob --role write
```

| Flag | Description |
|---|---|
| `<action>` | `create`, `delete`, `list`, `clone`, `permit` |
| `[name]` | Repository name |
| `--user` | Target username |
| `--role` | Access role (`admin`, `write`, `read`) |

### `deep auth`

Platform authentication.

```bash
deep auth login
```

```bash
deep auth status
```

```bash
deep auth logout
```

| Flag | Description |
|---|---|
| `<action>` | `login`, `logout`, `status`, `token` |
| `[token]` | Authentication token |

### `deep user`

Manage platform user accounts.

```bash
deep user create bob
```

```bash
deep user info alice
```

```bash
deep user list
```

| Flag | Description |
|---|---|
| `<action>` | `add`, `create`, `remove`, `list`, `info`, `show` |
| `[username]` | Username |

### `deep ai`

AI-assisted workflow tools.

```bash
deep ai suggest
```

```bash
deep ai review
```

```bash
deep ai predict-merge --source feature --branch main
```

```bash
deep ai branch-name --description "add caching layer"
```

```bash
deep ai refactor
```

```bash
deep ai explain
```

| Flag | Description |
|---|---|
| `[tool]` | `suggest`, `generate`, `analyze`, `branch-name`, `review`, `predict-merge`, `predict-push`, `cross-repo`, `refactor`, `cleanup`, `interactive`, `assistant`, `explain` |
| `[target]` | Target file, branch, or commit SHA |
| `--description` | Prompt to guide the AI |
| `--source` | Source branch (for predict-merge) |
| `--branch` | Target branch (for predict-merge) |

---

## Maintenance

### `deep doctor`

Repository health check and repair.

```bash
deep doctor
```

```bash
deep doctor --fix
```

| Flag | Description |
|---|---|
| `--fix` | Auto-repair detected issues |

### `deep fsck`

Verify object connectivity and validity.

```bash
deep fsck
```

### `deep gc`

Garbage collect unreachable objects.

```bash
deep gc
```

```bash
deep gc --dry-run
```

```bash
deep gc --prune 7200
```

| Flag | Description |
|---|---|
| `--dry-run` | Preview what would be removed |
| `-v`, `--verbose` | Detailed output |
| `--prune <seconds>` | Only prune objects older than this (default: 3600) |

### `deep verify`

Cryptographic integrity verification.

```bash
deep verify
```

```bash
deep verify --all
```

```bash
deep verify --verbose
```

| Flag | Description |
|---|---|
| `--all` | Verify every object in the database |
| `--verbose` | Show progress |

### `deep repack`

Consolidate loose objects into packfiles.

```bash
deep repack
```

```bash
deep repack --no-bitmaps
```

| Flag | Description |
|---|---|
| `--no-bitmaps` | Skip bitmap generation |

### `deep audit`

Security and access audit logs.

```bash
deep audit show
```

```bash
deep audit report
```

```bash
deep audit scan
```

| Flag | Description |
|---|---|
| `[action]` | `show`, `report`, `scan` (default: show) |

### `deep ultra`

Full optimization pass: GC + repack + commit-graph rebuild.

```bash
deep ultra
```

### `deep batch`

Execute a batch of Deep commands atomically.

```bash
deep batch script.deep
```

| Flag | Description |
|---|---|
| `<script>` | Path to the batch script file |

### `deep sandbox`

Execute commands in a secure, isolated environment.

```bash
deep sandbox init
```

```bash
deep sandbox run "ls -la"
```

| Flag | Description |
|---|---|
| `<action>` | `run`, `init` |
| `[cmd]` | Shell command to execute in the sandbox |

### `deep rollback`

Undo the most recent transaction via the WAL.

```bash
deep rollback
```

```bash
deep rollback --verify
```

| Flag | Description |
|---|---|
| `[commit]` | Commit to rollback to (default: parent of HEAD) |
| `--verify` | Check WAL integrity before rollback |

### `deep maintenance`

Run scheduled maintenance tasks.

```bash
deep maintenance
```

```bash
deep maintenance --force
```

| Flag | Description |
|---|---|
| `--force` | Run immediately regardless of schedule |

### `deep benchmark`

Performance benchmarking suite.

```bash
deep benchmark
```

```bash
deep benchmark --compare-legacy
```

```bash
deep benchmark --report
```

| Flag | Description |
|---|---|
| `--compare-legacy` | Include baseline comparison |
| `--report` | Export JSON results |

### `deep migrate`

Convert repository to Deep v2 format.

```bash
deep migrate
```

---

## Diagnostics (Hidden)

These commands are hidden from `deep -h` but available for advanced debugging.

### `deep version`

```bash
deep version
```

### `deep help`

```bash
deep help commit
```

### `deep debug-tree`

```bash
deep debug-tree <sha>
```

### `deep inspect-tree`

```bash
deep inspect-tree <sha>
```

### `deep commit-graph`

```bash
deep commit-graph write
```

```bash
deep commit-graph verify
```

```bash
deep commit-graph clear
```

---

**Next:** [User Guide](USER_GUIDE.md) · [Architecture](ARCHITECTURE.md) · [AI Features](AI_FEATURES.md)

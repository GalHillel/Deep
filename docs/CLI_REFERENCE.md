# Deep CLI Reference

Complete reference for all `deep` commands. Run `deep <command> --help` for full details on any command.

---

## Core Workflow

| Command | Description |
|---|---|
| `deep init [path]` | Initialize a new Deep repository. `--bare` creates a bare repo without a working tree. |
| `deep clone <url> [dir]` | Clone a repository. Supports `--depth`, `--filter`, `--shallow-since`, `--mirror`. |
| `deep config <key> [value]` | Get or set repository configuration. `--global` for user-wide settings. |

---

## Changes

| Command | Description |
|---|---|
| `deep add <files...>` | Stage files for commit. `-u` stages only tracked files. `.` stages everything. |
| `deep commit -m <msg>` | Record staged changes. `-a` auto-stages tracked files. `--ai` generates the message. `-S` signs the commit. `--amend` rewrites the last commit. `--allow-empty` permits empty commits. |
| `deep rm <files...>` | Remove files from working tree and index. `-r` for recursive. `--cached` removes from index only. |
| `deep mv <src> <dst>` | Move or rename a file and update the index. |
| `deep reset [commit]` | Reset HEAD. `--hard` resets index + working tree. `--soft` keeps everything staged. |
| `deep stash <action>` | Actions: `save`, `push`, `pop`, `apply`, `list`, `drop`, `clear`. |

---

## History & Overview

| Command | Description |
|---|---|
| `deep status` | Show working tree and index state. `--porcelain` for machine-readable output. `-v` for verbose. |
| `deep log` | Show commit history. `--oneline` for compact view. `-n <N>` to limit. `--graph` for ASCII visualization. Accepts revision ranges (`main..feature`). |
| `deep diff` | Show changes. `--cached`/`--staged` for staged changes. `--stat` for summary. Accepts revision pairs. |
| `deep show [object]` | Display commit or object content. Defaults to HEAD. |
| `deep graph` | ASCII commit graph. `--all` includes all refs. `-n <N>` limits commits. |
| `deep search <query>` | Search text across all historical versions. |
| `deep ls-tree <treeish>` | List tree contents. `-r` recurses into subtrees. |

---

## Branching & Merging

| Command | Description |
|---|---|
| `deep branch [name]` | List branches (no args) or create a new branch. `-d` deletes. `-a` shows remotes. `-v`/`-vv` for detail. |
| `deep checkout <target>` | Switch branches or detach HEAD. `-b` creates and switches. `-f` forces. Paths restore files. |
| `deep merge <branch>` | Merge a branch into HEAD. `--no-ff` forces a merge commit. `--abort` cancels. |
| `deep rebase <branch>` | Reapply commits onto another base. `--continue` / `--abort` for conflict resolution. `-i` for interactive. |
| `deep tag [name]` | List tags (no args) or create one. `-a -m <msg>` for annotated. `-d` deletes. |

---

## Collaboration

| Command | Description |
|---|---|
| `deep remote <action>` | `add <name> <url>`, `remove <name>`, `list`. |
| `deep push [remote] [branch]` | Upload objects and update remote refs. `-u` sets upstream. `--tags` pushes tags. `--force` for non-fast-forward. |
| `deep pull [remote] [branch]` | Fetch and integrate. `--rebase` rebases instead of merging. |
| `deep fetch [remote]` | Download objects and refs without merging. `--all` fetches all remotes. |
| `deep p2p <action>` | `discover`, `list`, `start`, `sync <peer>`, `status`. `--peer` specifies address. `--port` sets listener port. |
| `deep sync` | Smart fetch + integrate with upstream. `--peer` for manual targeting. |
| `deep ls-remote <url>` | List remote references and their SHAs. |
| `deep daemon` | Start the Deep network daemon. `--port` sets port (default: 9090). |
| `deep mirror <url> <path>` | Create a bare 1:1 mirror of a repository. |

---

## Platform & AI

| Command | Description |
|---|---|
| `deep pr <action>` | `create`, `list`, `show`, `merge`, `close`, `reopen`, `sync`, `comment`, `reply`, `resolve`, `review`. Use `--title`, `--description`, `--head`, `--base` for creation. |
| `deep issue <action>` | `create`, `list`, `show`, `close`, `reopen`, `sync`. Use `--title`, `--description`, `--type`, `--priority`. |
| `deep pipeline <action>` | `run`, `trigger`, `list`, `status`, `sync`. `--commit` targets a specific SHA. |
| `deep studio` | Launch the Deep Studio web dashboard. `--port` sets port (default: 9000). |
| `deep server <action>` | `start`, `stop`, `status`, `restart`. Platform HTTP API server. |
| `deep repo <action>` | `create`, `delete`, `list`, `clone`, `permit`. `--user` and `--role` for access control. |
| `deep auth <action>` | `login`, `logout`, `status`, `token`. |
| `deep user <action>` | `add`, `create`, `remove`, `list`, `info`, `show`. |
| `deep ai [tool]` | `suggest`, `generate`, `analyze`, `branch-name`, `review`, `predict-merge`, `predict-push`, `cross-repo`, `refactor`, `cleanup`, `interactive`, `assistant`, `explain`. |

---

## Maintenance

| Command | Description |
|---|---|
| `deep doctor` | Repository health check. `--fix` auto-repairs. |
| `deep fsck` | Verify object connectivity and validity. |
| `deep gc` | Garbage collect unreachable objects. `--dry-run` previews. `--prune <seconds>` sets age threshold. |
| `deep verify` | Cryptographic integrity verification. `--all` checks every object. `--verbose` shows progress. |
| `deep repack` | Consolidate loose objects into packfiles. `--no-bitmaps` disables bitmap generation. |
| `deep audit [action]` | `show`, `report`, `scan`. Security event logs. |
| `deep ultra` | Full optimization pass: GC + repack + commit-graph rebuild. |
| `deep batch <script>` | Execute a batch of Deep commands atomically from a script file. |
| `deep sandbox <action>` | `run <cmd>`, `init`. Execute commands in an isolated environment. |
| `deep rollback [commit]` | Undo the last transaction via the WAL. `--verify` checks WAL integrity first. |
| `deep maintenance` | Run scheduled maintenance tasks. `--force` runs immediately. |
| `deep benchmark` | Performance benchmarking. `--compare-legacy` adds baseline comparison. `--report` exports JSON. |
| `deep migrate` | Convert repository to Deep v2 format. |

---

## Diagnostics (Hidden)

| Command | Description |
|---|---|
| `deep version` | Print Deep version. |
| `deep help [command]` | Show help for a specific command. |
| `deep debug-tree <sha>` | Forensic tree inspection (hidden from main help). |
| `deep inspect-tree <sha>` | Verify raw tree entry modes (hidden). |
| `deep commit-graph <action>` | `write`, `verify`, `clear`. Manage the binary commit graph index (hidden). |

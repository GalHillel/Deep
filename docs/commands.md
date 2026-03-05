# Command Reference

Deep VCS provides a comprehensive set of commands for version control, repository management, and platform interaction.

## Core VCS Commands

| Command | Description |
|---|---|
| `init` | Create an empty Deep repository or reinitialize an existing one. |
| `add` | Add file contents to the staging area (index) for the next commit. |
| `commit` | Record changes to the repository with a message. |
| `status` | Show the state of the working directory and the staging area. |
| `log` | Show commit history for the current branch. |
| `diff` | Show changes between commits, working tree, and index. |
| `branch` | List, create, or delete branches. |
| `checkout` | Switch branches or restore working tree files. |
| `merge` | Join two or more development histories together. |
| `rebase` | Reapply commits on top of another base tip. |
| `reset` | Reset current HEAD to a specified state. |
| `rm` | Remove files from the working tree and index. |
| `mv` | Move or rename a file, directory, or symlink. |
| `tag` | Create, list, delete, or verify tag objects. |
| `stash` | Stash changes in a dirty working directory away. |

## Remote & Distributed Commands

| Command | Description |
|---|---|
| `clone` | Clone a repository into a new directory. |
| `push` | Update remote refs and associated objects. |
| `pull` | Fetch from and integrate with another repository. |
| `fetch` | Download objects and refs from another repository. |
| `remote` | Manage the set of tracked ("remote") repositories. |
| `mirror` | Create a full mirror of a repository. |
| `daemon` | Start a simple network daemon for repository access. |
| `p2p` | Discover peers and synchronize data over a P2P network. |
| `sync` | High-level synchronization with the upstream branch. |

## Platform & Server Commands

| Command | Description |
|---|---|
| `server` | Manage the Deep Git platform server. |
| `repo` | Create, list, or delete repositories on the platform. |
| `user` | Manage user accounts and profiles. |
| `auth` | Handle authentication and manage session tokens. |
| `pr` | Create, view, and manage Pull Requests. |
| `issue` | Create, view, and manage repository Issues. |
| `pipeline` | Run and monitor CI/CD pipelines. |
| `web` | Launch the local web dashboard. |

## Diagnostics & Dev Tools

| Command | Description |
|---|---|
| `doctor` | Run health checks to detect and fix repository corruption. |
| `benchmark` | Run performance benchmarks and compare with Git. |
| `graph` | Display a visual representation of commit history. |
| `audit` | View history of security-relevant actions. |
| `verify` | Verify the integrity of objects in the database. |
| `sandbox` | Execute commands in a secure, isolated environment. |
| `rollback` | Undo the last transaction using the WAL. |
| `ultra` | AI-powered refactoring and advanced system shortcuts. |
| `batch` | Execute multiple VCS operations atomically from a script. |
| `search` | Search for strings or regex patterns across history. |
| `gc` | Cleanup unreachable objects and optimize storage. |
| `version` | Show Deep VCS version information. |
| `help` | Display help index or detailed help for a command. |

---

*For detailed help on any command, run `deep <command> --help`.*

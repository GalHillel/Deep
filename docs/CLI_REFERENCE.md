# DeepGit CLI Reference

DeepGit provides a comprehensive and high-performance Command-Line Interface (CLI) designed for modern developers. This reference covers all available commands, categorized by their primary function.

---

## 🎨 Premium UX Standards

Every DeepGit command follows a standardized UX pattern for maximum clarity and discoverability:
- **Header**: Clearly identifies the command and its category.
- **Description**: Concise, professional explanation of the command's purpose.
- **Usage**: Standardized argument and option syntax.
- **Examples**: Real-world usage scenarios with colorized comments.
- **Visuals**: Modern ANSI styling with a fallback to plain text for non-TTY environments.

---

## 🌱 Starting a Working Area

| Command | Description | Example |
| :--- | :--- | :--- |
| `init` | Create an empty Deep repository or reinitialize an existing one. | `deep init` |
| `clone` | Clone a repository into a new directory, supporting P2P and standard remotes. | `deep clone <url>` |

---

## 📦 Work on the Current Change

| Command | Description | Example |
| :--- | :--- | :--- |
| `add` | Add file contents to the staging area (index) for the next commit. | `deep add .` |
| `rm` | Remove files from the working tree and the index. | `deep rm file.txt` |
| `mv` | Move or rename a file, directory, or symlink. | `deep mv old.txt new.txt` |
| `reset` | Reset current HEAD to the specified state, optionally clearing the index and working tree. | `deep reset --hard` |
| `stash` | Stash away the changes in a dirty working directory for later use. | `deep stash push` |

---

## 🌿 Examine the History and State

| Command | Description | Example |
| :--- | :--- | :--- |
| `status` | Show the state of the working directory and the staging area. | `deep status` |
| `log` | Display the commit history for the current branch with rich formatting. | `deep log --graph` |
| `diff` | Show changes between commits, the work tree and index, etc. | `deep diff --staged` |
| `show` | Display various types of objects (commits, tags, trees, blobs). | `deep show HEAD` |
| `ls-tree` | List the contents of a tree object including modes and SHA-1 hashes. | `deep ls-tree HEAD` |
| `graph` | Render a high-fidelity, text-based ASCII visualization of the commit history. | `deep graph --all` |
| `search` | Search for exact strings or regular expressions across history and objects. | `deep search 'TODO'` |

---

## 🔄 Grow, Mark and Tweak Your Common History

| Command | Description | Example |
| :--- | :--- | :--- |
| `commit` | Record changes to the repository with a cryptographically-signed message. | `deep commit -m "feat: core"` |
| `branch` | List, create, or delete branches in the repository. | `deep branch -a` |
| `checkout` | Switch branches or restore working tree files. | `deep checkout feature-x` |
| `merge` | Join two or more development histories (branches) together. | `deep merge develop` |
| `rebase` | Reapply commits on top of another base tip for a cleaner history. | `deep rebase main` |
| `tag` | Create, list, delete or verify a tag object signed with GPG/SSH. | `deep tag v1.0.0` |

---

## 🌐 Collaborate (P2P & Remote)

| Command | Description | Example |
| :--- | :--- | :--- |
| `push` | Update remote refs and associated objects to the platform or peers. | `deep push origin main` |
| `pull` | Fetch from and integrate with another repository or a local branch. | `deep pull` |
| `fetch` | Download objects and refs from another repository. | `deep fetch --all` |
| `remote` | Manage the set of tracked ("remote") repositories. | `deep remote add origin <url>` |
| `p2p` | Discover peers and synchronize data over a decentralized network. | `deep p2p discover` |
| `sync` | High-level, atomic synchronization with the upstream branch. | `deep sync` |
| `ls-remote` | List references in a remote repository without cloning. | `deep ls-remote origin` |
| `mirror` | Create a full, exact mirror of a remote repository. | `deep mirror <url>` |
| `daemon` | Start a high-performance network daemon for repository access. | `deep daemon start` |

---

## 🧠 AI & Platform

| Command | Description | Example |
| :--- | :--- | :--- |
| `ai` | Access Deep AI features for code explanation, refactoring, and generation. | `deep ai explain` |
| `pr` | Create, view, and manage Pull Requests on the Deep platform. | `deep pr list` |
| `issue` | Create, view, and manage repository Issues and tasks. | `deep issue show 42` |
| `pipeline` | Run and monitor CI/CD automation pipelines. | `deep pipeline status` |
| `studio` | Launch the Deep Studio IDE, an integrated developer environment. | `deep studio` |
| `repo` | Manage platform-level repository settings and permissions. | `deep repo settings` |
| `user` | Manage local and platform identities and profiles. | `deep user list` |
| `auth` | Handle platform authentication and session management. | `deep auth login` |
| `server` | Manage the local Deep Git platform server and services. | `deep server status` |

---

## 🛠️ Maintenance & Diagnostics

| Command | Description | Example |
| :--- | :--- | :--- |
| `doctor` | Run deep health checks to detect and repair repository corruption. | `deep doctor` |
| `fsck` | Verify the connectivity and validity of objects in the database. | `deep fsck` |
| `gc` | Cleanup unreachable objects and optimize storage through repacking. | `deep gc` |
| `maintenance` | Schedule or run background maintenance tasks (optimization, indexing).| `deep maintenance run` |
| `verify` | Perform a comprehensive security and integrity audit of signatures. | `deep verify` |
| `repack` | Consolidate loose objects into efficient, delta-compressed packfiles. | `deep repack` |
| `benchmark` | Measure the performance of core operations (hashing, commits). | `deep benchmark` |
| `audit` | Browse cryptographically-signed audit logs of repository actions. | `deep audit` |
| `ultra` | Execute a multi-stage, global system optimization for maximum speed. | `deep ultra` |
| `batch` | Execute multiple Deep commands atomically from a script. | `deep batch script.dgit` |
| `sandbox` | Execute untrusted code or builds in a secure, isolated environment. | `deep sandbox run app.py` |
| `rollback` | Undo the last repository transaction using the write-ahead log. | `deep rollback` |
| `commit-graph` | Manage the binary history index for ultra-fast graph traversal. | `deep commit-graph write` |
| `debug` | Access internal forensic tools for low-level database inspection. | `deep debug tree` |

---

*For detailed help on any command, run `deep <command> --help`.*

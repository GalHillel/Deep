# ⚓️ Deep CLI Reference

Deep v1.1.0 - Next-generation Distributed Version Control System.

## Main Menu Categorization

Deep organizes its commands into logical groups to facilitate discovery and workflow efficiency.

### 🌱 STARTING A WORKING AREA
| Command | Description |
| :--- | :--- |
| `init` | Initialize a new empty Deep repository or reinitialize an existing one. |
| `clone` | Create a local copy of a remote Deep repository. |

### 📦 WORK ON THE CURRENT CHANGE
| Command | Description |
| :--- | :--- |
| `add` | Add file contents to the staging area (index) for the next commit. |
| `rm` | Remove files from the working directory and the index. |
| `mv` | Move or rename a file, directory, or symlink. |
| `reset` | Reset current HEAD to a specified state, updating index/working tree. |
| `stash` | Save local changes in a temporary stack for later retrieval. |

### 🌿 EXAMINE THE HISTORY AND STATE
| Command | Description |
| :--- | :--- |
| `status` | Show the current state of the working directory and staging area. |
| `log` | Browse through the commit history of the current branch. |
| `diff` | Show changes between working tree, index, or commits. |
| `show` | Display detailed information about any Deep object (commit, tree, blob). |
| `ls-tree` | List the contents of a tree object. |
| `graph` | Render a text-based ASCII visualization of the commit history. |

### 🔄 GROW, MARK AND TWEAK YOUR COMMON HISTORY
| Command | Description |
| :--- | :--- |
| `commit` | Record staged changes to the repository history with metadata. |
| `branch` | List, create, or delete branches. |
| `checkout` | Switch branches or restore files from a specific commit. |
| `merge` | Integrate changes from another branch into the current one. |
| `rebase` | Forward-port local commits to the tip of another branch. |
| `tag` | Create, list, or delete tag objects (e.g., v1.0.0). |

### 🌐 COLLABORATE (P2P & REMOTE)
| Command | Description |
| :--- | :--- |
| `push` | Update remote references and associated objects from local history. |
| `pull` | Fetch changes from another repository and integrate them. |
| `fetch` | Download objects and refs from a remote without merging. |
| `remote` | Manage the list of tracked remote repositories. |
| `p2p` | Discover peers and sync data over a decentralized network. |
| `sync` | Orchestrate smart synchronization with upstream counters. |
| `ls-remote` | List available references in a remote repository. |
| `mirror` | Create a complete mirror of a Deep repository. |
| `daemon` | Serve the current repository over the network to other clients. |

### 🧠 AI & PLATFORM
| Command | Description |
| :--- | :--- |
| `ai` | Access Deep AI assistants for coding, commit messages, and review. |
| `pr` | Manage Pull Requests and code reviews locally with merge intelligence. |
| `issue` | Hybrid local-first issue tracking engine with optional sync. |
| `pipeline` | Local-first CI/CD pipeline management and GitHub Action sync. |
| `studio` | Launch the Deep Studio IDE interface. |
| `repo` | Manage platform-hosted repositories. |
| `user` | Manage platform user profiles and accounts. |
| `auth` | Manage session tokens and login status. |
| `server` | Control the lifecycle of the Deep platform server. |

### 🛠️ MAINTENANCE & DIAGNOSTICS
| Command | Description |
| :--- | :--- |
| `doctor` | Audit and repair the health of the local repository. |
| `fsck` | Check internal consistency and connectivity of objects. |
| `gc` | Garbage collect unreachable objects and optimize storage. |
| `verify` | Cryptographically verify object integrity via SHA-1 hashes. |
| `repack` | Optimize the object database into efficient packfiles. |
| `benchmark` | Measure and analyze core operation performance. |
| `audit` | Access security logs and administrative change records. |
| `ultra` | Enable high-performance mode for massive repositories. |
| `batch` | Execute multiple Deep commands in a single transactional batch. |
| `sandbox` | Execute potentially unsafe commands in an isolated environment. |
| `rollback` | Roll back state using the Write-Ahead Log (WAL). |

---
⚓️ **Deep** - Build the future of version control.

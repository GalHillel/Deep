# Deep Studio

Deep Studio is a browser-based visual dashboard that ships with every Deep installation. It provides a GUI for repository management without requiring any external tools, accounts, or infrastructure.

## Launch

```bash
deep studio
```

Opens the dashboard at `http://127.0.0.1:9000`.

### Custom Port

```bash
deep studio --port 8080
```

---

## Architecture

Deep Studio is a single-page application served by a built-in `ThreadingHTTPServer`. The frontend is static HTML/JS/CSS bundled in `src/deep/web/static/`. The backend exposes a REST API on `/api/*` endpoints.

```
Browser (SPA)
    │
    ▼
DashboardHandler (HTTP GET/POST)
    │
    ├── Static files: /index.html, /style.css, /app.js
    │
    └── REST API: /api/*
           │
           ▼
    DashboardService
           │
           ├── Repository Status  → core/status.py
           ├── Commit Graph       → core/refs.py + storage/objects.py
           ├── File Editor        → direct filesystem I/O
           ├── Branch Management  → commands/branch_cmd.py, checkout_cmd.py
           ├── Merge Operations   → commands/merge_cmd.py
           ├── PR Management      → core/pr.py (PRManager)
           ├── Issue Tracking     → core/issue.py (IssueManager)
           └── AI Suggestions     → ai/assistant.py
```

Every request creates a new `DashboardService` instance for thread safety. Responses are JSON with CORS headers enabled for local development flexibility.

---

## Features

### DAG Visualization

The `/api/graph` endpoint returns the full commit DAG (up to 100 commits) with branch and tag decoration. The frontend renders this as an interactive graph with clickable nodes.

**V2 Fast Path:** `/api/v2/commits` uses a cached commit graph for instant rendering on large repositories. Falls back to V1 (live object traversal) if the cache is cold.

### Real-Time Repository Status

The `/api/work` and `/api/status` endpoints return the current branch, staged files, modified files, untracked files, and deleted files — the same data as `deep status` but as structured JSON.

### File Explorer and Editor

- `/api/tree` returns the full directory tree (excluding `.git`, `node_modules`, `.deep`).
- `/api/file?path=<relative_path>` reads file content with automatic encoding detection (UTF-8, UTF-16 LE/BE, UTF-8 BOM).
- `/api/file/save` (POST) writes content back with CRLF→LF normalization.
- Files larger than 2MB and binary files are detected and handled gracefully.

**Security:** All file operations enforce path traversal protection. Resolved paths are validated against the repository root before any I/O.

### Staging, Committing, and Discarding

| Endpoint | Method | Action |
|---|---|---|
| `/api/stage` | POST | Stage a file (`deep add`) |
| `/api/unstage` | POST | Unstage a file (restore index entry to HEAD version) |
| `/api/unstage_all` | POST | Unstage all files |
| `/api/discard` | POST | Discard working tree changes for a file |
| `/api/discard_all` | POST | Discard all working tree changes |
| `/api/commit` | POST | Create a commit with message, optional amend |

### Branch Operations

| Endpoint | Method | Action |
|---|---|---|
| `/api/branches` | GET | List all branches |
| `/api/branch/create` | POST | Create a new branch |
| `/api/branch/checkout` | POST | Switch branches (forced checkout) |
| `/api/merge` | POST | Merge a branch into HEAD |

### Commit Exploration

| Endpoint | Method | Action |
|---|---|---|
| `/api/graph` | GET | Full commit DAG with refs |
| `/api/v2/commits` | GET | Cached V2 commit graph |
| `/api/commit/details?sha=<sha>` | GET | Full commit metadata, changed files, semantic analysis |
| `/api/diff?sha=<sha>&path=<path>` | GET | Unified diff for a specific file in a specific commit |
| `/api/v2/diff?sha1=<s1>&sha2=<s2>` | GET | Cached V2 diff between two commits |

### Pull Request Management

| Endpoint | Method | Action |
|---|---|---|
| `/api/prs/local` | GET | List all local PRs |
| `/api/pr/create` | POST | Create a PR (title, head, base, description, reviewers) |
| `/api/pr/review` | POST | Submit a review (approve, request changes, comment) |
| `/api/pr/merge` | POST | Merge a PR |
| `/api/pr/comment` | POST | Add a discussion thread |
| `/api/pr/reply` | POST | Reply to a thread |
| `/api/pr/resolve` | POST | Resolve a thread |

### Issue Tracking

| Endpoint | Method | Action |
|---|---|---|
| `/api/issues/local` | GET | List all local issues |
| `/api/issue/create` | POST | Create an issue (title, body, type, priority) |
| `/api/issue/manage` | POST | Close or reopen an issue |

### File Management

| Endpoint | Method | Action |
|---|---|---|
| `/api/item/create` | POST | Create a file or folder |
| `/api/item/rename` | POST | Rename a file or folder |
| `/api/item/delete` | POST | Delete a file or folder |

### Language Services

Deep Studio includes lightweight IDE features for Python files:

| Endpoint | Method | Action |
|---|---|---|
| `/api/language/format` | POST | Auto-format code (autopep8 for Python, JSON pretty-print) |
| `/api/language/analyze` | POST | Lint analysis (flake8 for Python) |
| `/api/language/complete` | POST | Autocomplete suggestions (Jedi for Python) |
| `/api/language/definition` | POST | Go-to-definition (Jedi for Python) |

### AI Integration

```bash
GET /api/ai/suggest
```

Returns an AI-generated commit message based on the current staging area. Uses the same `DeepAI.suggest_commit_message()` engine available via `deep ai suggest`.

---

## Security Model

- **Path traversal protection** on every file I/O endpoint. Resolved paths are checked against the repository root.
- **Request size limits** — JSON request bodies are read up to `Content-Length`.
- **CORS** is open (`*`) since Studio is intended for local use only.
- **No authentication** — Studio runs on `127.0.0.1` by default. Bind to `0.0.0.0` at your own risk.

---

**Next:** [AI Features](AI_FEATURES.md) · [CLI Reference](CLI_REFERENCE.md) · [User Guide](USER_GUIDE.md)

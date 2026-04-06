# AI-Assisted VCS

Deep embeds a rule-based AI engine that automates the tedious parts of version control. No external API keys. No network calls. Fully self-contained — runs entirely on your machine using AST analysis, diff heuristics, and pattern matching.

## Capabilities at a Glance

| Command | What it does |
|---|---|
| `deep ai suggest` | Generate a Conventional Commits message from staged changes |
| `deep ai review` | Automated code review of staged diffs |
| `deep ai predict-merge` | Forecast merge conflicts before merging |
| `deep ai branch-name` | Suggest a branch name from staged changes or a description |
| `deep ai analyze` | Quality analysis: complexity scoring, large file warnings |
| `deep ai refactor` | Suggest code simplifications (boolean expressions, print→logging) |
| `deep ai explain` | Natural language explanation of recent changes |
| `deep ai cleanup` | Identify and surface dead code and style issues |
| `deep commit --ai -a` | Auto-stage + AI-generated commit message in one shot |

---

## Smart Commit Messages

The commit message generator performs deep analysis of your staged changes:

```bash
deep ai suggest
```

### How It Works

1. **Diff Extraction** — Reads the staging index, computes unified diffs against HEAD for every staged file.
2. **Change Classification** — Each file is scored against commit type candidates (`feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `chore`) using weighted heuristics:
   - File extension (`.md` → docs, `test_*.py` → test)
   - Diff keywords (`fix`, `bug`, `error` → fix)
   - Line delta ratio (mostly additions → feat, mostly deletions → refactor)
   - AST analysis for Python files (new functions → feat, removed functions → refactor)
3. **Scope Detection** — Extracts the dominant module from file paths (`core/`, `storage/`, `network/`, etc.), weighted by change importance.
4. **Description Generation** — Picks action verbs and qualifiers from a curated vocabulary, deterministically seeded from file paths for variety.
5. **Multi-line Body** — Appends per-file summaries with AST-level detail (added/modified/removed symbols, intents like "add error handling").
6. **Risk Assessment** — Computes average complexity score across changed files. Flags high-risk changes.
7. **SemVer Prediction** — Estimates MAJOR/MINOR/PATCH impact based on public symbol additions and removals.
8. **Secret Scanning** — Scans diff additions for patterns matching API keys, tokens, passwords, and bearer tokens. Raises a critical alert if found.

### Example Output

```
feat(storage): implement chunking support

- storage/chunking.py: added chunk_data, FastCDCChunker (add error handling)
- storage/objects.py: modified write_large_blob, ChunkedBlob

[Risk Assessment: Medium]
[SemVer Impact: MINOR]
```

### One-Shot Commit with AI

```bash
deep commit --ai -a
```

Stages all tracked file changes and commits with an AI-generated message in a single command.

---

## Automated Code Review

```bash
deep ai review
```

Scans all staged changes for:

- **TODO markers** left in diff additions
- **Sensitive keywords** (`api_key`, `secret`, `password`) that may indicate credential leaks
- **Debug print statements** (`print(`) that should be replaced with structured logging
- **Large deletion alerts** when removed lines significantly outweigh additions

### Example Output

```
✎ TODO found in changes
🔒 Sensitive keyword found in changes
✎ Debug print remains in changes
⚠ Large deletion alert (-247 lines)
```

---

## Merge Conflict Prediction

```bash
deep ai predict-merge --source feature --branch main
```

Simulates a merge without modifying any state:

1. Walks the commit graph to find the merge base (LCA)
2. Computes modified file sets for both branches since the base
3. Identifies overlapping files — each is a potential conflict source
4. Reports confidence score and conflict-risk files

### Example Output

```
⚠ Potential conflicts in 2 file(s)
  Conflict risk: src/deep/core/merge.py
  Conflict risk: src/deep/storage/objects.py
```

If no overlapping files exist:

```
✅ Merge of feature into main looks clean (no overlapping file changes)
```

---

## Code Quality Analysis

```bash
deep ai analyze
```

For every staged file:

- **Complexity scoring** (0.0–1.0) based on line count, nesting depth, function count, and class count
- **Large file detection** (>500 lines)
- **Trailing whitespace** detection
- Reports a clean bill of health if no issues are found

---

## Branch Name Suggestions

```bash
deep ai branch-name --description "add caching to the object store"
```

Output:

```
feature/add-caching-object-store
```

Without a description, it generates a name from the staged file paths and their semantic tokens.

---

## Refactoring Suggestions

```bash
deep ai refactor
```

The `RefactorEngine` scans staged Python files for:

| Pattern | Suggestion |
|---|---|
| `if x == True:` | Simplify to `if x:` |
| `if x == False:` | Simplify to `if not x:` |
| `if x is True:` | Simplify to `if x:` |
| `if x is False:` | Simplify to `if not x:` |
| `print(...)` statements | Replace with `logger.info(...)` |
| Files > 300 lines | Consider splitting into sub-modules |

---

## AST-Level Analysis

For Python files, the AI engine performs full AST comparison between the old and new versions:

- **Added symbols** — New functions or classes not present in the previous version
- **Removed symbols** — Functions or classes that were deleted
- **Modified symbols** — Functions or classes whose AST dump changed
- **Intent detection** — Recognizes patterns like `try/except` blocks ("add error handling") and context managers with lock-related names ("introduce resource management / thread-safety")
- **Complexity scoring** — Measures nesting depth of control flow structures

This data drives the commit message body, SemVer prediction, and risk assessment.

---

## Metrics

The AI engine tracks internal metrics accessible via the Python API:

```python
from deep.ai.assistant import DeepAI
ai = DeepAI(repo_root)
suggestion = ai.suggest_commit_message()
print(ai.get_metrics())
# {'suggestions_made': 1, 'avg_latency_ms': 12.3, 'avg_confidence': 0.85}
```

Each suggestion records latency (milliseconds) and confidence (0.0–1.0). These metrics help assess the engine's effectiveness over time.

---

## Design Principles

1. **No external API dependency.** Everything runs locally. No OpenAI, no network calls, no API keys.
2. **Deterministic output.** Given the same staged changes, the engine produces the same commit message. Variation is seeded from file paths, not randomness.
3. **Conservative defaults.** The engine falls back to `chore: update project files` when confidence is low rather than generating a misleading message.
4. **Non-blocking.** AI operations never interfere with repository state. They read the index and object store but never write.

---

**Next:** [Deep Studio](STUDIO.md) · [CLI Reference](CLI_REFERENCE.md) · [User Guide](USER_GUIDE.md)

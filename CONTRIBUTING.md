# Contributing to Deep

Thanks for wanting to help. Whether you're fixing a typo, squashing a bug, or adding a whole new command, this guide gets you set up in under five minutes.

## Ground Rules

1. **Don't break the tests.** Every PR must pass `pytest -n auto` with zero failures. No exceptions.
2. **One command, one file.** Commands live in `src/deep/commands/<name>_cmd.py` and export a `run(args)` function.
3. **No raw `print()` for errors.** Use `print(..., file=sys.stderr)` or the helpers in `deep.utils.ux`.
4. **Type hints on new code.** We don't enforce 100% coverage, but new functions should have signatures.

## Setup

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/Deep.git
cd Deep

# 2. Create a virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate

# 3. Install in editable mode
pip install -e .

# 4. Verify
deep version
pytest -n auto tests/ -q
```

All 991 tests should pass. If something fails on a clean clone, that's a bug — open an issue.

## Architecture at a Glance

Deep has a strict layered architecture. Understanding this will save you time:

```
CLI Layer  →  main.py parses args, dispatches to commands/<name>_cmd.py
                ↓
Commands   →  Each command calls into core/ modules. Commands NEVER
              import from storage/ directly.
                ↓
Core       →  refs.py, merge.py, diff.py, status.py, graph.py, etc.
              Business logic lives here.
                ↓
Storage    →  objects.py (CAS), index.py (staging), txlog.py (WAL).
              Raw data persistence. Only core/ should call into this.
                ↓
Network    →  Remote sync (HTTP/SSH), P2P discovery, daemon server.
```

**Key rule:** Commands → Core → Storage. Never skip a layer.

For the full breakdown, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). For byte-level internals, see [docs/INTERNALS.md](docs/INTERNALS.md).

## Making Changes

### Adding a New Command

1. Create `src/deep/commands/yourcommand_cmd.py` with a `run(args)` function
2. Register it in `src/deep/cli/main.py`:
   - Add a subparser with help text, description, epilog, and `formatter_class=argparse.RawTextHelpFormatter`
   - Add the dispatch entry in the `main()` function's if/elif chain
3. Write tests in `tests/cli/` or `tests/core/`

### Modifying an Existing Command

- Find the command in `src/deep/commands/<name>_cmd.py`
- The `run(args)` function receives the parsed `argparse.Namespace`
- **Do not** change how `args` is structured in `main.py` without updating all tests that depend on it

### Running Tests

```bash
# Full suite (parallel)
pytest -n auto tests/

# Specific area
pytest tests/core/
pytest tests/cli/
pytest tests/storage/
pytest tests/network/

# Single test file
pytest tests/core/test_merge.py -v

# With coverage
pytest --cov=deep tests/
```

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add shallow clone support
fix: prevent index corruption on concurrent writes
docs: update architecture diagram
test: add merge conflict edge case
refactor: extract WAL recovery into standalone module
```

## Pull Request Checklist

Before opening a PR, verify:

- [ ] `pytest -n auto` passes with zero failures
- [ ] New code has type hints
- [ ] No `print("debug")` or `print("here")` left in the code
- [ ] Error messages go to `stderr`, not `stdout`
- [ ] If you added a new command, it appears in `deep -h`
- [ ] Your commit messages follow the conventional format

## Code Style

- **PEP 8** with a relaxed 120-character line limit
- **Imports:** `from __future__ import annotations` at the top of every file
- **Errors:** Raise `DeepError` subclasses for expected errors, catch them in `main.py`
- **Output colors:** Use `Color.wrap()` from `deep.utils.ux` — never hardcode ANSI escapes in command files

## Reporting Bugs

Open an issue with:
1. What you did (exact commands)
2. What you expected
3. What actually happened
4. Your Python version and OS

If you can include a failing test case, even better.

## License

By contributing, you agree your code will be released under the [MIT License](LICENSE).

---

Questions? Open a discussion or ping [@GalHillel](https://github.com/GalHillel).

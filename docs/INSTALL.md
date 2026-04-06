# Installing Deep

Deep is a system-level CLI tool. Install it once and use `deep` from any directory on your machine.

## Requirements

- **Python 3.9+** (check with `python --version`)
- **No native C dependencies.** No Docker. No build tools. Pure Python.

---

## For Users — Permanent Global Install

### Option A: pipx (Recommended)

`pipx` isolates Deep's dependencies in a managed virtual environment while exposing the `deep` command globally on your `$PATH`.

```bash
python3 -m pip install --user pipx
```

```bash
python3 -m pipx ensurepath
```

```bash
pipx install git+https://github.com/GalHillel/Deep.git
```

```bash
deep version
```

### Updating

```bash
pipx upgrade deep-vcs
```

### Option B: Global pip

If you don't want to use `pipx`, a direct `pip` install works:

```bash
pip install --user git+https://github.com/GalHillel/Deep.git
```

Ensure your Python `Scripts`/`bin` directory is on your `$PATH`.

---

## For Contributors — Development Mode

Editable (`-e`) installs link the `deep` command directly to your local source tree. Every code change takes effect immediately — no reinstall needed.

### Step 1: Clone

```bash
git clone https://github.com/GalHillel/Deep.git
```

```bash
cd Deep
```

### Step 2: Virtual Environment

```bash
python3 -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
.venv\Scripts\activate
```

### Step 3: Editable Install

```bash
pip install -e .
```

### Step 4: Verify

```bash
deep version
```

```bash
pytest -n auto tests/ -q
```

All 991 tests should pass. If something fails on a clean clone, that's a bug — [open an issue](https://github.com/GalHillel/Deep/issues).

---

## Uninstall

If installed via `pipx`:

```bash
pipx uninstall deep-vcs
```

If installed via `pip`:

```bash
pip uninstall deep-vcs
```

---

## Troubleshooting

### `deep: command not found`

Your `$PATH` doesn't include the directory where `pipx` or `pip --user` installs binaries.

```bash
python -m pipx ensurepath
```

On Linux/macOS, manually add `~/.local/bin`. On Windows, add `%LOCALAPPDATA%\Programs\Python\Python3x\Scripts`.

### `ModuleNotFoundError: No module named 'deep'`

You're running the source code without installing it. Follow the [contributor setup](#for-contributors--development-mode) above.

### Tests fail on Windows with `TimeoutExpired`

Some network-related tests use background daemon processes. Increase the timeout by setting:

```powershell
$env:DEEP_TEST_TIMEOUT = "30"
```

---

**Next:** [User Guide](USER_GUIDE.md) · [CLI Reference](CLI_REFERENCE.md) · [Architecture](ARCHITECTURE.md)

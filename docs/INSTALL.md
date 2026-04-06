# Installing Deep

Deep is a system-level CLI tool. Install it globally so you can run `deep` from any directory without managing virtual environments.

## Requirements

- **Python 3.9+** (check with `python --version`)
- **pipx** (recommended) or **pip**

No native C dependencies. No build tools. No Docker.

---

## 1. System-Wide Install (Recommended)

Using `pipx` isolates Deep's dependencies while exposing the `deep` executable on your `$PATH`.

```bash
# 1. Install pipx if you don't have it
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# 2. Install Deep directly from GitHub
pipx install git+https://github.com/GalHillel/Deep.git

# 3. Verify
deep version
```

### Alternative: Global Pip Install

```bash
pip install --user git+https://github.com/GalHillel/Deep.git
```

Make sure your Python user `Scripts` or `bin` directory is in your `$PATH`.

---

## 2. Developer Install (For Contributors)

If you plan to modify Deep's source code, install it in editable (`-e`) mode so changes apply immediately.

```bash
# 1. Clone
git clone https://github.com/GalHillel/Deep.git
cd Deep

# 2. Create and activate a virtual environment
python3 -m venv .venv

# macOS / Linux:
source .venv/bin/activate

# Windows (PowerShell):
.venv\Scripts\activate

# 3. Install in editable mode
pip install -e .

# 4. Verify
deep version
pytest -n auto tests/ -q
```

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

## Troubleshooting

- **`deep: command not found`**: Your `$PATH` doesn't include the directory where `pipx` or `pip --user` installs binaries. Run `python -m pipx ensurepath` or manually add `~/.local/bin` (Linux/macOS) or `%LOCALAPPDATA%\Programs\Python\Python3x\Scripts` (Windows).
- **`ModuleNotFoundError: No module named 'deep'`**: You're running the source code without installing it. Follow the Developer Install steps above.

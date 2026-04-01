# Installing Deep

Deep is a system-level CLI tool. It should be installed globally so you can execute the `deep` command from any directory on your machine without managing virtual environments.

## Requirements

- **Python 3.9+** (Check with `python --version`)
- **pipx** (Highly recommended) or **pip**

No native C dependencies, no build tools, no Docker required.

---

## 1. System-Wide Install (Recommended)

Using `pipx` is the standard best practice for Python CLI tools. It isolates Deep's dependencies while exposing the `deep` executable globally on your `$PATH`.

```bash
# 1. Install pipx if you don't have it
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# 2. Clone the repository
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit

# 3. Install Deep globally
pipx install .

# 4. Verify installation
deep version
```

### Alternative: Global Pip Install

If you prefer standard `pip`, install it to your user directory:

```bash
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit
pip install --user .
```
*(Ensure your Python user `Scripts` or `bin` directory is in your `$PATH`!)*

---

## 2. Developer Install (For Contributors)

If you plan to modify Deep's source code, you must install it in editable (`-e`) mode so changes apply immediately.

```bash
# 1. Clone
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit

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

- **`deep: command not found`**: Your system `$PATH` does not include the directory where `pipx` or `pip --user` installs binaries. Run `python -m pipx ensurepath` or manually add `~/.local/bin` (Linux/macOS) or `%LOCALAPPDATA%\Programs\Python\Python39\Scripts` (Windows).
- **`ModuleNotFoundError: No module named 'deep'`**: You are trying to run the source code directly without installing it. Follow the Developer Install steps.

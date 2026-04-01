# Installing Deep

## Requirements

- **Python 3.8+** (check with `python --version`)
- **pip** (ships with Python)

That's it. No native dependencies, no build tools, no Docker.

## Install from Source

```bash
# Clone the repository
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit

# Install (editable mode recommended for now)
pip install -e .

# Verify it works
deep version
```

You should see:

```
Deep version 1.0.0
```

## Platform-Specific Notes

### Windows

```powershell
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit
python -m venv .venv
.venv\Scripts\activate
pip install -e .
deep version
```

If `deep` isn't found after install, make sure your Python `Scripts` directory is in your `PATH`:
```powershell
$env:PATH += ";$env:LOCALAPPDATA\Programs\Python\Python311\Scripts"
```

### macOS / Linux

```bash
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
deep version
```

If you get a permission error:
```bash
pip install --user -e .
```

## Dependencies

Deep installs these automatically:

| Package | Why |
|---|---|
| `rich` | Terminal colors and formatting |
| `cryptography` | GPG signing and security features |
| `aiohttp` | Async HTTP for network operations |
| `pydantic` | Data validation for platform features |

## Uninstall

```bash
pip uninstall deep-vcs
```

Verify by running `deep version` — it should return "command not found."

To also remove cloned source:
```bash
rm -rf DeepGit/
```

## Upgrading

```bash
cd DeepGit
git pull
pip install -e .
```

## Troubleshooting

**`deep: command not found`**
Your Python scripts directory isn't in PATH. Run `python -m deep.cli.main version` as a workaround, then fix your PATH.

**`ModuleNotFoundError: No module named 'deep'`**
You didn't install the package. Run `pip install -e .` from the DeepGit directory.

**Permission errors on Linux**
Try `pip install --user -e .` or use a virtual environment (recommended).

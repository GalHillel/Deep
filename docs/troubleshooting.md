# Deep VCS Troubleshooting Guide

This guide provides solutions to common issues you might encounter while using Deep VCS.

## 1. Installation Issues

### `deep: command not found`
- **Cause**: The Python Scripts directory is not in your system's `PATH`.
- **Solution**: 
  - **Windows**: Add `C:\Users\<YourUser>\AppData\Roaming\Python\Python3x\Scripts` to your environment variables.
  - **Unix**: Ensure `~/.local/bin` is in your `$PATH` via `export PATH=$PATH:~/.local/bin` in your `.bashrc` or `.zshrc`.

### `ModuleNotFoundError: No module named 'rich'`
- **Cause**: Dependencies were not installed correctly.
- **Solution**: Run `pip install -r requirements.txt` (if available) or `pip install rich cryptography aiohttp pydantic`.

## 2. Repository Issues

### `FATAL: Repository corrupted. HEAD points to invalid object...`
- **Cause**: This usually happens if a write operation was interrupted or the filesystem experienced an error.
- **Solution**: 
  1. Run `deep doctor` to check for specific issues.
  2. Run `deep rollback` to revert the last transaction (requires WAL enabled).
  3. If all else fails, restore from a backup or a remote mirror.

### `PermissionError` (Windows)
- **Cause**: Another process (like an IDE or a background daemon) might be holding a lock on a file in the `.deep` directory.
- **Solution**: Close any programs that might be accessing the repository and try again.

## 3. Network & P2P

### `Connection refused` when cloning or pulling
- **Cause**: The remote daemon or server is not running or the port is blocked by a firewall.
- **Solution**: 
  - Ensure the target host is running `deep daemon`.
  - Check your firewall settings for the port being used (default: 9090).

### `Peer discovery failed`
- **Cause**: Local network discovery (mDNS/UDP) might be disabled or blocked.
- **Solution**: Ensure your machine is on the same subnet as your peers and that UDP traffic is allowed.

## 4. AI Features

### `AI suggestion failed` or `Connection error`
- **Cause**: DeepGit needs an active internet connection to contact the AI platform (unless a local model is cached).
- **Solution**: Check your internet connection and ensure your API tokens (if required) are valid in `deep config`.

---

Still having trouble? Open an issue on our [GitHub repository](https://github.com/GalHillel/DeepGit/issues) or consult the [Architecture Guide](architecture.md).

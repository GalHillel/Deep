# Installation Guide

This guide provides comprehensive instructions for installing and uninstalling DeepGit on various platforms.

## Prerequisites

- **Python**: Version 3.8 or higher is required.
- **Pip**: The Python package manager should be installed.

## Quick Installation

For most users, installing from the source repository in editable mode is the recommended approach during the current release phase:

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/yourusername/DeepGit.git
    cd DeepGit
    ```

2.  **Install the Package**:
    ```bash
    pip install -e .
    ```

3.  **Verify the Installation**:
    ```bash
    deep --version
    ```

## Installation Options

### 1. Developer (Editable) Mode
This is useful if you plan to contribute to DeepGit or want to test the latest changes.
```bash
pip install -e .
```

### 2. Standard Installation
To install the package normally:
```bash
pip install .
```

## Uninstallation

To completely remove DeepGit from your system:

1.  **Uninstall via Pip**:
    ```bash
    pip uninstall deep-vcs
    ```

2.  **Verify Uninstallation**:
    ```bash
    deep --version
    ```
    *(This should result in a "command not found" error)*

## Troubleshooting

- **Command Not Found**: Ensure your Python scripts directory (e.g., `~/.local/bin` on Linux/macOS or the Scripts folder in your Python installation on Windows) is in your system's `PATH`.
- **Permission Errors**: If you encounter permission issues, try adding `--user` to your pip command: `pip install --user -e .`.

For more detailed issues, please refer to the [Troubleshooting Guide](docs/troubleshooting.md).

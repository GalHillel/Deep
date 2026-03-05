# Contributing to Deep VCS

First of all, thank you for considering contributing to Deep! It’s people like you that make Deep such a great tool for the developer community.

## 🌈 Our Philosophy

Deep is built on the principles of **distributed power**, **security by default**, and **intelligent automation**. We welcome any contribution that aligns with these goals, whether it's a bug fix, a new feature, or an improvement to our documentation.

## 🛠 Getting Started

### 1. Prerequisite Checklist
- **Python**: 3.8+
- **Git**: (Optional, for initial cloning)
- **Pip**: For dependency management

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/GalHillel/DeepGit.git
cd DeepGit

# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install Deep in editable developer mode
pip install -e .
```

### 3. Verify Your Installation
```bash
deep --version
```

## 🧪 Testing Your Changes

We take stability seriously. Please ensure your changes pass the full test suite before submitting a Pull Request.

```bash
# Run all tests
pytest -v

# Run with coverage (optional but recommended)
pytest --cov=deep tests/
```

## 📝 Code Standards

To keep the codebase maintainable and world-class, we request the following:

-   **Style**: Adhere to [PEP 8](https://www.python.org/dev/peps/pep-0008/). 
-   **Types**: Use [Type Hints](https://docs.python.org/3/library/typing.html) for all new function definitions.
-   **Docs**: Every public class and function must have a descriptive docstring.
-   **Lints**: We recommend using `flake8` or `pylint` for local verification.

## 📦 Pull Request Process

1.  **Sync**: Ensure your fork is up-to-date with the `main` branch.
2.  **Branch**: Create a descriptive feature branch (e.g., `feature/ai-suggestion-refactor`).
3.  **Commit**: Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (e.g., `feat: add smarter conflict prediction`).
4.  **Describe**: Clearly explain what your PR does and why it's necessary.
5.  **Review**: A maintainer will review your code as soon as possible.

## 📜 License

By contributing to Deep, you agree that your contributions will be licensed under its [MIT License](LICENSE).

---

*Let's build the future of version control together!*

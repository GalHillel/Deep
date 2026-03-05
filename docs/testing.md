# Testing Deep VCS
Deep is built with a strong focus on reliability and correctness. We maintain an extensive test suite to ensure that every command and internal component works as intended across different platforms.

## 🧪 Running the Test Suite

We use `pytest` as our primary testing framework. To run the full suite of unit and integration tests:

```bash
# Run all tests with verbose output
pytest -v

# Run tests with coverage reporting
pytest --cov=deep tests/
```

## 🏗 Test Organization

Our tests are organized mirroring the `src/deep` structure:

- `tests/test_core/`: Core VCS logic, repository initialization, and reference management.
- `tests/test_storage/`: Object storage, indexing, and WAL integrity.
- `tests/test_network/`: P2P synchronization, remote operations, and dæmon tests.
- `tests/test_commands/`: Integration tests for every CLI command.

## 🛠 Adding New Tests

When contributing a new feature or fixing a bug, please include corresponding tests:

1.  **Unit Tests**: For individual functions and classes.
2.  **Integration Tests**: Using the `deep` CLI to verify end-to-end behavior.
3.  **Mocking**: Use `unittest.mock` to isolate tests from the network or specific filesystem states where appropriate.

## 📈 Performance Benchmarking

Deep also includes a built-in benchmarking suite to track performance over time:

```bash
deep benchmark
# Compare with Git for a baseline
deep benchmark --compare-git
```

---

*Back to [Developer Guide](development.md).*

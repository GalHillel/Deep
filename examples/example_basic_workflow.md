# Example: Basic Deep Workflow

This example demonstrates the foundational workflow for using Deep in a new project.

## Scenario
You want to start tracking a simple Python project.

## Steps

1.  **Initialize the repository**:
    ```bash
    mkdir my-project
    cd my-project
    deep init
    ```

2.  **Create a file and check status**:
    ```bash
    echo "print('Hello Deep')" > main.py
    deep status
    ```
    *Output should show `main.py` as an untracked file.*

3.  **Stage the file**:
    ```bash
    deep add main.py
    deep status
    ```
    *Output should show `main.py` ready to be committed.*

4.  **Create the first commit**:
    ```bash
    deep commit -m "Initialize project with hello world"
    ```

5.  **View the log**:
    ```bash
    deep log
    ```

## Summary
You have successfully initialized a repo, staged a file, and created your first persistent snapshot in Deep.

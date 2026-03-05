# Example: Branching and Feature Development

This example shows how to use branches to develop a new feature without affecting the main codebase.

## Scenario
You need to add a "login" feature to your application.

## Steps

1.  **Create and switch to a new branch**:
    ```bash
    deep checkout -b feature-login
    ```

2.  **Develop the feature**:
    ```bash
    echo "def login(): pass" > auth.py
    deep add auth.py
    deep commit -m "Add empty login function"
    ```

3.  **Switch back to main**:
    ```bash
    deep checkout main
    ```
    *Note that `auth.py` is no longer in your working directory.*

4.  **Merge the feature branch**:
    ```bash
    deep merge feature-login
    ```
    *`auth.py` is now integrated into the main branch.*

5.  **Delete the merged branch**:
    ```bash
    deep branch -d feature-login
    ```

## Summary
By using branches, you kept your `main` branch clean while working on the new feature, then safely integrated it once complete.

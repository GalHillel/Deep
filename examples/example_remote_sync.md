# Example: Remote Synchronization (P2P)

This example demonstrates how to synchronize two local repositories using DeepGit's P2P capabilities.

## Scenario
You have a repository on your machine and want to share it with a colleague on the same network.

## Steps

### Machine A (The "Source")
1.  **Start the DeepGit daemon**:
    ```bash
    deep daemon --port 8080
    ```
    *Note the IP address and port.*

### Machine B (The "Colleague")
2.  **Clone the repository**:
    ```bash
    deep clone http://<machine-a-ip>:8080/path/to/repo my-copy
    cd my-copy
    ```

3.  **Make a change and push**:
    ```bash
    echo "# New change" >> README.md
    deep add README.md
    deep commit -m "Update from Colleague"
    deep push origin main
    ```

### Machine A
4.  **Pull the changes**:
    ```bash
    deep pull
    ```

## Summary
You have synchronized code between two machines without using a central server like GitHub or GitLab.

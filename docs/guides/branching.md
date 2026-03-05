# Branching & Merging in DeepGit

Branching is a core concept in DeepGit, allowing you to develop features, fix bugs, and experiment in isolation.

## 1. Creating and Listing Branches

To see your current branches:

```bash
deep branch
```

To create a new branch named `feature-xyz`:

```bash
deep branch feature-xyz
```

## 2. Switching Branches

To switch to your new branch:

```bash
deep checkout feature-xyz
```

### Pro-Tip: Create and Switch
You can combine these steps into one command:

```bash
deep checkout -b feature-abc
```

## 3. Merging Changes

Once your work on a branch is complete, you'll want to integrate it back into your main branch (typically `main` or `master`).

1.  **Switch to the target branch**:
    ```bash
    deep checkout main
    ```

2.  **Perform the merge**:
    ```bash
    deep merge feature-xyz
    ```

DeepGit will attempt to automatically merge the histories. If there are conflicts, the system will pause and allow you to resolve them.

## 4. Deleting Branches

After a successful merge, you can clean up by deleting the feature branch:

```bash
deep branch -d feature-xyz
```

## 5. Visualizing the Graph

To understand how your branches relate to each other, use the graph command:

```bash
deep graph --all
```

Next, learn how to share your work with others in the [Remote Operations](remote_ops.md) guide.

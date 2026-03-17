# Getting Started with Deep

Welcome to Deep! This guide will walk you through your first steps with the system, from initialization to your first remote synchronization.

## 1. Local Initialization

Every Deep journey starts with a local repository. Navigate to your project folder and run:

```bash
deep init
```

This creates a hidden `.deep` directory (managed internally) to track your project's history and configuration.

## 2. Staging Changes

Deep uses a staging index identical in concept to Git. You can add specific files or entire directories:

```bash
# Stage a single file
deep add hello_world.py

# Stage everything in the current directory
deep add .
```

To see what's currently staged, use the status command:

```bash
deep status
```

## 3. Creating Your First Commit

Once your changes are staged, wrap them up in a commit:

```bash
deep commit -m "Add original hello world script"
```

### Pro-Tip: AI-Powered Commits
Don't want to think of a message? Let Deep analyze your changes and suggest one:

```bash
deep commit --ai
```

## 4. Browsing History

To see your project's timeline, use the log:

```bash
deep log --oneline --graph
```

This provides a concise view of your commits and branch structure.

## 5. Next Steps

Now that you've mastered the basics, explore more advanced topics:

- [Branching & Merging](branching.md)
- [Remote Operations](remote_ops.md)
- [Deep AI Features](ai_features.md)

Happy coding!

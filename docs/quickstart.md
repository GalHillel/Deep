# Quick Start Guide

Welcome to Deep VCS! This guide will help you get up and running with your first repository in minutes.

## 1. Initialize a Repository

Move into your project directory and run:

```bash
deep init
```

This creates a `.deep` directory which stores all your repository metadata and objects.

## 2. Stage Your Files

Just like Git, you must stage your changes before committing them.

```bash
# Add a single file
deep add hello.py

# Add everything in the current directory
deep add .
```

## 3. Create Your First Commit

Commit your staged changes with a descriptive message.

```bash
deep commit -m "Initialize project"
```

## 4. Check Your Status

At any time, see what has changed and what is staged.

```bash
deep status
```

## 5. View Your History

Check the project's commit history.

```bash
deep log --oneline
```

## 6. Going Further: Branching

Create a new branch for a feature:

```bash
deep branch feature-x
deep checkout feature-x
```

Make changes, add, and commit as usual!

## 7. Next Steps

- **Remotes**: Learn how to sync with others using `deep push` and `deep pull`.
- **Platform Features**: Try out Pull Requests (`deep pr`) and Issues (`deep issue`).
- **AI Tools**: Use `deep commit --ai` for smart commit messages.

---

*Explore the full command list by running `deep help`.*

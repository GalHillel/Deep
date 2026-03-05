# Basic Workflow Example

This example walks through a standard development cycle using Deep.

## 1. Initialize
```bash
mkdir project-alpha
cd project-alpha
deep init
```

## 2. Work and Stage
```bash
echo "Hello Deep" > main.py
deep add main.py
```

## 3. Commit
```bash
deep commit -m "Bootstrap project"
```

## 4. Branching
```bash
deep branch feature-ui
deep checkout feature-ui
# Modify files...
deep add .
deep commit -m "Add UI components"
```

## 5. Merge
```bash
deep checkout main
deep merge feature-ui
```

## 6. Cleanup
```bash
deep branch -d feature-ui
```

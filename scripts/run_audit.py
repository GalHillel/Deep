import os
import ast
import site
from pathlib import Path
from collections import defaultdict, deque
import sys

log_file = open("audit_results_clean.txt", "w", encoding="utf-8")
def my_print(msg=""):
    log_file.write(str(msg) + "\n")

print = my_print

REPO_ROOT = Path(r"c:\Users\galh2\Desktop\DeepGit")
SRC_DIR = REPO_ROOT / "src"
DEEP_DIR = SRC_DIR / "deep"

print("--- PHASE 1: REPOSITORY STRUCTURE AUDIT ---")

missing_files = []
empty_dirs = []

all_py_files = set()
for root, dirs, files in os.walk(DEEP_DIR):
    if "__pycache__" in dirs:
        dirs.remove("__pycache__")
    if not dirs and not files:
        empty_dirs.append(root)
    for f in files:
        if f.endswith(".py"):
            all_py_files.add(os.path.join(root, f))

print(f"Total Python files found: {len(all_py_files)}")
print(f"Empty directories: {len(empty_dirs)}")
for d in empty_dirs:
    print(f"  - {d}")

print("\n--- PHASE 2: IMPORT & DEPENDENCY INTEGRITY ---")

def get_module_name(filepath):
    rel_path = os.path.relpath(filepath, SRC_DIR)
    module = rel_path.replace(os.sep, ".")[:-3]
    if module.endswith(".__init__"):
        module = module[:-9]
    return module

module_to_file = {get_module_name(f): f for f in all_py_files}
file_to_module = {v: k for k, v in module_to_file.items()}

# Ensure packages have __init__.py if they act as such implicitly or we consider them.
# We will track imports:
imports = defaultdict(set)
imported_by = defaultdict(set)

broken_imports = []
external_deps = set()

for pyfile in all_py_files:
    mod_name = file_to_module[pyfile]
    with open(pyfile, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=pyfile)
        except SyntaxError as e:
            print(f"CRITICAL: Syntax error in {pyfile}: {e}")
            continue
            
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if target.startswith("deep.") or target == "deep":
                    imports[mod_name].add(target)
                else:
                    external_deps.add(target)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # relative or absolute
                if node.level > 0:
                    # relative
                    parts = mod_name.split(".")
                    if len(parts) >= node.level:
                        base = ".".join(parts[:-node.level])
                        if base:
                            target = base + "." + node.module
                        else:
                            target = node.module
                    else:
                        broken_imports.append((mod_name, f"{node.level * '.'}{node.module}"))
                        continue
                else:
                    target = node.module
                
                if target.startswith("deep.") or target == "deep":
                    imports[mod_name].add(target)
                else:
                    external_deps.add(target.split(".")[0])

# Verify existence
missing_modules = []
for src, targets in imports.items():
    for t in targets:
        # It could be a package or a module or a class/function inside a module
        # Let's try to resolve it:
        resolved = False
        parts = t.split(".")
        
        for i in range(len(parts), 0, -1):
            sub_mod = ".".join(parts[:i])
            if sub_mod in module_to_file:
                imported_by[sub_mod].add(src)
                resolved = True
                break
        if not resolved:
            missing_modules.append((src, t))

print(f"Broken/Missing deep.* imports: {len(missing_modules)}")
for src, t in missing_modules:
    print(f"  - CRITICAL: {src} imports {t} which was not found.")

# Circular dependencies detection
print("\nChecking for Circular Dependencies:")
circular_count = 0
for node in imports:
    visited = set()
    path = []
    
    def dfs(current):
        global circular_count
        if current in path:
            idx = path.index(current)
            cycle = path[idx:] + [current]
            # print(f"  - WARNING: Cycle detected: {' -> '.join(cycle)}")
            circular_count += 1
            return
        if current in visited:
            return
        visited.add(current)
        path.append(current)
        for neighbor in imports.get(current, []):
            # Only trace deep.* neighbors that are modules
            n_parts = neighbor.split(".")
            for i in range(len(n_parts), 0, -1):
                sub_mod = ".".join(n_parts[:i])
                if sub_mod in module_to_file:
                    dfs(sub_mod)
                    break
        path.pop()
        
    dfs(node)
print(f"Circular paths found: {circular_count} (Note: some might be safe at runtime due to local imports, requires manual check if high)")

print("\n--- PHASE 3: FILE MOVE VALIDATION ---")
# Orphans (Files not imported by anyone, and not an entrypoint)
orphans = []
entrypoints = ["deep.cli.main", "deep.__main__", "deep.__init__"]

for mod in module_to_file:
    if not imported_by[mod] and mod not in entrypoints:
        # Could be test, plugin, or script inside deep tree that is never explicitly imported.
        # But wait, deep.plugins might be dynamically loaded.
        # Let's flag them anyway.
        if "plugins" not in mod and "cli" not in mod:
            orphans.append(mod)

print(f"Potential Orphan Modules (Not imported statically): {len(orphans)}")
for o in orphans:
    print(f"  - {o}")

print("\nDone.")

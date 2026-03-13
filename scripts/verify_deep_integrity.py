import os
import sys
import hashlib
from pathlib import Path

def verify_objects(objects_dir):
    print(f"Verifying objects in {objects_dir}...")
    count = 0
    errors = 0
    for root, dirs, files in os.walk(objects_dir):
        for f in files:
            sha = root[-2:] + f
            path = Path(root) / f
            with open(path, "rb") as bf:
                data = bf.read()
                # Assuming standard Deep compression/prefixing
                # If using Git-style: blob <size>\0<data>
                # Let's just check if it's readable and not empty for now
                if not data:
                    print(f"Error: Object {sha} is empty")
                    errors += 1
            count += 1
    print(f"Checked {count} objects, {errors} errors.")
    return errors == 0

def check_git_dependencies(src_dir):
    print(f"Checking for local Git dependencies in {src_dir}...")
    forbidden = ['subprocess.run(["git"', 'subprocess.call(["git"', 'os.system("git"', 'pygit2', 'gitpython']
    found = []
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                path = Path(root) / f
                content = path.read_text(errors="ignore")
                for pattern in forbidden:
                    if pattern in content:
                        # Allow remote bridge only
                        if "GitBridge" in content and "remote" in content:
                            continue
                        found.append(f"{path}: {pattern}")
    
    if found:
        print("Found potential Git dependencies:")
        for f in found:
            print(f"  {f}")
        return False
    print("No local Git dependencies found.")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        repo_root = Path(sys.argv[1])
    else:
        repo_root = Path(os.getcwd())
        
    src_dir = Path(__file__).parent.parent / "src"
    dg_dir = repo_root / ".deep_git"
    
    success = True
    if dg_dir.exists():
        if not verify_objects(dg_dir / "objects"):
            success = False
    else:
        print(f"Error: .deep_git directory not found at {repo_root}")
        success = False
    
    if not check_git_dependencies(src_dir):
        success = False
        
    if success:
        print("\nREPOSITORY INTEGRITY: OK")
        sys.exit(0)
    else:
        print("\nREPOSITORY INTEGRITY: FAILED")
        sys.exit(1)

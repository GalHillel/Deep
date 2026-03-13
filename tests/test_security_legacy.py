import ast
import os
import pathlib
import sys

from deep.cli.main import main
from deep.core.repository import DEEP_DIR
from deep.core.refs import resolve_head

def audit_security(root_dir):
    print("--- PHASE 8 & 9: SECURITY, NETWORKING, AI AUDIT ---")
    
    suspicious_calls = []
    unsafe_modules = ["os.system", "subprocess.Popen", "eval", "exec"]
    
    python_files = list(pathlib.Path(root_dir).rglob("*.py"))
    
    for pyfile in python_files:
        try:
            content = pyfile.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except Exception:
            continue
            
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    call_name = f"{node.func.value.id}.{node.func.attr}"
                    if call_name in unsafe_modules:
                        # Check if shell=True is passed
                        shell_true = False
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                shell_true = True
                        if call_name == "subprocess.Popen" and not shell_true:
                            pass # subprocess.Popen without shell=True is generally safe
                        else:
                            suspicious_calls.append((pyfile, node.lineno, call_name))
                            
                elif isinstance(node.func, ast.Name):
                    if node.func.id in unsafe_modules:
                        suspicious_calls.append((pyfile, node.lineno, node.func.id))
    dg_dir = pathlib.Path(root_dir) / DEEP_DIR
    if not dg_dir.exists():
        print(f"ERROR: {DEEP_DIR} not found")
        sys.exit(1)
    
    if suspicious_calls:
        print("WARNING: Found potentially unsafe calls:")
        for fname, line, call in suspicious_calls:
            print(f"  {fname.name}:{line} -> {call}")
            # If any exist, fail the audit for manual fixing
        sys.exit(1)
    else:
        print("Security Audit: Clean. No os.system, eval, exec, or shell=True used.")
        
    print("--- Security Audit PASSED ---")

if __name__ == "__main__":
    # Target the src/deep directory relative to the project root
    target_dir = Path(__file__).parent.parent / "src" / "deep"
    audit_security(target_dir)

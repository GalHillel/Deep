import os
from pathlib import Path

def fix_file(filepath):
    content = Path(filepath).read_text(encoding="utf-8")
    original = content
    
    # Replace literal ESC character (0x1b) with the string '\033'
    # Wait, in the source code it's literally an ESC character followed by '['.
    # So we replace chr(27) with '\\033'
    content = content.replace(chr(27), r'\033')
    
    # Also fix main.py's epilog if it still has any issues.
    
    if content != original:
        Path(filepath).write_text(content, encoding="utf-8")
        print(f"Fixed {filepath}")

def main():
    repo_dir = Path("c:/Users/galh2/Documents/GitHub/DeepGit")
    main_py = repo_dir / "src/deep/cli/main.py"
    fix_file(main_py)
    
    commands_dir = repo_dir / "src/deep/commands"
    for py_file in commands_dir.glob("*_cmd.py"):
        fix_file(py_file)

if __name__ == "__main__":
    main()

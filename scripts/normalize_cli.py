import os
from pathlib import Path

def normalize_file(filepath):
    content_raw = Path(filepath).read_bytes()
    # Decode and replace literal ESC bytes
    # But python 3's read_text handles \r\n to \n automatically
    content = content_raw.decode("utf-8")
    original = content
    
    # Replace literal ESC byte (0x1b) with string \033
    escaped_content = content.replace(chr(27), r'\033')
    
    # Normalize line endings to exactly Unix \n
    # When using replace, we don't care about \r\n
    normalized_content = escaped_content.replace('\r\n', '\n')
    
    if content_raw != normalized_content.encode("utf-8"):
        # Write bytes back so it forces unix newlines
        Path(filepath).write_bytes(normalized_content.encode("utf-8"))
        print(f"Normalized {filepath}")

def main():
    repo_dir = Path("c:/Users/galh2/Documents/GitHub/Deep")
    main_py = repo_dir / "src/deep/cli/main.py"
    normalize_file(main_py)
    
    commands_dir = repo_dir / "src/deep/commands"
    for py_file in commands_dir.glob("*.py"):
        normalize_file(py_file)

if __name__ == "__main__":
    main()

import os
import re
import glob

commands_dir = "src/deep/commands"
cmd_files = glob.glob(os.path.join(commands_dir, "*_cmd.py"))

bad_ux_funcs = {"DeepHelpFormatter", "format_header", "format_example", "format_description"}

for file_path in cmd_files:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Deduplicate standard imports
    def dedup_import(content, import_line):
        matches = list(re.finditer(re.escape(import_line), content))
        if len(matches) > 1:
            # Keep first, remove others
            for m in reversed(matches[1:]):
                content = content[:m.start()] + content[m.end():]
        return content

    content = dedup_import(content, "import argparse")
    content = dedup_import(content, "from typing import Any")
    content = dedup_import(content, "from __future__ import annotations")

    # 2. Cleanup deep.utils.ux imports
    # Handle both single line and multiline (parenthesized)
    
    # Multiline first
    def clean_multiline_ux(m):
        names_text = m.group(1)
        names = [n.strip() for n in names_text.split(",") if n.strip()]
        new_names = [n for n in names if n not in bad_ux_funcs]
        if not new_names:
            return ""
        return f"from deep.utils.ux import (\n    " + ", ".join(new_names) + "\n)"

    content = re.sub(r'from deep\.utils\.ux import \(([^\)]+)\)', clean_multiline_ux, content, flags=re.MULTILINE)

    # Single line
    def clean_singleline_ux(m):
        names_text = m.group(1)
        names = [n.strip() for n in names_text.split(",") if n.strip()]
        new_names = [n for n in names if n not in bad_ux_funcs]
        if not new_names:
            return ""
        return f"from deep.utils.ux import " + ", ".join(new_names)

    content = re.sub(r'from deep\.utils\.ux import ([^\n\(]+)', clean_singleline_ux, content)

    # 3. Final polish: remove triple newlines
    content = re.sub(r'\n{3,}', '\n\n', content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

print("Cleanup completed.")

import os
import re
import glob

commands_dir = "src/deep/commands"
cmd_files = glob.glob(os.path.join(commands_dir, "*_cmd.py"))

for file_path in cmd_files:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Add "import argparse" if not present
    if "import argparse" not in content:
        content = re.sub(
            r"(from typing import Any)",
            r"import argparse\n\1",
            content
        )

    # 2. Replace DeepHelpFormatter with argparse.RawTextHelpFormatter
    content = content.replace("formatter_class=DeepHelpFormatter", "formatter_class=argparse.RawTextHelpFormatter")

    # 3. Handle descriptions.
    # From format_description("...") to """..."""
    # Some descriptions have multiple sentences. Let's convert format_description("text.") to """text.""" 
    # and maybe split sentences into paragraphs if long, or just leave as is.
    def replace_description(m):
        desc = m.group(1)
        # Add basic newlines instead of long single lines
        desc = re.sub(r'(\. )([A-Z])', r'.\n\n\2', desc)
        return f'description="""{desc}"""'
        
    content = re.sub(r'description=format_description\(\s*"([^"]+)"\s*\)', replace_description, content)

    # 4. Handle epilogs
    # Replace the {format_header("...")}
    def replace_header(m):
        title = m.group(1).upper()
        if not title.endswith(":"):
            title += ":"
        return f"\\033[1m{title}\\033[0m"
        
    content = re.sub(r'\{format_header\(\s*"([^"]+)"\s*\)\}', replace_header, content)

    # Replace the {format_example("cmd", "desc")}
    def replace_example(m):
        cmd = m.group(1)
        desc = m.group(2)
        return f"  \\033[1;34m⚓️ {cmd}\\033[0m\n     {desc}"

    content = re.sub(r'\{format_example\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)\}', replace_example, content)
    
    # Also handle standalone {Color.wrap(...)}
    def replace_color_wrap(m):
        color = m.group(1)
        text = m.group(2)
        color_val = "\\033[1;36m" # Default generic
        if "CYAN" in color: color_val = "\\033[1;36m"
        elif "YELLOW" in color: color_val = "\\033[1;33m"
        elif "RED" in color: color_val = "\\033[1;31m"
        return f'{color_val}{text}\\033[0m'
        
    content = re.sub(r'\{Color\.wrap\(Color\.(\w+),\s*"([^"]+)"\)\}', replace_color_wrap, content)

    # Note: F-strings for epilog no longer need 'f' if there are no braces remaining, 
    # but maintaining 'f' is harmless if no braces are present, or we can strip 'f'.
    # Actually, the user's example doesn't use 'f'. Let's strip 'f' if no braces.
    content = re.sub(r'epilog=f"""', 'epilog="""\n', content)

    # 5. Clean up unused imports from ux
    content = re.sub(r'from deep\.utils\.ux import \([^\)]+\)', '', content, flags=re.MULTILINE | re.DOTALL)
    content = re.sub(r'from deep\.utils\.ux import .*\n', '', content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

print("Command refactoring completed.")

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
    # From description=format_description("xyz") to description="""xyz"""
    def replace_description(m):
        desc = m.group(1)
        desc = re.sub(r'(\. )([A-Z])', r'.\n\n\2', desc)
        return f'description="""{desc}"""'
        
    content = re.sub(r'description=format_description\(\s*"([^"]+)"\s*\)', replace_description, content)
    
    # What if it's already description="xyz" without format_description?
    # We leave it alone, but just to be safe, any description="""...""" is fine.
    
    # 4. Handle epilogs
    def replace_header(m):
        title = m.group(1).upper()
        if not title.endswith(":"):
            title += ":"
        return f"\\033[1m{title}\\033[0m"
        
    content = re.sub(r'\{format_header\(\s*"([^"]+)"\s*\)\}', replace_header, content)

    def replace_example(m):
        cmd = m.group(1)
        desc = m.group(2)
        return f"  \\033[1;34m⚓️ {cmd}\\033[0m\n     {desc}"

    content = re.sub(r'\{format_example\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)\}', replace_example, content)
    
    def replace_color_wrap(m):
        color = m.group(1)
        text = m.group(2)
        color_val = "\\033[1;36m" # Default generic
        if "CYAN" in color: color_val = "\\033[1;36m"
        elif "YELLOW" in color: color_val = "\\033[1;33m"
        elif "RED" in color: color_val = "\\033[1;31m"
        return f'{color_val}{text}\\033[0m'
        
    content = re.sub(r'\{Color\.wrap\(Color\.(\w+),\s*"([^"]+)"\)\}', replace_color_wrap, content)

    content = re.sub(r'epilog=f"""', 'epilog="""\n', content)
    
    # 5. We don't remove ux imports to avoid breaking Color usage in run() functions.

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

print("Command refactoring completed.")

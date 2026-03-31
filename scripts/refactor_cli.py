import re
import os
from pathlib import Path

def process_epilog(match):
    content = match.group(1)
    if "Examples:" not in content and "EXAMPLES:" not in content and "⚓️" not in content:
        return match.group(0) # don't touch if not examples
    
    # If it already has the ⚓️, we might be re-running. 
    # Let's try to parse the existing blocks.
    
    lines = content.strip().split('\n')
    new_parts = ["\n\\033[1mEXAMPLES:\\033[0m\n"]
    
    current_examples = []
    
    for line in lines:
        line = line.strip()
        if not line or line.lower().startswith("examples:") or line == "\\033[1mEXAMPLES:\\033[0m":
            continue
            
        if "⚓️" in line or line.startswith("deep "):
            # Start of a new example
            # Clean up the line (remove existing formatting if re-running)
            clean_line = line.replace("\\033[1;34m⚓️ ", "").replace("\\033[0m", "").replace("⚓️ ", "").strip()
            if clean_line.startswith("deep "):
                current_examples.append({"cmd": clean_line, "desc": ""})
            else:
                # Might be a description line if it didn't start with deep
                if current_examples:
                    current_examples[-1]["desc"] += " " + line
        elif "#" in line:
            parts = line.split("#", 1)
            cmd = parts[0].strip()
            desc = parts[1].strip()
            current_examples.append({"cmd": cmd, "desc": desc})
        else:
            if current_examples:
                current_examples[-1]["desc"] += " " + line

    for ex in current_examples:
        cmd = ex["cmd"]
        desc = ex["desc"].strip()
        # remove trailing period if any, then add one
        if desc.endswith('.'):
            desc = desc[:-1]
        
        new_parts.append(f"\n  \\033[1;34m⚓️ {cmd}\\033[0m\n     {desc}.\n")
             
    new_epilog = "".join(new_parts)
    return f'epilog="""{new_epilog}"""'


def update_file(filepath):
    content = Path(filepath).read_text(encoding="utf-8")
    original = content
    
    # Update formatter_class
    content = content.replace("formatter_class=argparse.RawDescriptionHelpFormatter", "formatter_class=argparse.RawTextHelpFormatter")
    
    # Fix epilogs
    content = re.sub(r'epilog="""(.*?)"""', process_epilog, content, flags=re.DOTALL)
    
    # Try alternate quote styles
    content = re.sub(r"epilog='''(.*?)'''", process_epilog, content, flags=re.DOTALL)
    
    # Add formatter_class to add_parser if missing
    # But only if it doesn't already have one
    # Regex is tricky. Instead, we can do it by finding add_parser and checking if it has formatter_class
    def ensure_formatter(match):
        block = match.group(0)
        if "formatter_class" not in block:
            # add it before the closing paren
            if block.endswith(")\n"):
                 return block[:-2] + ",\n        formatter_class=argparse.RawTextHelpFormatter,\n    )\n"
            elif block.endswith(")"):
                 return block[:-1] + ", formatter_class=argparse.RawTextHelpFormatter)"
        return block
        
    # Find add_parser calls. It's multi-line usually, up to closing paren inside the same indent level.
    # A bit risky with simple regex, but let's try.
    # Actully, some files have `add_parser("cmd", help=...)` all on one line.
    
    # Add some breathability to descriptions defined as multi-line strings or long lines
    def clean_description(match):
        desc = match.group(1)
        # Add newlines after ". " if not already there
        desc = re.sub(r'\. +([A-Z])', r'.\n\n\1', desc)
        return f'description={match.group(0)[12] + match.group(0)[12] + match.group(0)[12]}{desc}{match.group(0)[12] + match.group(0)[12] + match.group(0)[12]}'
        
    # We will do description breathability only for main.py where it's single-line mostly strings
    # For single line strings:
    def split_single_line_desc(match):
        quote = match.group(1)
        desc = match.group(2)
        if "\\n" not in desc and ". " in desc:
            desc = desc.replace(". ", ".\\n\\n")
        return f"description={quote}{desc}{quote}"
        
    content = re.sub(r'description=(["\'])(.*?)\1', split_single_line_desc, content)

    if content != original:
        Path(filepath).write_text(content, encoding="utf-8")
        print(f"Updated {filepath}")

def main():
    repo_dir = Path("c:/Users/galh2/Documents/GitHub/DeepGit")
    main_py = repo_dir / "src/deep/cli/main.py"
    
    # Update main.py
    update_file(main_py)
    
    # Specifically update main.py for DEEP_LOGO and ROOT epilog
    if main_py.exists():
        content = main_py.read_text(encoding="utf-8")
        
        if "from deep.utils.ux import DEEP_LOGO" not in content:
            content = content.replace("from deep.core.errors import DeepError", "from deep.core.errors import DeepError\nfrom deep.utils.ux import DEEP_LOGO")
            
        content = content.replace('description="Deep — Next-generation Distributed Version Control System",', 'description=DEEP_LOGO,')
        
        main_epilog = '''epilog="""
\\033[1;32m🌱 STARTING A WORKING AREA\\033[0m
    \\033[1;36minit, clone\\033[0m

\\033[1;33m📦 WORK ON THE CURRENT CHANGE\\033[0m
    \\033[1;36madd, rm, mv, reset, stash\\033[0m

\\033[1;32m🌿 EXAMINE THE HISTORY AND STATE\\033[0m
    \\033[1;36mstatus, log, diff, show, ls-tree, graph\\033[0m

\\033[1;35m🔄 GROW, MARK AND TWEAK YOUR COMMON HISTORY\\033[0m
    \\033[1;36mcommit, branch, checkout, merge, rebase, tag\\033[0m

\\033[1;34m🌐 COLLABORATE (P2P & REMOTE)\\033[0m
    \\033[1;36mpush, pull, fetch, remote, p2p, sync, ls-remote, mirror, daemon\\033[0m

\\033[1;35m🧠 AI & PLATFORM\\033[0m
    \\033[1;36mai, pr, issue, pipeline, studio, repo, user, auth, server\\033[0m

\\033[1;31m🛠️ MAINTENANCE & DIAGNOSTICS\\033[0m
    \\033[1;36mdoctor, fsck, gc, verify, repack, benchmark, audit, ultra, batch, sandbox, rollback\\033[0m

\\033[1;33m💡 UNIVERSAL SHORTCUTS\\033[0m
    \\033[1;36mdeep <command> --help\\033[0m    # Detailed help for any command
    \\033[1;36mdeep version\\033[0m             # Show version and logo
"""'''
        
        # Replace the root parser epilog
        content = re.sub(r'epilog="""\nCore Commands:.*?Help:\n  deep <command> --help\n  deep help\n"""', main_epilog, content, flags=re.DOTALL)
        
        # Hide default command list by adding metavar=""
        content = content.replace('sub = parser.add_subparsers(dest="command", metavar="COMMAND")', 'sub = parser.add_subparsers(dest="command", metavar="")')
        
        # Ensure all add_parser calls have formatter_class
        # simple targeted replacements for some common issues if needed
        
        main_py.write_text(content, encoding="utf-8")
        print("Special updates applied to main.py")
        
    # Update command modules
    commands_dir = repo_dir / "src/deep/commands"
    for py_file in commands_dir.glob("*_cmd.py"):
        update_file(py_file)

if __name__ == "__main__":
    main()

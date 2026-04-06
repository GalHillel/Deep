import os
import re
from pathlib import Path

def main():
    target_dirs = [
        Path(r"c:\Users\galh2\Documents\GitHub\Deep\src\deep\commands"),
        Path(r"c:\Users\galh2\Documents\GitHub\Deep\src\deep\cli"),
    ]
    for d in target_dirs:
        for p in d.glob("*.py"):
            txt = p.read_text("utf-8")
            original = txt
            txt = re.sub(r'sys\.exit\(0\)', 'return 0', txt)
            txt = re.sub(r'sys\.exit\(([^)]+)\)', r'raise DeepCLIException(\1)', txt)
            if txt != original:
                if 'from deep.core.errors import DeepCLIException' not in txt:
                    txt = txt.replace('from __future__ import annotations', 'from __future__ import annotations\nfrom deep.core.errors import DeepCLIException')
                p.write_text(txt, "utf-8")

if __name__ == "__main__":
    main()

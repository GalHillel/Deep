import os
import re
import glob

commands_dir = "src/deep/commands"
cmd_files = glob.glob(os.path.join(commands_dir, "*_cmd.py"))

# symbol -> import_line
SYMBOLS = {
    "DEEP_DIR": "from deep.core.constants import DEEP_DIR",
    "find_repo": "from deep.core.repository import find_repo",
    "Color": "from deep.utils.ux import Color",
    "print_error": "from deep.utils.ux import print_error",
    "print_success": "from deep.utils.ux import print_success",
    "print_info": "from deep.utils.ux import print_info",
    "print_warning": "from deep.utils.ux import print_warning",
    "read_object": "from deep.storage.objects import read_object",
    "Commit": "from deep.storage.objects import Commit",
    "Tree": "from deep.storage.objects import Tree",
    "Blob": "from deep.storage.objects import Blob",
    "Tag": "from deep.storage.objects import Tag",
    "IssueManager": "from deep.core.issue import IssueManager",
    "Issue": "from deep.core.issue import Issue",
    "PRManager": "from deep.core.pr import PRManager",
    "PR": "from deep.core.pr import PR",
    "Config": "from deep.core.config import Config",
    "TransactionLog": "from deep.storage.txlog import TransactionLog",
    "TransactionManager": "from deep.storage.transaction import TransactionManager",
    "SandboxRunner": "from deep.core.security import SandboxRunner",
    "DeepHistoryGraph": "from deep.storage.commit_graph import DeepHistoryGraph",
    "build_history_graph": "from deep.storage.commit_graph import build_history_graph",
    "argparse": "import argparse",
    "os": "import os",
    "sys": "import sys",
    "subprocess": "import subprocess",
    "json": "import json",
    "time": "import time",
    "datetime": "import datetime",
    "hashlib": "import hashlib",
    "struct": "import struct",
    "shutil": "import shutil",
    "pickle": "import pickle",
    "socket": "import socket",
    "threading": "import threading",
    "Any": "from typing import Any",
    "List": "from typing import List",
    "Dict": "from typing import Dict",
    "Optional": "from typing import Optional",
    "Path": "from pathlib import Path",
}

for file_path in cmd_files:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    missing_imports = set()
    for symbol, import_line in SYMBOLS.items():
        # Check if symbol is used (simple word match)
        if re.search(r'\b' + re.escape(symbol) + r'\b', content):
            # Check if it's already imported
            if import_line not in content and f"import {symbol}" not in content and f"as {symbol}" not in content:
                # Handle cases like 'from typing import Any, List'
                if symbol in ["Any", "List", "Dict", "Optional"]:
                    if not re.search(r'from typing import .*\b' + symbol + r'\b', content):
                        missing_imports.add(import_line)
                elif symbol in ["Color", "print_error", "print_success", "print_info", "print_warning"]:
                    if not re.search(r'from deep\.utils\.ux import .*\b' + symbol + r'\b', content):
                        missing_imports.add(import_line)
                elif symbol in ["read_object", "Commit", "Tree", "Blob", "Tag"]:
                    if not re.search(r'from deep\.storage\.objects import .*\b' + symbol + r'\b', content):
                        missing_imports.add(import_line)
                else:
                    missing_imports.add(import_line)

    if missing_imports:
        print(f"Fixing {file_path} - adding {len(missing_imports)} imports")
        # Find the line after docstring or from __future__
        lines = content.splitlines()
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('"""') and i > 0:
                insert_idx = i + 1
                break
            if line.startswith('from __future__'):
                insert_idx = i + 1
                break
        
        # Sort and join missing imports
        new_imports = "\n".join(sorted(list(missing_imports)))
        lines.insert(insert_idx, new_imports)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

print("Import fix completed.")

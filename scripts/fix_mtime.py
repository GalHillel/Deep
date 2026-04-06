"""Bulk fix: Replace all occurrences of int(stat.st_mtime * 1e9) with stat.st_mtime_ns across the codebase."""
import os

root = r'c:\Users\galh2\Documents\GitHub\Deep'

files_to_fix = [
    'src/deep/commands/merge_cmd.py',
    'src/deep/core/repository.py',
    'src/deep/commands/reset_cmd.py',
    'src/deep/commands/mv_cmd.py',
    'src/deep/storage/txlog.py',
]

for fpath in files_to_fix:
    full = os.path.join(root, fpath)
    with open(full, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    content = content.replace('int(stat.st_mtime * 1e9)', 'stat.st_mtime_ns')
    if content != original:
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)
        count = original.count('int(stat.st_mtime * 1e9)')
        print(f"Fixed {count} occurrences in {fpath}")
    else:
        print(f"No changes needed in {fpath}")

print("\nmtime precision fix complete!")

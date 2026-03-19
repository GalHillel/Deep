"""Purge all DeepBridge references from source files."""
import os

FILES_AND_REPLACEMENTS = {
    'src/deep/core/stash.py': [('DeepBridge Stash', 'Deep Stash')],
    'src/deep/core/maintenance.py': [('DeepBridge:', 'Deep:')],
    'src/deep/core/pipeline.py': [('for DeepBridge', 'for Deep')],
    'src/deep/core/config.py': [('for DeepBridge', 'for Deep')],
    'src/deep/core/benchmark.py': [('for DeepBridge', 'for Deep'), ('DeepBridge Benchmarks', 'Deep Benchmarks')],
    'src/deep/network/protocol.py': [('DeepBridge', 'Deep')],
    'src/deep/storage/pack.py': [('for DeepBridge', 'for Deep')],
}

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for fpath, replacements in FILES_AND_REPLACEMENTS.items():
    full = os.path.join(root, fpath)
    with open(full, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed: {fpath}")

print("DeepBridge purge complete")

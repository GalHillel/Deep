"""Purge all forbidden word references from objects/ and network/ packages."""
import os
import re

def replace_in_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    for old, new in replacements:
        content = content.replace(old, new)
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

root = r'c:\Users\galh2\Documents\GitHub\Deep'

# objects/ package files
objects_replacements = [
    # __init__.py
    ('Git-compatible object layer for Deep.', 'Pure-Python object layer for Deep.'),
    ('This package provides pure-Python implementations of the Git object format,', 'This package provides pure-Python implementations of the standard VCS object format,'),
    ('interoperate with standard Git servers (GitHub, GitLab) over SSH and HTTPS', 'interoperate with standard remote servers (GitHub, GitLab) over SSH and HTTPS'),
    ('without any external git CLI or library dependency.', 'without any external CLI or library dependency.'),
    # packfile.py
    ('Git v2 packfile parser and writer.', 'Standard v2 packfile parser and writer.'),
    ('Implements the full Git packfile format:', 'Implements the full standard packfile format:'),
    ('All without external git CLI or library dependency.', 'All without external CLI or library dependency.'),
    ('from deep.objects.delta import apply_delta as git_apply_delta', 'from deep.objects.delta import apply_delta as deep_apply_delta'),
    ('# Git packfile constants', '# Packfile constants'),
    ('# \u2500\u2500 Variable-length integer encoding (Git MSB format)', '# \u2500\u2500 Variable-length integer encoding (MSB format)'),
    ('Read the Git packfile object type and size.', 'Read the packfile object type and size.'),
    ('Git encodes this as a variable-length integer where each', 'Encoded as a variable-length integer where each'),
    ('Parse a Git v2 packfile and extract all objects.', 'Parse a v2 packfile and extract all objects.'),
    ('resolved = git_apply_delta(base_data, delta_data)', 'resolved = deep_apply_delta(base_data, delta_data)'),
    ('target = git_apply_delta(base_data, delta_data)', 'target = deep_apply_delta(base_data, delta_data)'),
    ('Build a Git v2 packfile from a list of (type_str, data) tuples.', 'Build a v2 packfile from a list of (type_str, data) tuples.'),
    ('Encode object type and size in Git packfile format.', 'Encode object type and size in packfile format.'),
    # hash_object.py
    ('Git-compatible object hashing, reading and writing.', 'Standard object hashing, reading and writing.'),
    ('Objects are stored in the canonical Git format:', 'Objects are stored in the canonical format:'),
    ('.deep/objects/xx/yyyy...  (Level 1 fan-out, Git-compatible)', '.deep/objects/xx/yyyy...  (Level 1 fan-out)'),
    ('Compute the SHA-1 hash of a Git object.', 'Compute the SHA-1 hash of an object.'),
    ('Format data as a Git object (header + null + content).', 'Format data as an object (header + null + content).'),
    ('Write a Git-format object to the object store.', 'Write a formatted object to the object store.'),
    ("Uses Level 1 fan-out (xx/yyyy...) matching Git's standard layout.", 'Uses Level 1 fan-out (xx/yyyy...) standard layout.'),
    ('# Git-compatible Level 1 fan-out: objects/xx/yyyy...', '# Level 1 fan-out: objects/xx/yyyy...'),
    ('Read a raw Git object from the object store.', 'Read a raw object from the object store.'),
    ('# Try Level 1 fan-out (Git standard)', '# Try Level 1 fan-out (standard)'),
    # delta.py
    ('Git-compatible delta compression engine.', 'Delta compression engine for Deep.'),
    ('Implements the Git delta format used inside packfiles:', 'Implements the delta format used inside packfiles:'),
    ('This is the standard Git OFS_DELTA / REF_DELTA undelta format.', 'This is the standard OFS_DELTA / REF_DELTA undelta format.'),
    ('Read a Git-style variable-length integer (little-endian, MSB continuation).', 'Read a variable-length integer (little-endian, MSB continuation).'),
    ('Apply a Git delta to a base object to produce the target.', 'Apply a delta to a base object to produce the target.'),
    ("# Size of 0 means 0x10000 (65536) in Git's encoding", '# Size of 0 means 0x10000 (65536) in delta encoding'),
    ('Create a Git-format delta that transforms source into target.', 'Create a delta that transforms source into target.'),
    ('Delta instruction bytes in Git format.', 'Delta instruction bytes in standard format.'),
    ("Encode an integer as Git-style variable-length LE bytes.", 'Encode an integer as variable-length LE bytes.'),
    ("Emit a COPY instruction with Git's bitmask encoding.", 'Emit a COPY instruction with bitmask encoding.'),
    # pack_index.py
    ('Git pack index (.idx) file format, version 2.', 'Pack index (.idx) file format, version 2.'),
    ('Read and query a Git pack index file.', 'Read and query a pack index file.'),
    ('Create a Git pack index (v2) from a list of (sha, offset, crc32) entries.', 'Create a pack index (v2) from a list of (sha, offset, crc32) entries.'),
]

objects_files = [
    'src/deep/objects/__init__.py',
    'src/deep/objects/packfile.py',
    'src/deep/objects/hash_object.py',
    'src/deep/objects/delta.py',
    'src/deep/objects/pack_index.py',
]

for fpath in objects_files:
    full = os.path.join(root, fpath)
    if os.path.exists(full):
        if replace_in_file(full, objects_replacements):
            print(f"Fixed: {fpath}")
        else:
            print(f"No changes: {fpath}")

# network/ package files
network_replacements = [
    # transport.py
    ('Transport layer for Git smart protocol.', 'Transport layer for Deep smart protocol.'),
    ('1. SSH \u2014 via system `ssh` subprocess (NOT git CLI)', '1. SSH \u2014 via system `ssh` subprocess (NOT external VCS CLI)'),
    ('    SSH:   git@github.com:user/repo.git', '    SSH:   user@github.com:user/repo'),
    # git_protocol.py header references handled by file rename later
]

network_files = [
    'src/deep/network/transport.py',
]

for fpath in network_files:
    full = os.path.join(root, fpath)
    if os.path.exists(full):
        if replace_in_file(full, network_replacements):
            print(f"Fixed: {fpath}")
        else:
            print(f"No changes: {fpath}")

# objects.py (storage)
storage_replacements = [
    ('Serialize commit in Git-compatible format.', 'Serialize commit in standard VCS format.'),
    ('Standard Git headers: tree, parent, author, committer.', 'Standard headers: tree, parent, author, committer.'),
    ('for full Git interoperability.', 'for full interoperability.'),
    ('# These are ignored by Git but preserved by Deep', '# Deep-specific metadata preserved in custom headers'),
]

full = os.path.join(root, 'src/deep/storage/objects.py')
if replace_in_file(full, storage_replacements):
    print("Fixed: src/deep/storage/objects.py")

# sparse.py
full = os.path.join(root, 'src/deep/utils/sparse.py')
if os.path.exists(full):
    if replace_in_file(full, [("# Note: Deep's sparse-checkout is more complex (gitignore-like), ", "# Note: Deep's sparse-checkout uses pattern-based filtering, ")]):
        print("Fixed: src/deep/utils/sparse.py")

print("\nForbidden word purge complete!")

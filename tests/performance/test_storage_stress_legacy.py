import os
import shutil
import time
import random
from pathlib import Path
import pytest

from deep.core.repository import DEEP_DIR
from deep.storage.objects import write_object, Blob
from deep.core.refs import update_branch as update_ref, resolve_head

def test_storage_stress():
    with tempfile_dir() as tmpdir:
        run_storage_stress(Path(tmpdir))

def run_storage_stress(repo_root: Path):
    if repo_root.exists():
        shutil.rmtree(repo_root)
    repo_root.mkdir()
    
    dg_dir = repo_root / DEEP_DIR
    dg_dir.mkdir()
    objects_dir = dg_dir / "objects"
    objects_dir.mkdir()
    
    print("--- Storage Stress Analysis ---")
    # Simulation of massive object writes
    for i in range(1000):
         data = os.urandom(1024)
         blob = Blob(data)
         sha = write_object(objects_dir, blob)
         if i % 100 == 0:
             print(f"Written {i} objects...")
             
    print("Storage Stress: PASSED")

import tempfile
from contextlib import contextmanager

@contextmanager
def tempfile_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

if __name__ == "__main__":
    with tempfile_dir() as tmpdir:
        run_storage_stress(Path(tmpdir))

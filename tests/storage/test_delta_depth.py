import pytest
from pathlib import Path
from deep.core.repository import init_repo
from deep.storage.objects import (
    Blob, 
    DeltaObject, 
    write_object, 
    read_object, 
    MAX_DELTA_CHAIN_DEPTH
)
from deep.storage.delta import create_delta

def test_max_delta_depth_enforcement(tmp_path):
    """Verify that deep delta chains trigger the recursion guard."""
    repo_root = tmp_path / "repo"
    dg = init_repo(repo_root)
    objects_dir = dg / "objects"
    
    # 1. Create a base blob
    base_content = b"initial content"
    base_blob = Blob(data=base_content)
    last_sha = write_object(objects_dir, base_blob)
    
    # 2. Programmatically create a chain of 51 delta objects.
    # Each delta will point to the previous SHA.
    # We do this manually to bypass the 'write_delta_object' size check.
    
    for i in range(MAX_DELTA_CHAIN_DEPTH + 1):
        target_content = f"content version {i}".encode("utf-8")
        delta_data = create_delta(base_content, target_content) # Delta relative to original base for simplicity
        # BUT we store it as a delta relative to last_sha to build the chain
        delta_obj = DeltaObject(base_sha=last_sha, delta_data=delta_data)
        last_sha = write_object(objects_dir, delta_obj)
        # Update base_content for next delta creation if we wanted a real chain,
        # but here we just want to force recursion depth during read.
    
    # 3. Attempt to read the tip of the 51-deep chain.
    # It should raise ValueError due to MAX_DELTA_CHAIN_DEPTH = 50.
    
    with pytest.raises(ValueError) as excinfo:
        read_object(objects_dir, last_sha)
    
    assert "delta-chain depth exceeded" in str(excinfo.value)
    assert f"({MAX_DELTA_CHAIN_DEPTH})" in str(excinfo.value)

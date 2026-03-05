"""
tests.test_crdt_sync
~~~~~~~~~~~~~~~~~~~~
Tests for Phase 55: Quantum-Level Conflict Resolution (CRDTs).
"""

import pytest
import time
from deep.core.crdt import LWWSet, RepoStateCRDT


def test_lww_set_basic():
    lww = LWWSet()
    
    # Add 'v1' at t1
    lww.add("v1", 100)
    assert lww.exists("v1")
    
    # Remove 'v1' at t2
    lww.remove("v1", 200)
    assert not lww.exists("v1")
    
    # Add 'v1' back at t3
    lww.add("v1", 300)
    assert lww.exists("v1")


def test_lww_set_merge():
    l1 = LWWSet(); l2 = LWWSet()
    
    l1.add("A", 100)
    l1.add("B", 100)
    
    l2.add("B", 200) # L2 has newer B
    l2.remove("A", 200) # L2 removed A later
    
    l1.merge(l2)
    
    assert not l1.exists("A")
    assert l1.exists("B")
    assert l1.add_set["B"] == 200


def test_repo_state_reconciliation():
    node_a = RepoStateCRDT()
    node_b = RepoStateCRDT()
    
    # Node A updates 'main'
    node_a.update_branch("main", "sha_A")
    time.sleep(0.01)
    
    # Node B updates 'main' later
    node_b.update_branch("main", "sha_B")
    
    # Merge B into A
    node_a.merge(node_b)
    
    # A should resolve to B's SHA because it was later
    assert node_a.resolve_branch("main") == "sha_B"
    
    # Even if we merge A back to B, it stays B
    node_b.merge(node_a)
    assert node_b.resolve_branch("main") == "sha_B"

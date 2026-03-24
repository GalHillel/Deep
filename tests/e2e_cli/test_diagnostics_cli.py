import pytest
from .conftest import run_deep

def test_maintenance_flow(repo_factory):
    """Test doctor, fsck, gc, repack, and maintenance."""
    path = repo_factory.create()
    repo_factory.run(["maintenance", "run"], cwd=path)
    repo_factory.run(["doctor"], cwd=path)
    repo_factory.run(["fsck"], cwd=path)
    repo_factory.run(["gc"], cwd=path)
    repo_factory.run(["repack"], cwd=path)

def test_benchmark_and_verify(repo_factory):
    """Test benchmark and verify commands."""
    path = repo_factory.create()
    repo_factory.run(["benchmark"], cwd=path)
    repo_factory.run(["verify"], cwd=path)

def test_audit_and_commit_graph(repo_factory):
    """Test audit and commit-graph commands."""
    path = repo_factory.create()
    repo_factory.run(["audit"], cwd=path)
    repo_factory.run(["commit-graph", "write"], cwd=path)

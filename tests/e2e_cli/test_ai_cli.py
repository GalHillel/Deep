import pytest

def test_ai_generate(repo_factory):
    """Test ai and ultra commands 10 times."""
    path = repo_factory.create()
    # Add an initial 'ai generate' call as per the instruction's example
    repo_factory.run(["ai", "generate", "--prompt", "python hello world"], cwd=path)
    for i in range(10):
        # AI message suggestion
        (path / "change.txt").write_text(f"change {i}")
        repo_factory.run(["add", "change.txt"], cwd=path)
        
        res = repo_factory.run(["ai", "suggest"], cwd=path)
        assert res.returncode == 0
        assert res.stdout # AI should suggest something
        
        # Ultra (advanced AI)
        res = repo_factory.run(["ultra"], cwd=path)
        assert res.returncode == 0

def test_batch_and_search(repo_factory):
    """Test batch and search commands with proper history."""
    path = repo_factory.create("search_test")
    for i in range(10):
        (path / f"file_{i}.txt").write_text(f"searchable content {i}")
        repo_factory.run(["add", f"file_{i}.txt"], cwd=path)
        repo_factory.run(["commit", "-m", f"commit {i}"], cwd=path) # Commits needed for search_history
        
        res = repo_factory.run(["search", f"content {i}"], cwd=path)
        assert res.returncode == 0
        assert f"file_{i}.txt" in res.stdout
        
        # Batch test
        batch_script = path / "test.deep"
        batch_script.write_text("status\nlog\n")
        repo_factory.run(["batch", str(batch_script)], cwd=path)

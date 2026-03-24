import pytest
import os
from pathlib import Path
from deep.core.repository import init_repo
from deep.core.issue import IssueManager
from deep.core.pr import PRManager
from deep.core.refs import update_branch
from deep.storage.objects import Commit

def ns(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)

@pytest.fixture
def repo(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    init_repo(repo_path)
    return repo_path

def test_pr_issue_two_way_binding_and_autoclose(repo):
    dg_dir = repo / ".deep"
    im = IssueManager(dg_dir)
    pm = PRManager(dg_dir)
    
    # 1. Create an issue
    issue = im.create_issue(
        title="Fix the bug",
        description="There is a bug in the system.",
        type="bug",
        author="gal"
    )
    assert issue.id == 1
    assert issue.status == "open"
    
    # 2. Setup repo for PR (need commits and branches)
    objs_dir = dg_dir / "objects"
    # Initial commit on main
    c1 = Commit(tree_sha="tree1", parent_shas=[], author="gal", message="initial", timestamp=100)
    sha1 = c1.write(objs_dir)
    update_branch(dg_dir, "main", sha1)
    
    # Commit on feature branch
    c2 = Commit(tree_sha="tree2", parent_shas=[sha1], author="gal", message="fix", timestamp=200)
    sha2 = c2.write(objs_dir)
    update_branch(dg_dir, "feature", sha2)
    
    # 3. Create a PR linked to the issue
    pr = pm.create_pr(
        title="Fix PR",
        author="gal",
        head="feature",
        base="main",
        body="This fixes issue #1",
        linked_issue=issue.id
    )
    
    # 4. Assert Issue state after PR creation (Two-way binding)
    updated_issue = im.get_issue(issue.id)
    assert pr.id in updated_issue.linked_prs
    # Check events
    assert any(e["action"] == "PR_CREATED" for e in updated_issue.events)
    assert any(e["action"] == "PR_LINKED" for e in updated_issue.events)
    
    # 5. Merge the PR
    # Mock recursive_merge to avoid actual tree diffing complexity in this test
    # We just want to test the hooks
    import deep.core.pr as pr_module
    from unittest.mock import patch
    
    with patch("deep.core.merge.recursive_merge") as mock_merge:
        mock_merge.return_value = ("merged_tree", []) # tree_sha, conflicts
        pm.merge_pr(pr.id)
    
    # 6. Assert Issue state after PR merge (Auto-close)
    final_issue = im.get_issue(issue.id)
    assert final_issue.status == "closed"
    assert any(e["action"] == "PR_MERGED" for e in final_issue.events)
    assert "Automatically closed" in [e["description"] for e in final_issue.events if e["action"] == "PR_MERGED"][0]

def test_collaboration_timeline_events(repo):
    dg_dir = repo / ".deep"
    im = IssueManager(dg_dir)
    pm = PRManager(dg_dir)
    
    issue = im.create_issue("Title", "Desc", "task", "gal")
    pr = pm.create_pr("PR", "gal", "head", "base", linked_issue=issue.id)
    
    # Add comment to PR
    pm.add_thread(pr.id, "reviewer", "Looks good")
    
    # Verify event in Issue
    updated_issue = im.get_issue(issue.id)
    assert any(e["action"] == "COMMENT_ADDED" for e in updated_issue.events)
    assert any(e["actor"] == "reviewer" for e in updated_issue.events if e["action"] == "COMMENT_ADDED")

"""
tests.test_tags
~~~~~~~~~~~~~~~~
Tests for tagging system (lightweight and annotated).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deep.storage.objects import Tag, read_object
from deep.core.refs import get_tag
from deep.cli.main import main


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    main(["init"])
    
    (tmp_path / "f.txt").write_text("v1")
    main(["add", "f.txt"])
    main(["commit", "-m", "c1"])
    
    return tmp_path


def test_lightweight_tag(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["tag", "v1.0"])
    
    capsys.readouterr()
    main(["log"])
    out = capsys.readouterr().out
    
    assert "tag: v1.0" in out
    
    # List tags
    main(["tag"])
    out = capsys.readouterr().out
    assert "v1.0\n" in out


def test_annotated_tag(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["config", "user.name", "Test Tagger"])
    main(["config", "user.email", "tagger@test.com"])
    
    main(["tag", "-a", "v2.0", "-m", "Release 2"])
    
    capsys.readouterr()
    main(["log"])
    out = capsys.readouterr().out
    
    assert "tag: v2.0" in out
    
    # Verify the object is a Tag object
    dg_dir = repo / ".deep"
    tag_sha = get_tag(dg_dir, "v2.0")
    assert tag_sha is not None
    
    obj = read_object(dg_dir / "objects", tag_sha)
    assert isinstance(obj, Tag)
    assert obj.tag_name == "v2.0"
    assert obj.message == "Release 2"
    assert "Test Tagger" in obj.tagger


def test_multiple_tags(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["tag", "v1.0"])
    main(["tag", "-a", "v2.0", "-m", "second tag on same commit"])
    
    capsys.readouterr()
    main(["log"])
    out = capsys.readouterr().out
    
    # Should contain both decorations
    assert "tag: v1.0" in out
    assert "tag: v2.0" in out

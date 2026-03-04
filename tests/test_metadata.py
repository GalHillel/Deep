"""
tests.test_metadata
~~~~~~~~~~~~~~~~~~~~
Tests for commit metadata parsing, timezone offsets, and date formatting.
"""

from __future__ import annotations

import time
from deep_git.core.utils import format_git_date, get_local_timezone_offset
from deep_git.core.objects import Commit


def test_format_git_date_utc() -> None:
    # 0 -> Jan 1 1970 00:00:00
    formatted = format_git_date(0, "+0000")
    assert formatted == "Thu Jan  1 00:00:00 1970 +0000"


def test_format_git_date_positive_offset() -> None:
    # 0 -> UTC, but with +0200 we add 2 hours -> Jan 1 1970 02:00:00
    formatted = format_git_date(0, "+0200")
    assert formatted == "Thu Jan  1 02:00:00 1970 +0200"


def test_format_git_date_negative_offset() -> None:
    # 0 -> +0000. For -0300, it's 3 hours behind UTC -> Dec 31 1969 21:00:00
    # Watch out for negative timestamps on some platforms, let's use a standard positive time.
    # 86400 = Jan 2 1970 00:00:00 UTC
    formatted = format_git_date(86400, "-0300")
    assert formatted == "Thu Jan  1 21:00:00 1970 -0300"


def test_format_git_date_malformed_offset() -> None:
    formatted = format_git_date(0, "INVALID")
    # Falls back to offset 0
    assert formatted == "Thu Jan  1 00:00:00 1970 INVALID"


def test_get_local_timezone_offset() -> None:
    offset = get_local_timezone_offset()
    assert len(offset) == 5
    assert offset[0] in ("+", "-")
    # Hours between 00 and 14 ordinarily
    assert 0 <= int(offset[1:3]) <= 14
    # Minutes 00, 30, 45 typically
    assert 0 <= int(offset[3:5]) <= 59


def test_commit_timezone_default() -> None:
    c = Commit()
    assert len(c.timezone) == 5
    assert c.timezone[0] in ("+", "-")


def test_commit_serialization_with_metadata() -> None:
    c = Commit(
        tree_sha="a" * 40,
        author="Alice <alice@example.com>",
        committer="Bob <bob@example.com>",
        timestamp=1234567890,
        timezone="+0530",
        message="Test parsing"
    )
    
    raw = c.serialize_content()
    assert b"author Alice <alice@example.com> 1234567890 +0530" in raw
    assert b"committer Bob <bob@example.com> 1234567890 +0530" in raw
    
    parsed = Commit.from_content(raw)
    assert parsed.author == "Alice <alice@example.com>"
    assert parsed.committer == "Bob <bob@example.com>"
    assert parsed.timestamp == 1234567890
    assert parsed.timezone == "+0530"
    assert parsed.message == "Test parsing"

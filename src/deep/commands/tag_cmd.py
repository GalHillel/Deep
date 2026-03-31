"""
deep.commands.tag_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~
``deep tag`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
import time
from pathlib import Path

from deep.core.config import Config
from deep.storage.objects import Tag
from deep.core.refs import create_tag, list_tags, resolve_head
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import DeepHelpFormatter, format_example
import argparse
from typing import Any


from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
import argparse
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'tag' command parser."""
    p_tag = subparsers.add_parser(
        "tag",
        help="Create, list, or delete tags",
        description="""Manage tag objects in your repository.

Tags are used to mark specific points in history as important, such as release versions (e.g., v1.0.0).

Supports both lightweight and annotated tags.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep tag\033[0m
     List all tags in the repository
  \033[1;34m⚓️ deep tag v1.0\033[0m
     Create a lightweight tag at current HEAD
  \033[1;34m⚓️ deep tag -a v1.1 -m 'Release'\033[0m
     Create an annotated tag with a message
  \033[1;34m⚓️ deep tag -d v0.9\033[0m
     Delete an existing tag
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p_tag.add_argument("name", nargs="?", help="The name of the tag to create, list, or delete")
    p_tag.add_argument("object", nargs="?", default="HEAD", help="The commit SHA or reference to tag (default: HEAD)")
    p_tag.add_argument("-a", "--annotate", action="store_true", help="Create an annotated tag object containing metadata")
    p_tag.add_argument("-m", "--message", help="The message for an annotated tag")
    p_tag.add_argument("-d", "--delete", action="store_true", help="Delete the specified tag")
    p_tag.add_argument("-l", "--list", action="store_true", help="List tags (default action if no name is provided)")


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``tag`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    # If no tag name is given, list tags
    if not args.name:
        for t in list_tags(dg_dir):
            print(t)
        return

    # Find target commit
    target_sha = resolve_head(dg_dir)
    if not target_sha:
        print("Deep: error: no commits to tag", file=sys.stderr)
        raise DeepCLIException(1)

    tag_name = args.name

    if args.message:
        # Annotated tag
        config = Config(repo_root)
        author_name = config.get("user.name", "Deep User")
        author_email = config.get("user.email", "user@deep")
        tagger_str = f"{author_name} <{author_email}>"

        tag_obj = Tag(
            target_sha=target_sha,
            target_type="commit",
            tag_name=tag_name,
            tagger=tagger_str,
            message=args.message,
            timestamp=int(time.time()),
        )
        # We need to write the tag object and point the ref to it
        tag_sha = tag_obj.write(objects_dir)
        try:
            create_tag(dg_dir, tag_name, tag_sha)
        except FileExistsError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
    else:
        # Lightweight tag
        try:
            create_tag(dg_dir, tag_name, target_sha)
        except FileExistsError as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)

"""
deep.commands.tag_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~
``deep tag`` command implementation.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from deep.core.config import Config
from deep.storage.objects import Tag
from deep.core.refs import create_tag, list_tags, resolve_head
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``tag`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

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
        print("DeepGit: error: no commits to tag", file=sys.stderr)
        sys.exit(1)

    tag_name = args.name

    if args.message:
        # Annotated tag
        config = Config(repo_root)
        author_name = config.get("user.name", "DeepGit User")
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
            print(f"DeepGit: error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Lightweight tag
        try:
            create_tag(dg_dir, tag_name, target_sha)
        except FileExistsError as e:
            print(f"DeepGit: error: {e}", file=sys.stderr)
            sys.exit(1)

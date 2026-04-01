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
from deep.core.refs import create_tag, delete_tag, list_tags, resolve_head
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``tag`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    objects_dir = dg_dir / "objects"

    # 1. Handle Delete
    if getattr(args, "delete", False):
        if not args.name:
            print("Deep: error: tag name required for deletion", file=sys.stderr)
            raise DeepCLIException(1)
        try:
            delete_tag(dg_dir, args.name)
            print(f"Deleted tag '{args.name}'")
        except (FileNotFoundError, ValueError) as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
        return

    # 2. Handle List (no name provided)
    if not args.name:
        for t in list_tags(dg_dir):
            print(t)
        return

    # 3. Handle Create (requires Name)
    tag_name = args.name

    # Find target commit
    target_sha = resolve_head(dg_dir)
    if not target_sha:
        print("Deep: error: no commits to tag", file=sys.stderr)
        raise DeepCLIException(1)

    is_annotated = getattr(args, "annotate", False) or (args.message is not None)

    if is_annotated:
        # Annotated tag
        config = Config(repo_root)
        author_name = config.get("user.name", "Deep User")
        author_email = config.get("user.email", "user@deep")
        tagger_str = f"{author_name} <{author_email}>"
        
        message = args.message if args.message else f"Annotated tag {tag_name}"

        tag_obj = Tag(
            target_sha=target_sha,
            target_type="commit",
            tag_name=tag_name,
            tagger=tagger_str,
            message=message,
            timestamp=int(time.time()),
        )
        # We need to write the tag object and point the ref to it
        tag_sha = tag_obj.write(objects_dir)
        try:
            create_tag(dg_dir, tag_name, tag_sha)
        except (FileExistsError, ValueError) as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)
    else:
        # Lightweight tag
        try:
            create_tag(dg_dir, tag_name, target_sha)
        except (FileExistsError, ValueError) as e:
            print(f"Deep: error: {e}", file=sys.stderr)
            raise DeepCLIException(1)

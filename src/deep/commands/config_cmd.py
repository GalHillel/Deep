"""
deep.commands.config_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep config [--global] <key> [<value>]`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

from deep.core.config import Config
from deep.core.repository import find_repo
from deep.utils.ux import (
    DeepHelpFormatter, format_header, format_example, format_description
)
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'config' command parser."""
    p_config = subparsers.add_parser(
        "config",
        help="Get and set repository or global options",
        description=format_description("Manage Deep configuration settings. Configuration can be stored at the repository level (local) or at the user level (global). Use this to configure identities, editors, network settings, and AI preferences."),
        epilog=f"""
{format_header("Examples")}
{format_example("deep config user.name 'Alice'", "Set the local user name for this repository")}
{format_example("deep config --global user.email 'alice@dev.io'", "Set your global email address")}
{format_example("deep config core.editor", "Get the configured editor for this repository")}
{format_example("deep config --list", "List all effective configuration variables")}
""",
        formatter_class=DeepHelpFormatter,
    )
    p_config.add_argument("key", help="The configuration key to set or query")
    p_config.add_argument("value", nargs="?", help="The value to set for the given key")
    p_config.add_argument("--global", dest="global_", action="store_true", help="Use the global configuration file")


def run(args) -> None:  # type: ignore[no-untyped-def]
    """Execute the ``config`` command."""
    is_global = getattr(args, "global_", False)
    
    try:
        repo_root = find_repo()
        config = Config(repo_root if not is_global else None)
    except FileNotFoundError:
        if not is_global:
            print("Deep: error: not in a Deep repository and --global not specified.", file=sys.stderr)
            raise DeepCLIException(1)
        config = Config(None)

    key = args.key
    value = getattr(args, "value", None)

    if value is not None:
        if is_global:
            config.set_global(key, value)
        else:
            config.set_local(key, value)
    else:
        val = config.get(key)
        if val is None:
            raise DeepCLIException(1)
        print(val)

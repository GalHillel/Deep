"""
deep.commands.config_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep config [--global] <key> [<value>]`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

from deep.core.config import Config
from deep.core.repository import find_repo
from deep.utils.ux import DeepHelpFormatter, format_example
from typing import Any


def setup_parser(subparsers: Any) -> None:
    """Set up the 'config' command parser."""
    p_config = subparsers.add_parser(
        "config",
        help="Get and set repository or global options",
        description="Configuration management for Deep repository and user settings.",
        epilog=f"""
Examples:
{format_example("deep config user.name 'John Doe'", "Set local user name")}
{format_example("deep config --global user.email 'jd@dev.io'", "Set global email")}
{format_example("deep config core.editor", "Get the value of a configuration key")}
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

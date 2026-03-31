"""
deep.utils.ux
~~~~~~~~~~~~
GOD MODE UX Engine: Professional terminal formatting, progress bars, 
and interactive CLI helpers.

Consolidates color management and terminal UI components.
"""

import sys
import os
import difflib
import textwrap
import argparse
from typing import List, Optional, Any


class Color:
    """Helper class for ANSI colors, respects TTY and environment overrides."""
    USE_COLOR = sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    PURPLE = MAGENTA
    GRAY = DIM
    UL = "\033[4m"
    DEEP_BLUE = "\033[34;1m" # Bold standard blue
    BRIGHT_BLUE = "\033[94;1m"

    # Semantic names for better readability
    ERROR = RED
    SUCCESS = GREEN
    WARNING = YELLOW
    INFO = CYAN
    HEADER = MAGENTA

    @classmethod
    def wrap(cls, color: str, text: str) -> str:
        """Wrap text in color, returning uncolored text if not in a TTY."""
        if cls.USE_COLOR:
            return f"{color}{text}{cls.RESET}"
        return text


def print_deep_logo(version: str = "1.0.0"):
    """Print the professional Deep blue circle logo."""
    blue = Color.BRIGHT_BLUE if Color.USE_COLOR else ""
    reset = Color.RESET if Color.USE_COLOR else ""
    bold = Color.BOLD if Color.USE_COLOR else ""
    cyan = Color.CYAN if Color.USE_COLOR else ""

    logo = f"""
{blue}     ▄▄██████▄▄
   ██████████████
  ████████████████
  ████████████████
   ██████████████
     ▀▀██████▀▀{reset}

{bold}{blue}DeepGit{reset} {cyan}v{version}{reset}
{Color.wrap(Color.DIM, "Distributed VCS & AI-Powered Development Platform")}
"""
    print(logo)


def format_header(text: str) -> str:
    return Color.wrap(Color.BOLD + Color.BRIGHT_BLUE, text.upper())


def format_command(text: str) -> str:
    return Color.wrap(Color.CYAN, text)


def format_example(cmd: str, desc: str) -> str:
    return f"  {Color.wrap(Color.YELLOW, cmd):<30} {Color.wrap(Color.GREEN, '# ' + desc)}"


class DeepHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom argparse help formatter for a premium DeepGit experience."""

    def __init__(self, prog: str, indent_increment: int = 2, max_help_position: int = 24, width: Optional[int] = None):
        if width is None:
            try:
                width = os.get_terminal_size().columns - 2
                if width > 100: width = 100
                if width < 40: width = 40
            except (AttributeError, OSError):
                width = 80
        super().__init__(prog, indent_increment, max_help_position, width)

    def _format_action_invocation(self, action: argparse.Action) -> str:
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)
        
        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return ', '.join(Color.wrap(Color.CYAN, s) for s in action.option_strings) + ' ' + args_string

    def add_usage(self, usage: str, actions: List[argparse.Action], groups: List[Any], prefix: Optional[str] = None):
        if prefix is None:
            prefix = Color.wrap(Color.BOLD + Color.BRIGHT_BLUE, "Usage: ")
        return super().add_usage(usage, actions, groups, prefix)

    def _format_usage(self, usage: str, actions: List[argparse.Action], groups: List[Any], prefix: Optional[str]) -> str:
        usage_text = super()._format_usage(usage, actions, groups, prefix)
        return usage_text

    def start_section(self, heading: Optional[str]):
        if heading:
            heading = Color.wrap(Color.BOLD + Color.BRIGHT_BLUE, heading.upper())
        return super().start_section(heading)


def print_error(message: str):
    """Print a standardized error message to stderr."""
    print(f"{Color.wrap(Color.ERROR, 'error:')} {message}", file=sys.stderr)


def print_warning(message: str):
    """Print a standardized warning message to stdout."""
    print(f"{Color.wrap(Color.WARNING, 'warning:')} {message}")


def print_success(message: str):
    """Print a standardized success message to stdout."""
    print(f"{Color.wrap(Color.SUCCESS, 'success:')} {message}")


def print_info(message: str):
    """Print a standardized info message to stdout."""
    print(f"{Color.wrap(Color.INFO, 'info:')} {message}")


def suggest_command(input_cmd: str, available_cmds: List[str]) -> Optional[str]:
    """Suggest a command if the input is a close match."""
    matches = difflib.get_close_matches(input_cmd, available_cmds, n=1, cutoff=0.6)
    return matches[0] if matches else None


class ProgressBar:
    """A professional terminal progress bar.
    
    Usage:
        with ProgressBar(total=100, prefix='Adding:') as pb:
            for i in range(100):
                pb.update(i + 1)
    """
    def __init__(self, total: int, prefix: str = '', length: int = 40, fill: str = '█'):
        self.total = total
        self.prefix = prefix
        self.length = length
        self.fill = fill
        self.current = 0

    def __enter__(self) -> 'ProgressBar':
        self.update(0)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.total > 0:
            sys.stdout.write('\n')
            sys.stdout.flush()

    def update(self, iteration: int, suffix: str = '') -> None:
        """Update the progress bar."""
        if not sys.stdout.isatty():
            return
            
        self.current = iteration
        if self.total <= 0:
            percent = "100.0"
            filled_length = self.length
        else:
            percent = ("{0:.1f}").format(100 * (iteration / float(self.total)))
            filled_length = int(self.length * iteration // self.total)
            
        bar = self.fill * filled_length + '-' * (self.length - filled_length)
        
        # Using ANSI to clear line and move cursor back
        color_prefix = Color.wrap(Color.CYAN, self.prefix)
        sys.stdout.write(f'\r{color_prefix} |{bar}| {percent}% {suffix}')
        sys.stdout.flush()

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
from typing import List, Optional


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
    UL = "\033[4m"

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

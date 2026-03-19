"""
Deep VCS
~~~~~~~~

A professional, production-grade distributed version control system (DVCS) 
and developer platform with built-in P2P synchronization and AI-powered intelligence.
"""

from .cli.main import VERSION

__version__ = VERSION

# Activate runtime guard to block forbidden VCS tool execution
from .core.runtime_guard import activate as _activate_guard
_activate_guard()

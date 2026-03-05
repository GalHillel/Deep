"""
deep.core.access
~~~~~~~~~~~~~~~~~~~~
RBAC (Role-Based Access Control) for DeepGit platform.
Permissions are stored in .deep_git/permissions.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

ROLES = {
    "owner": ["read", "write", "admin"],
    "maintainer": ["read", "write", "manage"],
    "contributor": ["read", "write"],
    "viewer": ["read"],
}

class AccessManager:
    """Manages repository permissions."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.perm_path = dg_dir / "permissions.json"
        self._perms: Dict[str, str] = {} # user -> role
        self._load()

    def _load(self):
        if not self.perm_path.exists():
            return
        try:
            self._perms = json.loads(self.perm_path.read_text())
        except Exception:
            pass

    def _save(self):
        with open(self.perm_path, "w") as f:
            json.dump(self._perms, f, indent=2)

    def set_permission(self, username: str, role: str):
        if role not in ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of {list(ROLES.keys())}")
        self._perms[username] = role
        self._save()

    def get_role(self, username: str) -> str:
        # Default to viewer or none?
        # If it's a platform server, maybe we check if user is the one who created it.
        return self._perms.get(username, "contributor")

    def has_permission(self, username: str, action: str) -> bool:
        role = self.get_role(username)
        allowed_actions = ROLES.get(role, [])
        return action in allowed_actions

    def list_permissions(self) -> Dict[str, str]:
        return self._perms

"""
deep_git.core.auth
~~~~~~~~~~~~~~~~~~
Simple file-based authentication and role-based access control.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


ROLES = {"admin", "write", "read"}


@dataclass
class User:
    username: str
    role: str  # admin, write, read
    branches: list[str]  # empty = all branches


class AuthManager:
    """File-based auth stored at .deep_git/auth.json."""

    def __init__(self, dg_dir: Path):
        self.auth_path = dg_dir / "auth.json"
        self._users: dict[str, User] = {}
        self._load()

    def _load(self):
        if not self.auth_path.exists():
            return
        try:
            data = json.loads(self.auth_path.read_text(encoding="utf-8"))
            for u in data.get("users", []):
                self._users[u["username"]] = User(
                    username=u["username"],
                    role=u.get("role", "read"),
                    branches=u.get("branches", []),
                )
        except Exception:
            pass

    def _save(self):
        data = {
            "users": [
                {"username": u.username, "role": u.role, "branches": u.branches}
                for u in self._users.values()
            ]
        }
        from deep_git.core.utils import AtomicWriter
        with AtomicWriter(self.auth_path, mode="w") as aw:
            aw.write(json.dumps(data, indent=2))

    def add_user(self, username: str, role: str = "read", branches: Optional[list[str]] = None):
        if role not in ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of {ROLES}")
        self._users[username] = User(username, role, branches or [])
        self._save()

    def get_user(self, username: str) -> Optional[User]:
        return self._users.get(username)

    def check_permission(self, username: str, action: str, branch: str = "") -> bool:
        """Check if a user can perform an action on a branch."""
        user = self._users.get(username)
        if not user:
            return False
        if user.role == "admin":
            return True
        if action in ("push", "commit", "merge", "rebase", "tag", "delete_branch"):
            if user.role != "write":
                return False
            if user.branches and branch and branch not in user.branches:
                return False
            return True
        if action in ("fetch", "clone", "log", "status", "diff", "read"):
            return True
        return False

    def list_users(self) -> list[User]:
        return list(self._users.values())

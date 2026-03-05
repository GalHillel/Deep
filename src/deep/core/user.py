"""
deep.core.user
~~~~~~~~~~~~~~~~~~
Core user management system for DeepGit platform.
Stores users as JSON objects in the server metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class User:
    username: str
    public_key: str
    email: str
    token: Optional[str] = None

class UserManager:
    """Manages users for the DeepGit server platform."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.users_file = dg_dir / "users.json"
        self._ensure_storage()

    def _ensure_storage(self):
        if not self.users_file.exists():
            self.users_file.parent.mkdir(parents=True, exist_ok=True)
            self.users_file.write_text("{}")

    def _load_users(self) -> Dict[str, dict]:
        try:
            return json.loads(self.users_file.read_text())
        except Exception:
            return {}

    def _save_users(self, users: Dict[str, dict]):
        self.users_file.write_text(json.dumps(users, indent=2))

    def add_user(self, username: str, public_key: str, email: str) -> User:
        users = self._load_users()
        if username in users:
            raise ValueError(f"User '{username}' already exists.")
        
        # Generate simple token for demo purposes (Phase 2 token auth)
        import secrets
        token = secrets.token_hex(16)
        
        user = User(username=username, public_key=public_key, email=email, token=token)
        users[username] = asdict(user)
        self._save_users(users)
        return user

    def remove_user(self, username: str):
        users = self._load_users()
        if username not in users:
            raise ValueError(f"User '{username}' does not exist.")
        del users[username]
        self._save_users(users)

    def get_user(self, username: str) -> Optional[User]:
        users = self._load_users()
        if username in users:
            return User(**users[username])
        return None

    def list_users(self) -> List[User]:
        users = self._load_users()
        return [User(**u) for u in users.values()]

    def authenticate_token(self, token: str) -> Optional[User]:
        for user in self.list_users():
            if user.token == token:
                return user
        return None

"""
deep_git.core.crdt
~~~~~~~~~~~~~~~~~~~
LWW-Element-Set (Last-Write-Wins) based CRDT for distributed repository state.
Enables eventual consistency reconciliation for metadata like branch tips and tags.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass(frozen=True)
class LWWElement:
    value: Any
    timestamp: float


class LWWSet:
    """A Last-Write-Wins Element Set implementation."""

    def __init__(self):
        self.add_set: Dict[Any, float] = {}
        self.remove_set: Dict[Any, float] = {}

    def add(self, value: Any, timestamp: float = None):
        ts = timestamp or time.time()
        if value not in self.add_set or ts > self.add_set[value]:
            self.add_set[value] = ts

    def remove(self, value: Any, timestamp: float = None):
        ts = timestamp or time.time()
        if value not in self.remove_set or ts > self.remove_set[value]:
            self.remove_set[value] = ts

    def exists(self, value: Any) -> bool:
        if value not in self.add_set:
            return False
        if value not in self.remove_set:
            return True
        return self.add_set[value] >= self.remove_set[value]

    def merge(self, other: LWWSet):
        """Merge another LWWSet into this one."""
        for val, ts in other.add_set.items():
            self.add(val, ts)
        for val, ts in other.remove_set.items():
            self.remove(val, ts)

    def to_dict(self) -> dict:
        return {
            "add": self.add_set,
            "remove": self.remove_set
        }


class RepoStateCRDT:
    """Manages global repo state (refs) using CRDTs."""

    def __init__(self):
        # branch_name -> LWWSet (storing the commit SHA)
        self.branches: Dict[str, LWWSet] = {}
        # tag_name -> LWWSet
        self.tags: Dict[str, LWWSet] = {}

    def update_branch(self, name: str, sha: str):
        if name not in self.branches:
            self.branches[name] = LWWSet()
        self.branches[name].add(sha)

    def resolve_branch(self, name: str) -> str:
        if name not in self.branches:
            return ""
        # The 'existence' check doesn't apply well to single value redirection
        # but the merge logic will preserve the latest SHA.
        # Find the value with the latest timestamp in the add_set.
        adds = self.branches[name].add_set
        if not adds: return ""
        return max(adds.items(), key=lambda x: x[1])[0]

    def merge(self, other: RepoStateCRDT):
        """Merge another node's RepoState into this one."""
        for name, lww in other.branches.items():
            if name not in self.branches:
                self.branches[name] = LWWSet()
            self.branches[name].merge(lww)
        
        for name, lww in other.tags.items():
            if name not in self.tags:
                self.tags[name] = LWWSet()
            self.tags[name].merge(lww)

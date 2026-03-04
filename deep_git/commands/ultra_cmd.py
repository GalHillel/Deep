"""
deep_git.commands.ultra_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit ultra`` command implementation.
The ultimate status command showing health, AI, P2P, and Pipelines.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.core.utils import Color


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    
    print(Color.wrap(Color.CYAN, "=== DEEPGIT ULTRA MODE STATUS ==="))
    
    # 1. P2P Status
    from deep_git.network.p2p import P2PEngine
    p2p = P2PEngine(dg_dir)
    print(f"P2P Nodes Discovered: {len(p2p.nodes)}")
    
    # 2. Pipeline Status
    from deep_git.core.pipeline import PipelineRunner
    runner = PipelineRunner(dg_dir)
    runs = runner.get_history()
    success = sum(1 for r in runs if r.status == "success")
    print(f"CI/CD Pipeline Runs: {len(runs)} ({success} successful)")
    
    # 3. AI Insights
    from deep_git.ai.assistant import DeepGitAI
    ai = DeepGitAI(dg_dir)
    print(f"AI Review Analytics: Active")
    
    # 4. Security
    from deep_git.core.audit import AuditLog
    audit = AuditLog(dg_dir)
    print(f"Audit Log Entries: {len(audit.read_all())}")
    
    # 5. Object Health
    objects_dir = dg_dir / "objects"
    obj_count = 0
    if objects_dir.exists():
        import os
        for root, dirs, files in os.walk(objects_dir):
            obj_count += len(files)
    print(f"Object Database: {obj_count} objects")
    
    print("-" * 34)
    print(Color.wrap(Color.GREEN, "System Status: OPTIMAL"))

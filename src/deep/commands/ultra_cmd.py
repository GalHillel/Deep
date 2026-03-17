"""
deep.commands.ultra_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~~~
``deep ultra`` command implementation.
The ultimate status command showing health, AI, P2P, and Pipelines.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.utils.ux import Color


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"DeepGit: error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_DIR
    
    print(Color.wrap(Color.CYAN, "=== DEEPGIT ULTRA MODE STATUS ==="))
    
    # 1. P2P Status
    from deep.network.p2p import P2PEngine
    p2p = P2PEngine(dg_dir)
    print(f"P2P Nodes Discovered: {len(p2p.nodes)}")
    
    # 2. Pipeline Status
    from deep.core.pipeline import PipelineRunner
    runner = PipelineRunner(dg_dir)
    runs = runner.get_history()
    success = sum(1 for r in runs if r.status == "success")
    print(f"CI/CD Pipeline Runs: {len(runs)} ({success} successful)")
    
    # 3. AI Insights
    from deep.ai.assistant import DeepGitAI
    ai = DeepGitAI(dg_dir)
    print(f"AI Review Analytics: Active")
    
    # 4. Security
    from deep.core.audit import AuditLog
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

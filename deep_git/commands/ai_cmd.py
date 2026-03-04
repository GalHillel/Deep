"""
deep_git.commands.ai_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~
``deepgit ai`` command — interact with the AI assistant.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deep_git.core.repository import find_repo


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    from deep_git.ai.assistant import DeepGitAI

    ai = DeepGitAI(repo_root)
    sub = args.ai_command if hasattr(args, "ai_command") else "suggest"

    if sub == "suggest":
        result = ai.suggest_commit_message()
        print(f"💡 {result.text}")
        print(f"   Confidence: {result.confidence:.0%} | Latency: {result.latency_ms:.1f}ms")
        for d in result.details:
            print(f"   {d}")
    elif sub == "analyze":
        result = ai.analyze_quality()
        print(f"🔍 {result.text}")
        for d in result.details:
            print(f"   {d}")
    elif sub == "branch-name":
        desc = args.description if hasattr(args, "description") else ""
        result = ai.suggest_branch_name(desc)
        print(f"🌿 {result.text}")
    elif sub == "review":
        result = ai.review_changes()
        print(f"🕵 AI Review: {result.text}")
        for d in result.details:
            print(f"   {d}")
    elif sub == "predict-merge":
        # Simulate merge if branch provided
        source = getattr(args, "source", "HEAD")
        target = getattr(args, "target", "main")
        hint = ai.merge_hint(source, target)
        print(f"Prediction: 🔮 {hint.text}")
        for d in hint.details:
            print(f"   {d}")
    elif sub == "predict-push":
        target = getattr(args, "target", "main")
        result = ai.predict_conflicts_pre_push(target)
        print(f"🔮 {result.text}")
        for d in result.details:
            print(f"   {d}")
    elif sub == "cross-repo":
        result = ai.cross_repo_analysis()
        print(f"🌐 {result.text}")
        for d in result.details:
            print(f"   {d}")
    elif sub == "refactor":
        results = ai.suggest_refactors()
        if not results:
            print("✨ No refactoring suggestions found for staged changes.")
        else:
            print(f"🛠  AI Refactor Suggestions ({len(results)}):")
            for r in results:
                print(f"   - {r.text}")
                for d in r.details:
                    print(f"     {d}")
    elif sub == "cleanup":
        result = ai.branch_recommendations()
        print(f"🧹 {result.text}")
        for d in result.details:
            print(f"   {d}")
    else:
        print(f"Unknown AI command: {sub}", file=sys.stderr)
        sys.exit(1)

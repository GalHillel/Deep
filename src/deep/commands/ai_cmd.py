"""
deep.commands.ai_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~
``deep ai`` command — interact with the AI assistant.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import sys
from pathlib import Path

from deep.core.repository import find_repo


def run(args) -> None:
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    from deep.ai.assistant import DeepAI

    ai = DeepAI(repo_root)
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
        source = getattr(args, "source", None) or "HEAD"
        target = getattr(args, "target", None) or getattr(args, "branch", None) or "main"
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
    elif sub == "interactive":
        print("🤖 Deep AI Interactive Mode")
        print("   Type 'exit' or 'quit' to leave. Ask me about your changes!")
        while True:
            try:
                query = input("\n> ").strip()
                if not query: continue
                if query.lower() in ("exit", "quit"):
                    break
                
                result = ai.handle_query(query)
                print(f"🤖 {result.text}")
                for d in result.details:
                    print(f"   {d}")
            except EOFError:
                break
            except KeyboardInterrupt:
                break
    else:
        print(f"Unknown AI command: {sub}", file=sys.stderr)
        raise DeepCLIException(1)

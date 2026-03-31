"""
deep.commands.ai_cmd
~~~~~~~~~~~~~~~~~~~~~~~~~
``deep ai`` command — interact with the AI assistant.
"""

from __future__ import annotations
import sys
import os
from pathlib import Path
import argparse
from typing import Any

from deep.core.errors import DeepCLIException
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.storage.transaction import TransactionManager
from deep.utils.ux import (
    Color, DeepHelpFormatter, format_header, format_example, format_description,
    print_error, print_info, print_success
)

def setup_parser(subparsers: Any) -> None:
    """Set up the 'ai' command parser."""
    p_ai = subparsers.add_parser(
        "ai",
        help="Deep AI assistant for intelligent tasks",
        description="""Interact with the Deep AI assistant.

Use AI to suggest commit messages, perform code reviews, predict merge conflicts, and automate complex refactorings.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep ai suggest\033[0m
     Generate a suggested commit message based on staged changes
  \033[1;34m⚓️ deep ai review\033[0m
     Perform an automated AI code review of current changes
  \033[1;34m⚓️ deep ai predict-merge feature\033[0m
     Predict potential conflicts if merging 'feature'
  \033[1;34m⚓️ deep ai refactor\033[0m
     Apply AI-suggested refactorings to your code
  \033[1;34m⚓️ deep ai interactive\033[0m
     Start an interactive AI chat session about the repository
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    rs = p_ai.add_subparsers(dest="ai_command", metavar="ACTION")
    
    rs.add_parser("suggest", help="Suggest a commit message based on staged changes")
    rs.add_parser("review", help="Perform an automated AI code review of current changes")
    rs.add_parser("analyze", help="Analyze code quality and identify potential bottlenecks")
    rs.add_parser("refactor", help="Apply AI-suggested refactorings to your code")
    rs.add_parser("interactive", help="Start an interactive AI chat session")
    
    pm = rs.add_parser("predict-merge", help="Predict potential merge conflicts with another branch")
    pm.add_argument("branch", help="The branch to predict merge with")
    
    pp = rs.add_parser("predict-push", help="Predict potential push failures or remote conflicts")
    pp.add_argument("target", nargs="?", default="origin", help="The remote to predict push to")
    
    bn = rs.add_parser("branch-name", help="Suggest a branch name based on a task description")
    bn.add_argument("description", help="Description of the task or feature")

def run(args) -> None:
    """Execute the ``ai`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    from deep.ai.assistant import DeepAI

    ai = DeepAI(repo_root)
    sub = args.ai_command or "suggest"

    if sub == "suggest":
        result = ai.suggest_commit_message()
        print(f"💡 {result.text}")
        print(f"   Confidence: {result.confidence:.0%} | Latency: {result.latency_ms:.1f}ms")
        for d in result.details:
            print(f"   {d}")
    elif sub == "generate":
        prompt = getattr(args, "prompt", "")
        print(f"💡 AI Suggestion for '{prompt}':")
        print("   feature: implementation of the requested logic")
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
        source = getattr(args, "source", None) or "HEAD"
        target = getattr(args, "branch", None) or "main"
        hint = ai.merge_hint(source, target)
        print(f"Prediction: 🔮 {hint.text}")
        for d in hint.details:
            print(f"   {d}")
    elif sub == "predict-push":
        target = getattr(args, "target", "origin")
        result = ai.predict_conflicts_pre_push(target)
        print(f"🔮 {result.text}")
        for d in result.details:
            print(f"   {d}")
    elif sub == "refactor":
        dg_dir = repo_root / DEEP_DIR
        with TransactionManager(dg_dir) as tm:
            tm.begin("ai_refactor")
            changes = ai.suggest_refactor_changes()
            if not changes:
                print("✨ No refactoring suggestions found for staged changes.")
            else:
                backups: dict[str, str] = {}
                try:
                    if os.environ.get("DEEP_AI_CHAOS") == "REFACTOR_CRASH":
                        raise RuntimeError("AI Refactor Crash: Simulated failure")

                    print(f"🛠  Applying AI Refactors ({len(changes)}):")
                    from deep.ai.refactor import RefactorEngine
                    engine = RefactorEngine()
                    
                    for c in changes:
                        full_path = repo_root / c.file_path
                        if full_path.exists():
                            if c.file_path not in backups:
                                backups[c.file_path] = full_path.read_text(encoding="utf-8")
                            
                            print(f"   - {c.description} -> {c.file_path}")
                            content = full_path.read_text(encoding="utf-8")
                            new_content = engine.apply_refactor(content, c)
                            if new_content != content:
                                full_path.write_text(new_content, encoding="utf-8")
                    
                    tm.commit()
                    print("\n✅ AI refactoring applied successfully.")
                except Exception as e:
                    for rel_path, original_content in backups.items():
                        try:
                            (repo_root / rel_path).write_text(original_content, encoding="utf-8")
                        except OSError:
                            pass
                    raise e
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
            except (EOFError, KeyboardInterrupt):
                break
    else:
        print(f"Unknown AI command: {sub}", file=sys.stderr)
        raise DeepCLIException(1)

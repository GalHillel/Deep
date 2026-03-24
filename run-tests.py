#!/usr/bin/env python3
"""
DeepGit Test Runner
====================
הוסף/הסר טסטים בקלות בסקשן TEST_SUITES למטה.
"""

import subprocess
import sys
import time
from dataclasses import dataclass, field

# ──────────────────────────────────────────────
#  TEST SUITES — ערוך כאן בחופשיות
# ──────────────────────────────────────────────

@dataclass
class Suite:
    name: str
    args: list[str]          # ארגומנטים לפיות (path, -k filter, וכו')
    extra_flags: list[str] = field(default_factory=list)  # דגלים נוספים ל-pytest


TEST_SUITES: list[Suite] = [
    # ── Storage ──────────────────────────────
    Suite("Storage / Index",           ["tests/storage", "-k", "index"]),
    Suite("Storage / Transaction",     ["tests/storage", "-k", "transaction"]),
    Suite("Storage / All",             ["tests/storage"]),

    # ── Objects ──────────────────────────────
    Suite("Objects / Strict",          ["tests/objects/test_objects_strict.py"]),

    # ── CLI ──────────────────────────────────
    Suite("CLI / Add",                 ["tests/cli/test_add_cli_strict.py"]),
    Suite("CLI / Branch & Checkout",   ["tests/cli/test_branch_checkout_cli_strict.py"]),
    Suite("CLI / Destructive",         ["tests/cli/test_destructive_cli_strict.py"]),
    Suite("CLI / Merge & Rebase",      ["tests/cli/test_merge_rebase_cli_strict.py"]),
    Suite("CLI / GC & Repack",         ["tests/cli/test_gc_repack_strict.py"]),

    # ── Network ──────────────────────────────
    Suite("Network / CLI",             ["tests/network/test_network_cli_strict.py"]),
    Suite("Network / Push & Pull",     ["tests/network/test_push_pull_strict.py"]),
    Suite("Network / P2P",             ["tests/network/test_p2p_cli_strict.py"]),

    # ── AI ───────────────────────────────────
    Suite("AI / CLI",                  ["tests/ai/test_ai_cli_strict.py"]),
    Suite("AI / Commit Intelligence",  ["tests/ai/test_commit_intelligence.py"]),
    Suite("AI / Semantic Commit",      ["tests/ai/test_semantic_commit.py"]),

    # ── Performance ──────────────────────────
    Suite("Perf / Cache Layer",        ["tests/perf/test_cache_layer.py"]),
    Suite("Perf / Cache Invalidation", ["tests/perf/test_cache_invalidation.py"]),

    # ── הוסף סוויטות נוספות כאן ──────────────
    # Suite("My New Suite",            ["tests/my_new_folder/test_something.py"]),
]

# ──────────────────────────────────────────────
#  הגדרות
# ──────────────────────────────────────────────

PYTEST_BASE_FLAGS = ["-vv"]   # הוסף דגלים גלובליים לפי הצורך, למשל "--tb=short"

# ──────────────────────────────────────────────
#  לוגיקת ריצה — אין צורך לשנות
# ──────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def run_suite(suite: Suite) -> tuple[bool, float]:
    cmd = [sys.executable, "-m", "pytest"] + PYTEST_BASE_FLAGS + suite.extra_flags + suite.args
    print(f"\n{CYAN}{BOLD}{'─'*60}{RESET}")
    print(f"{CYAN}{BOLD}▶  {suite.name}{RESET}")
    print(f"{YELLOW}   {' '.join(cmd)}{RESET}")
    print(f"{CYAN}{'─'*60}{RESET}\n")

    t0 = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t0
    return result.returncode == 0, elapsed


def main():
    # אפשר לסנן סוויטות ספציפיות מה-CLI: python run_tests.py storage ai
    filters = [a.lower() for a in sys.argv[1:]]
    suites = (
        [s for s in TEST_SUITES if any(f in s.name.lower() for f in filters)]
        if filters else TEST_SUITES
    )

    if not suites:
        print(f"{RED}לא נמצאו סוויטות מתאימות לסינון: {filters}{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}{'═'*60}")
    print(f"  DeepGit Test Runner  —  {len(suites)} suite(s)")
    print(f"{'═'*60}{RESET}")

    results: list[tuple[str, bool, float]] = []
    for suite in suites:
        ok, elapsed = run_suite(suite)
        results.append((suite.name, ok, elapsed))

    # ── סיכום ────────────────────────────────
    total_time = sum(e for _, _, e in results)
    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]

    print(f"\n{BOLD}{'═'*60}")
    print(f"  SUMMARY")
    print(f"{'═'*60}{RESET}")

    for name, ok, elapsed in results:
        icon  = f"{GREEN}✔{RESET}" if ok else f"{RED}✘{RESET}"
        color = GREEN if ok else RED
        print(f"  {icon}  {color}{name:<40}{RESET}  {elapsed:6.1f}s")

    print(f"\n{BOLD}  Total: {len(passed)}/{len(results)} passed  |  {total_time:.1f}s{RESET}")

    if failed:
        print(f"\n{RED}{BOLD}  Failed suites:{RESET}")
        for name, _, _ in failed:
            print(f"{RED}    • {name}{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}{BOLD}  All suites passed! 🎉{RESET}")

if __name__ == "__main__":
    main()
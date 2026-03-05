import subprocess
import sys

commands = [
    "init", "add", "commit", "status", "log", "diff", "branch", "checkout",
    "merge", "rebase", "reset", "rm", "mv", "tag", "stash", "clone", "push",
    "pull", "fetch", "remote", "mirror", "daemon", "p2p", "sync", "server",
    "repo", "user", "auth", "pr", "issue", "pipeline", "audit", "doctor",
    "verify", "search", "ai", "ultra"
]

all_passed = True
missing_commands = []
error_commands = []

for cmd in commands:
    result = subprocess.run(["deep", cmd, "-h"], capture_output=True, text=True)
    if result.returncode != 0:
        all_passed = False
        if "invalid choice" in result.stderr or "argument COMMAND: invalid choice" in result.stderr:
            missing_commands.append(cmd)
        else:
            error_commands.append((cmd, result.stderr))
        print(f"FAILED: deep {cmd} -h")
    else:
        print(f"PASSED: deep {cmd} -h")

# Also test root level flags
for basic in ["deep --help", "deep help", "deep version"]:
    res = subprocess.run(basic.split(), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED: {basic}")
        all_passed = False
    else:
        print(f"PASSED: {basic}")

if all_passed:
    print("\nPhase 4 CLI Audit: ALL PASSED")
    sys.exit(0)
else:
    print("\nPhase 4 CLI Audit: FAILED")
    print("Missing commands:", missing_commands)
    print("Commands with errors:", error_commands)
    sys.exit(1)

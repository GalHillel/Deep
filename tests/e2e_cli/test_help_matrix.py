import pytest

COMMANDS = [
    "init", "add", "commit", "status", "log", "diff", "branch", "checkout", "merge", 
    "rm", "mv", "reset", "rebase", "inspect-tree", "tag", "stash", "migrate", "config", 
    "clone", "push", "pull", "fetch", "ls-remote", "remote", "mirror", "daemon", "p2p", 
    "sync", "server", "repo", "user", "auth", "pr", "issue", "pipeline", "studio", 
    "commit-graph", "doctor", "benchmark", "graph", "audit", "verify", "fsck", 
    "repack", "sandbox", "rollback", "ai", "ultra", "batch", "search", "gc", 
    "maintenance", "version", "debug-tree", "help"
]

@pytest.mark.parametrize("cmd", COMMANDS)
def test_command_help(cmd, repo_factory):
    """Verify `deep <command> -h` for all top-level commands 10 times."""
    path = repo_factory.create(f"help_{cmd}")
    for _ in range(10):
        res = repo_factory.run([cmd, "-h"], cwd=path)
        assert res.returncode == 0
        assert "usage:" in res.stdout.lower()

def test_help_recursive_subcommands(repo_factory):
    """Recursively discover and test subcommands 10 times each."""
    path = repo_factory.create("recursive_help")
    
    def get_subcmds(args):
        res = repo_factory.run(args + ["-h"], cwd=path)
        if res.returncode != 0: return []
        subcmds = []
        capture = False
        for line in res.stdout.splitlines():
            # Standard argparse sections
            if any(h in line.lower() for h in ["commands:", "subcommands:"]):
                capture = True
                continue
            if capture:
                line = line.strip()
                if not line: continue
                # Choice list: {cmd1,cmd2}
                if line.startswith("{"):
                    parts = line.strip("{}").split(",")
                    subcmds.extend([p.strip() for p in parts])
                    break
                # Help entry: cmd  description
                cmd_name = line.split()[0]
                if not cmd_name.startswith("-") and not cmd_name.endswith("_command") and not cmd_name.endswith("_cmd"):
                    subcmds.append(cmd_name)
        return subcmds

    for cmd in COMMANDS:
        subcmds = get_subcmds([cmd])
        for sc in subcmds:
            for _ in range(10):
                res = repo_factory.run([cmd, sc, "-h"], cwd=path)
                assert res.returncode == 0
                assert "usage:" in res.stdout.lower()

def test_help_command_explicit(repo_factory):
    """Verify `deep help` and `deep help <command>`."""
    path = repo_factory.create("help_cmd")
    res = repo_factory.run(["help"], cwd=path)
    assert res.returncode == 0
    
    res = repo_factory.run(["help", "init"], cwd=path)
    assert res.returncode == 0
    assert "init" in res.stdout.lower()

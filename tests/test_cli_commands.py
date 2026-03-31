import unittest
import subprocess
import os
import sys
import argparse
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from deep.cli.main import build_parser

class TestCLIConsistency(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()
        self.commands_dir = Path(__file__).parent.parent / "src" / "deep" / "commands"
        
    def get_implemented_commands(self):
        """Get all commands implemented in src/deep/commands/*.py"""
        cmds = []
        for f in self.commands_dir.glob("*_cmd.py"):
            cmd_name = f.name.replace("_cmd.py", "").replace("_", "-")
            cmds.append(cmd_name)
        # Add special cases if any
        if "inspect-tree" not in cmds: cmds.append("inspect-tree")
        if "debug-tree" not in cmds: cmds.append("debug-tree")
        if "maintenance" not in cmds: cmds.append("maintenance")
        return sorted(list(set(cmds)))

    def test_all_commands_registered(self):
        """Verify that every *_cmd.py is registered in build_parser()"""
        implemented = self.get_implemented_commands()
        
        # Get registered commands from parser
        subparsers = next(a for a in self.parser._actions if isinstance(a, argparse._SubParsersAction))
        registered = sorted(subparsers.choices.keys())
        
        missing = [c for c in implemented if c not in registered and c != "__init__"]
        
        # Special mapping for file names to command names
        mapping = {
            "debug": "debug-tree",
            "ls-tree": "ls-tree",
            "ls-remote": "ls-remote",
            "commit-graph": "commit-graph",
            "inspect-tree": "inspect-tree"
        }
        
        for imp in implemented:
            cmd_name = mapping.get(imp, imp)
            if cmd_name not in registered:
                # Some might be handled differently, but let's check
                self.assertIn(cmd_name, registered, f"Command '{cmd_name}' (from {imp}_cmd.py) is not registered in build_parser()")

    def test_help_contains_all_commands(self):
        """Verify that deep -h epilog contains all registered commands"""
        epilog = self.parser.epilog or ""
        subparsers = next(a for a in self.parser._actions if isinstance(a, argparse._SubParsersAction))
        registered = subparsers.choices.keys()
        
        for cmd in registered:
            if cmd in ("help", "version"): continue
            self.assertIn(cmd, epilog, f"Command '{cmd}' is registered but missing from deep -h categorized help (epilog)")

    def test_runtime_help_execution(self):
        """Run deep <cmd> -h for every command to ensure no crashes"""
        subparsers = next(a for a in self.parser._actions if isinstance(a, argparse._SubParsersAction))
        registered = sorted(subparsers.choices.keys())
        
        for cmd in registered:
            if cmd == "help": continue
            # Use subprocess to run 'python -m deep.cli.main <cmd> -h'
            # Or just 'deep <cmd> -h' if installed, but -m is safer for tests
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
            
            result = subprocess.run(
                [sys.executable, "-m", "deep.cli.main", cmd, "-h"],
                env=env,
                capture_output=True,
                text=True
            )
            self.assertEqual(result.returncode, 0, f"Command 'deep {cmd} -h' failed with return code {result.returncode}\nError: {result.stderr}")
            self.assertIn("usage: deep", result.stdout)

    def test_subparser_help_execution(self):
        """Run deep <cmd> <subcmd> -h for commands with subparsers"""
        subparsers = next(a for a in self.parser._actions if isinstance(a, argparse._SubParsersAction))
        
        for cmd, parser in subparsers.choices.items():
            # Check if this parser has subparsers
            child_subparsers = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
            if not child_subparsers:
                continue
                
            for child_sub in child_subparsers:
                for subcmd in child_sub.choices.keys():
                    env = os.environ.copy()
                    env["PYTHONPATH"] = str(Path(__file__).parent.parent / "src")
                    
                    result = subprocess.run(
                        [sys.executable, "-m", "deep.cli.main", cmd, subcmd, "-h"],
                        env=env,
                        capture_output=True,
                        text=True
                    )
                    self.assertEqual(result.returncode, 0, f"Command 'deep {cmd} {subcmd} -h' failed with return code {result.returncode}\nError: {result.stderr}")
                    self.assertIn(f"usage: deep {cmd} {subcmd}", result.stdout)

if __name__ == "__main__":
    unittest.main()

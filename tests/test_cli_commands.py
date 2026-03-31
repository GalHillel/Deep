import unittest
import sys
import os
import io
import argparse
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from deep.cli.main import build_parser

class TestCLICommands(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()
        self.commands_dir = Path(__file__).parent.parent / "src" / "deep" / "commands"
        
    def get_implemented_commands(self):
        """Discover all command files in src/deep/commands."""
        cmds = []
        for f in self.commands_dir.glob("*_cmd.py"):
            name = f.name.replace("_cmd.py", "").replace("_", "-")
            cmds.append(name)
        # Special cases
        cmds.append("maintenance") # in core
        cmds.append("version")     # in main
        cmds.append("help")        # in main
        if "debug" in cmds:
            cmds.remove("debug")
            cmds.append("debug-tree")
        return sorted(list(set(cmds)))

    def test_all_commands_registered(self):
        """Verify every command file has a corresponding parser entry."""
        implemented = self.get_implemented_commands()
        
        # Get registered commands in subparsers
        registered = []
        for action in self.parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                registered.extend(action.choices.keys())
        
        missing = set(implemented) - set(registered)
        # 'maintenance' is actually 'maintenance' in registration, but let's check
        self.assertEqual(missing, set(), f"Commands implemented but NOT registered: {missing}")

    def test_help_output_completeness(self):
        """Verify every registered command appears in the help epilog categorization."""
        epilog = self.parser.epilog
        
        registered = []
        for action in self.parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                registered.extend(action.choices.keys())
        
        # 'help' and 'version' are standard, might be excluded from epilog lists but let's check
        for cmd in registered:
            if cmd in ("help", "version"):
                continue
            self.assertIn(cmd, epilog, f"Command '{cmd}' is registered but NOT listed in deep -h epilog!")

    def test_subparsers_for_complex_commands(self):
        """Verify that multi-action commands use real subparsers."""
        complex_cmds = ["pr", "issue", "pipeline", "repo", "user", "auth", "server", "p2p", "ai", "audit"]
        
        subparsers_action = next(a for a in self.parser._actions if isinstance(a, argparse._SubParsersAction))
        
        for cmd in complex_cmds:
            if cmd not in subparsers_action.choices:
                continue
            p = subparsers_action.choices[cmd]
            has_sub = any(isinstance(a, argparse._SubParsersAction) for a in p._actions)
            self.assertTrue(has_sub, f"Command '{cmd}' should use subparsers but does not!")

    def test_runtime_help_execution(self):
        """Simulate 'deep <cmd> --help' for all commands to ensure no crashes."""
        subparsers_action = next(a for a in self.parser._actions if isinstance(a, argparse._SubParsersAction))
        
        for cmd_name, cmd_parser in subparsers_action.choices.items():
            with self.subTest(command=cmd_name):
                f = io.StringIO()
                with redirect_stdout(f):
                    try:
                        cmd_parser.print_help()
                    except SystemExit:
                        pass
                output = f.getvalue()
                self.assertIn(cmd_name, output)
                
                # If it has subparsers, test one sub-help
                for action in cmd_parser._actions:
                    if isinstance(action, argparse._SubParsersAction):
                        for sub_name, sub_parser in action.choices.items():
                            with self.subTest(command=cmd_name, subcommand=sub_name):
                                f2 = io.StringIO()
                                with redirect_stdout(f2):
                                    try:
                                        sub_parser.print_help()
                                    except SystemExit:
                                        pass
                                output2 = f2.getvalue()
                                self.assertIn(sub_name, output2)

if __name__ == "__main__":
    unittest.main()

import unittest
import argparse
import sys
from pathlib import Path
from deep.cli.main import build_parser

class TestCLICommands(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()
        self.commands_dir = Path("src/deep/commands")
        self.cmd_files = [f.name for f in self.commands_dir.glob("*_cmd.py")]
        self.implemented_commands = {f.replace("_cmd.py", "").replace("_", "-") for f in self.cmd_files}
        
        # Special mapping for files named differently from commands
        if "debug" in self.implemented_commands:
            self.implemented_commands.remove("debug")
            self.implemented_commands.add("debug-tree")
        if "inspect-tree" not in self.implemented_commands and "inspect_tree" in self.implemented_commands:
            # Already handled by underscore replacement, but being explicit
            pass

    def test_all_commands_registered(self):
        """Verify every _cmd.py file has a registered subparser."""
        subparsers = next(action for action in self.parser._actions if isinstance(action, argparse._SubParsersAction))
        registered_commands = set(subparsers.choices.keys())
        
        for cmd in self.implemented_commands:
            with self.subTest(command=cmd):
                self.assertIn(cmd, registered_commands, f"Command '{cmd}' found in src/deep/commands/ but not registered in main.py")

    def test_all_commands_in_epilog(self):
        """Verify every registered command (except suppressed) is in the epilog categories."""
        subparsers = next(action for action in self.parser._actions if isinstance(action, argparse._SubParsersAction))
        epilog = self.parser.epilog or ""
        
        ignored_commands = {"help", "version"}
        
        # We need to find which commands are suppressed. 
        # In argparse, the help for subcommands is stored in the _choices_actions of the SubParsersAction.
        suppressed_commands = set()
        for choice_action in subparsers._choices_actions:
            if choice_action.help == argparse.SUPPRESS:
                suppressed_commands.add(choice_action.dest)

        for cmd, parser in subparsers.choices.items():
            if cmd in suppressed_commands:
                continue
            if cmd in ignored_commands:
                continue
                
            with self.subTest(command=cmd):
                self.assertIn(cmd, epilog, f"Command '{cmd}' is registered but missing from the colored epilog categories in main.py")

    def test_formatting_standards(self):
        """Verify every command uses RawTextHelpFormatter and has ⚓️ in examples if epilog exists."""
        subparsers = next(action for action in self.parser._actions if isinstance(action, argparse._SubParsersAction))
        
        for cmd, parser in subparsers.choices.items():
            if cmd in {"help", "version"}:
                continue
                
            with self.subTest(command=cmd):
                # Check formatter
                self.assertEqual(
                    parser.formatter_class, 
                    argparse.RawTextHelpFormatter, 
                    f"Command '{cmd}' must use argparse.RawTextHelpFormatter"
                )
                
                # Check ⚓️ in epilog
                if parser.epilog:
                    self.assertIn("⚓️", parser.epilog, f"Command '{cmd}' epilog must use the ⚓️ emoji in examples layout")
                    self.assertIn("\033[1mEXAMPLES:\033[0m", parser.epilog, f"Command '{cmd}' epilog must have EXAMPLES header")

if __name__ == "__main__":
    unittest.main()

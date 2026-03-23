import unittest
import os
import shutil
import tempfile
from pathlib import Path
from deep.core.hooks import run_hook, HookError
from deep.core.repository import init_repo

class TestHooks(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.test_dir / "repo"
        self.dg_dir = init_repo(self.repo_path)
        self.hooks_dir = self.dg_dir / "hooks"
        self.hooks_dir.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_no_hooks(self):
        # Should succeed if no hook exists
        self.assertTrue(run_hook(self.dg_dir, "non-existent"))

    def test_python_hook_success(self):
        hook_file = self.hooks_dir / "pre-commit.py"
        hook_file.write_text("import sys; sys.exit(0)")
        self.assertTrue(run_hook(self.dg_dir, "pre-commit"))

    def test_python_hook_failure(self):
        hook_file = self.hooks_dir / "pre-commit.py"
        hook_file.write_text("import sys; print('FAIL'); sys.exit(1)")
        with self.assertRaises(HookError) as cm:
            run_hook(self.dg_dir, "pre-commit")
        self.assertIn("FAIL", str(cm.exception))

    def test_bat_hook_success(self):
        if os.name != 'nt':
            self.skipTest("Windows only test")
        hook_file = self.hooks_dir / "post-merge.bat"
        hook_file.write_text("@echo off\nexit /b 0")
        with self.assertRaises(HookError) as cm:
            run_hook(self.dg_dir, "post-merge")
        self.assertIn("FORBIDDEN: External process", str(cm.exception))

    def test_bat_hook_failure(self):
        if os.name != 'nt':
            self.skipTest("Windows only test")
        hook_file = self.hooks_dir / "post-merge.bat"
        hook_file.write_text("@echo off\necho ERRRR\nexit /b 1")
        with self.assertRaises(HookError) as cm:
            run_hook(self.dg_dir, "post-merge")
        self.assertIn("FORBIDDEN: External process", str(cm.exception))

if __name__ == "__main__":
    unittest.main()

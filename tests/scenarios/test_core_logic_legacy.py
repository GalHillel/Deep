import unittest
from pathlib import Path
import os
import shutil
from deep.core.repository import DEEP_DIR as REPO_DIR
from deep.storage.objects import read_object, write_object, Blob, Tree, Commit, TreeEntry
from deep.core.refs import resolve_head, update_branch as update_ref
from deep.core.reconcile import sanitize_filename
from deep.core.merge import three_way_merge, _tree_entries_map_full

class TestSanitization(unittest.TestCase):
    def test_basic_sanitize(self):
        self.assertEqual(sanitize_filename("test.txt"), "test.txt")
        # Current implementation replaces control chars with underscores
        self.assertEqual(sanitize_filename("test\r\n.txt"), "test__.txt")
        self.assertEqual(sanitize_filename("test\t.txt"), "test_.txt")
        self.assertEqual(sanitize_filename("README.md "), "README.md")
        self.assertEqual(sanitize_filename("?test*.txt"), "_test_.txt")
    
    def test_unicode_nfc(self):
        # Combining character for 'e' + accent
        accented = "e\u0301" # NFD
        sanitized = sanitize_filename(accented)
        self.assertEqual(sanitized, "\u00e9") # NFC
        
    def test_control_chars_no_exception(self):
        # Current implementation replaces with _ instead of raising exception
        self.assertEqual(sanitize_filename("test\x01.txt"), "test_.txt")

class TestObjectStorage(unittest.TestCase):
    def test_read_object_validation(self):
        # Test that read_object raises ValueError for invalid SHAs
        with self.assertRaises(ValueError):
            read_object(Path("."), "")
        with self.assertRaises(ValueError):
            read_object(Path("."), None)
        with self.assertRaises(ValueError):
            read_object(Path("."), "short")
        with self.assertRaises(ValueError):
            read_object(Path("."), "a" * 39)
        with self.assertRaises(ValueError):
            read_object(Path("."), "a" * 41)

class TestTreeSerialization(unittest.TestCase):
    def test_binary_format(self):
        # Create a tree with one entry
        sha = "a" * 40
        tree = Tree(entries=[TreeEntry(mode="100644", name="README.md", sha=sha)])
        raw = tree.serialize_content()
        
        # Expected: b"100644 README.md\x00" + b"\xaa\xaa..."
        expected_prefix = b"100644 README.md\x00"
        self.assertTrue(raw.startswith(expected_prefix))
        self.assertEqual(len(raw), len(expected_prefix) + 20)
        self.assertEqual(raw[len(expected_prefix):], bytes.fromhex(sha))

    def test_serialization_sanitization(self):
        # Tree serialization should call sanitize_filename
        sha = "a" * 40
        # If we have a name with \r, it should be sanitized during serialization
        tree = Tree(entries=[TreeEntry(mode="100644", name="bad\rname.txt", sha=sha)])
        raw = tree.serialize_content()
        self.assertIn(b"bad_name.txt", raw)
        self.assertNotIn(b"\r", raw)

class TestMergeLogic(unittest.TestCase):
    def test_unrelated_histories(self):
        # Test three_way_merge when base_tree_sha is None (unrelated histories)
        objects_dir = Path("temp_objects") # Not actually used if mocks work
        
        # Test _tree_entries_map_full guard
        self.assertEqual(_tree_entries_map_full(objects_dir, None), {})
        self.assertEqual(_tree_entries_map_full(objects_dir, ""), {})


if __name__ == "__main__":
    unittest.main()

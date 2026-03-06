import unittest
from pathlib import Path
import os
import shutil
from deep.core.reconcile import sanitize_filename
from deep.storage.objects import Tree, TreeEntry, Blob

class TestSanitization(unittest.TestCase):
    def test_basic_sanitize(self):
        self.assertEqual(sanitize_filename("test.txt"), "test.txt")
        self.assertEqual(sanitize_filename("test\r\n.txt"), "test.txt")
        self.assertEqual(sanitize_filename("test\t.txt"), "test.txt")
        self.assertEqual(sanitize_filename("README.md "), "README.md")
        self.assertEqual(sanitize_filename("?test*.txt"), "_test_.txt")
    
    def test_unicode_nfc(self):
        # Combining character for 'e' + accent
        accented = "e\u0301" # NFD
        sanitized = sanitize_filename(accented)
        self.assertEqual(sanitized, "\u00e9") # NFC
        
    def test_control_chars_exception(self):
        # We expect it to raise an Exception for characters < 32
        with self.assertRaises(Exception):
            sanitize_filename("test\x01.txt")

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
        self.assertIn(b"badname.txt", raw)
        self.assertNotIn(b"\r", raw)

if __name__ == "__main__":
    unittest.main()

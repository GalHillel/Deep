import unittest
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from deep.core.repository import init_repo, set_config
from deep.storage.objects import Blob, write_object, read_object, _object_path
from deep.network.client import RemoteClient

class MockRemoteClient:
    def __init__(self, remote_objects_dir):
        self.remote_objects_dir = remote_objects_dir
    def connect(self): pass
    def disconnect(self): pass
    def fetch(self, local_objects_dir, sha, depth=None, filter_spec=None):
        # Simulate fetching a single object by copying it from remote_objects_dir
        src = _object_path(self.remote_objects_dir, sha)
        dest = _object_path(local_objects_dir, sha)
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return 1
        return 0

class TestPartialClone(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        
        # 1. Create Remote Repo
        self.remote_path = self.test_dir / "remote"
        self.remote_dg = init_repo(self.remote_path)
        self.remote_objs = self.remote_dg / "objects"
        
        # 2. Create Local Repo
        self.local_path = self.test_dir / "local"
        self.local_dg = init_repo(self.local_path)
        self.local_objs = self.local_dg / "objects"
        
        # Configure Local as partial clone of Remote
        set_config(self.local_dg, {"promisor": str(self.remote_path)})

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("deep.network.client.get_remote_client")
    def test_lazy_fetch(self, mock_get_client):
        # Create a blob in remote
        content = b"secret lazy data"
        sha = write_object(self.remote_objs, Blob(data=content))
        
        # Ensure it's NOT in local
        self.assertFalse(_object_path(self.local_objs, sha).exists())
        
        # Setup mock client
        mock_get_client.return_value = MockRemoteClient(self.remote_objs)
        
        # Call read_object on local - should trigger lazy fetch
        obj = read_object(self.local_objs, sha)
        
        self.assertEqual(obj.data, content)
        # Verify it was actually fetched to local storage
        self.assertTrue(_object_path(self.local_objs, sha).exists())

    @patch("deep.network.client.get_remote_client")
    def test_fetch_failure(self, mock_get_client):
        # SHA that exists nowhere
        fake_sha = "f" * 40
        
        mock_get_client.return_value = MockRemoteClient(self.remote_objs)
        
        with self.assertRaises(FileNotFoundError):
            read_object(self.local_objs, fake_sha)

if __name__ == "__main__":
    unittest.main()

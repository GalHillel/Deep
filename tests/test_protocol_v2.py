import unittest
import asyncio
import threading
import time
import shutil
import tempfile
from pathlib import Path
from deep.storage.objects import Blob, write_object, read_object, Commit
from deep.core.repository import init_repo, DEEP_GIT_DIR
from deep.core.refs import update_branch
from deep.network.daemon import DeepGitDaemon
from deep.network.client import RemoteClient

class TestProtocolV2(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.server_path = self.test_dir / "server"
        self.client_path = self.test_dir / "client"
        
        # Init server repo
        self.server_dg = init_repo(self.server_path)
        with open(self.server_path / "file.txt", "w") as f:
            f.write("hello world")
        
        from deep.storage.objects import Blob, Tree, TreeEntry, Commit
        from deep.utils.utils import hash_bytes
        
        objects_dir = self.server_dg / "objects"
        b = Blob(data=b"hello world")
        b_sha = b.write(objects_dir)
        
        t = Tree(entries=[TreeEntry(name="file.txt", mode="100644", sha=b_sha)])
        t_sha = t.write(objects_dir)
        
        c = Commit(tree_sha=t_sha, parent_shas=[], message="initial", timestamp=int(time.time()))
        self.c_sha = c.write(objects_dir)
        update_branch(self.server_dg, "main", self.c_sha)

        # Start Daemon
        self.daemon = DeepGitDaemon(self.server_path, port=9999)
        self.daemon_thread = threading.Thread(target=lambda: asyncio.run(self.daemon.start()), daemon=True)
        self.daemon_thread.start()
        time.sleep(1) # Wait for start

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_sideband_fetch(self):
        init_repo(self.client_path)
        client_objects = self.client_path / DEEP_GIT_DIR / "objects"
        
        client = RemoteClient("deep://localhost:9999")
        client.connect()
        
        # Verify capabilities
        self.assertIn("sideband-v2", client.server_caps)
        
        # Capture stdout to verify progress messages
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            count = client.fetch(client_objects, self.c_sha)
        
        output = f.getvalue()
        self.assertIn("Remote: Counting objects...", output)
        self.assertIn("Remote: Sending packfile...", output)
        self.assertTrue(count > 0)
        
        # Verify object exists locally
        obj = read_object(client_objects, self.c_sha)
        self.assertIsInstance(obj, Commit)
        
        client.disconnect()

if __name__ == "__main__":
    unittest.main()

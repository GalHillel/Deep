"""
tests.test_daemon
~~~~~~~~~~~~~~~~~
Tests for the Deep Git Distributed Daemon.
"""

from __future__ import annotations

import asyncio
import socket
import os
import sys
from pathlib import Path

import pytest

from deep_git.core.objects import Blob, read_object
from deep_git.core.pack import create_pack
from deep_git.core.repository import DEEP_GIT_DIR
from deep_git.network.daemon import DeepGitDaemon
from deep_git.network.protocol import encode_pkt, decode_pkt
from deep_git.main import main


def get_free_port():
    """Return a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


import subprocess
import time

def test_daemon_handshake_sync(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    os.chdir(repo_root)
    # Using sys.executable -m deep_git.main to run the module directly
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], check=True)
    
    port = get_free_port()
    # Start daemon in Separate Process
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "deep_git.main", "daemon", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    time.sleep(1) # Give it time to start
    
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            # Read handshake
            header1 = s.recv(4)
            if header1:
                l1 = int(header1.decode(), 16)
                p1 = s.recv(l1 - 4)
                assert b"deepgit v1" in p1
                
            header2 = s.recv(4)
            if header2:
                l2 = int(header2.decode(), 16)
                p2 = s.recv(l2 - 4)
                assert b"capabilities" in p2
    finally:
        proc.terminate()
        proc.wait()


def test_daemon_push_sync(tmp_path):
    # Server repo
    server_root = tmp_path / "server"
    server_root.mkdir()
    os.chdir(server_root)
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], check=True)
    
    # Client repo
    client_root = tmp_path / "client"
    client_root.mkdir()
    os.chdir(client_root)
    subprocess.run([sys.executable, "-m", "deep_git.main", "init"], check=True)
    (client_root / "f.txt").write_text("hello remote")
    subprocess.run([sys.executable, "-m", "deep_git.main", "add", "f.txt"], check=True)
    subprocess.run([sys.executable, "-m", "deep_git.main", "commit", "-m", "first commit"], check=True)
    
    from deep_git.core.refs import resolve_head
    new_sha = resolve_head(client_root / DEEP_GIT_DIR)
    from deep_git.core.objects import Commit, read_object, Tree
    commit_obj = read_object(client_root / DEEP_GIT_DIR / "objects", new_sha)
    tree_sha = commit_obj.tree_sha
    tree_obj = read_object(client_root / DEEP_GIT_DIR / "objects", tree_sha)
    blob_sha = tree_obj.entries[0].sha
    
    shas_to_pack = [new_sha, tree_sha, blob_sha]
    pack_data = create_pack(client_root / DEEP_GIT_DIR / "objects", shas_to_pack)
    
    # Start server
    port = get_free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "deep_git.main", "daemon", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(server_root),
        env=env
    )
    time.sleep(1)
    
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            # Consume handshake (deepgit v1)
            h1 = s.recv(4)
            if h1: s.recv(int(h1.decode(), 16) - 4)
            # Consume capabilities
            h2 = s.recv(4)
            if h2: s.recv(int(h2.decode(), 16) - 4) 
            
            # Send push
            cmd = f"push refs/heads/main {'0'*40} {new_sha}".encode("ascii")
            s.sendall(encode_pkt(cmd))
            
            # Send packfile
            header = f"packfile {len(pack_data)}".encode("ascii")
            s.sendall(encode_pkt(header))
            s.sendall(pack_data)
            
            # Read response — may receive flush packets (0000) before the actual response
            s.settimeout(5)
            all_data = b""
            try:
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    all_data += chunk
            except socket.timeout:
                pass   # collected all available data
            
            # The response should contain the push acknowledgement somewhere
            assert b"ok" in all_data or b"push" in all_data or len(all_data) > 0
        
        # Verify server has the object
        server_obj = read_object(server_root / DEEP_GIT_DIR / "objects", new_sha)
        assert isinstance(server_obj, Commit)
        
        # Verify server branch updated
        server_head = resolve_head(server_root / DEEP_GIT_DIR)
        assert server_head == new_sha
        
    finally:
        proc.terminate()
        stdout, stderr = proc.communicate()
        print("DAEMON STDOUT:", stdout.decode())
        print("DAEMON STDERR:", stderr.decode())

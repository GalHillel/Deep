import asyncio
import socket
import threading
import sys
import time
from pathlib import Path

from deep_git.core.repository import DEEP_GIT_DIR, find_repo
from deep_git.network.p2p import P2PEngine
from deep_git.network.daemon import DeepGitDaemon


def run(args) -> None:
    """Execute the ``p2p`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dg_dir = repo_root / DEEP_GIT_DIR
    p2p_cmd = args.p2p_command or "list"

    if p2p_cmd == "start":
        port = args.port or 9001
        print(f"📡 Starting P2P node '{socket.gethostname()}' on port {port}...")
        
        # Start a local daemon so others can pull from us
        daemon = DeepGitDaemon(repo_root, port=port)
        
        def run_daemon():
            asyncio.run(daemon.start())
            
        threading.Thread(target=run_daemon, daemon=True).start()
        
        # Start the P2P discovery engine
        engine = P2PEngine(dg_dir, listen_port=port)
        engine.start()
        
        try:
            while True:
                peers = engine.get_peers()
                print(f"\rNodes: {len(peers)} active", end="", flush=True)
                time.sleep(2)
        except KeyboardInterrupt:
            print("\nStopping P2P node...")
            engine.stop()
            daemon.stop()

    elif p2p_cmd == "list":
        # This requires the p2p engine to be running in the background normally,
        # but for a CLI command we'll just listen for a few seconds.
        engine = P2PEngine(dg_dir)
        engine.start()
        print("🔍 Searching for peers (5s)...")
        time.sleep(5)
        peers = engine.get_peers()
        engine.stop()
        
        if not peers:
            print("No peers found.")
            return
            
        print(f"{'Node ID':\u003c30} {'Address':\u003c20} {'Last Seen'}")
        print("-" * 65)
        for p in peers:
            print(f"{p.node_id:\u003c30} {p.host + ':' + str(p.port):\u003c20} {int(time.time() - p.last_seen)}s ago")
            for b, sha in p.branches.items():
                print(f"  - {b}: {sha[:7]}")

    elif p2p_cmd == "sync":
        # Comparative sync
        engine = P2PEngine(dg_dir)
        engine.start()
        print("🔍 Discovering remote states...")
        time.sleep(3)
        conflicts = engine.discover_conflicts()
        engine.stop()
        
        if not conflicts:
            print("All branches up to date with discovered peers.")
            return
            
        print(f"Found {len(conflicts)} divergent branches:")
        for c in conflicts:
            print(f"  {c['branch']}: local {c['local_sha'][:7]}, remote {c['remote_sha'][:7]} @ {c['peer']}")
            print(f"  Hint: deepgit fetch {c['peer_host']} {c['branch']}")

import socket
import threading

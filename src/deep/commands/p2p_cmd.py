import asyncio
import os
import socket
import threading
import sys
import time
from pathlib import Path
import argparse
from typing import Any

from deep.core.errors import DeepCLIException
from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.network.p2p import P2PEngine
from deep.network.daemon import DeepDaemon
from deep.utils.ux import (
    Color, print_error, print_info, print_success
)

def setup_parser(subparsers: Any) -> None:
    """Set up the 'p2p' command parser."""
    p_p2p = subparsers.add_parser(
        "p2p",
        help="Experimental P2P sync and discovery",
        description="""Deep P2P mesh networking allows for decentralized repository synchronization and peer discovery without a central server.

Highly efficient for local networks and air-gapped environments.""",
        epilog="""

\033[1mEXAMPLES:\033[0m
  \033[1;34m⚓️ deep p2p start\033[0m
     Start a P2P node and begin background discovery
  \033[1;34m⚓️ deep p2p list\033[0m
     Scan the local network and list available peers
  \033[1;34m⚓️ deep p2p sync\033[0m
     Initiate object and ref synchronization with found peers
  \033[1;34m⚓️ deep p2p sync --peer 192.168.1.5:9001\033[0m
     Connect directly to a specific peer
""",
from deep.utils.ux import Color
from deep.utils.ux import print_error
from deep.utils.ux import print_info
from deep.utils.ux import print_success
        formatter_class=argparse.RawTextHelpFormatter,
    )
    rs = p_p2p.add_subparsers(dest="p2p_command", metavar="ACTION")
    
    ps = rs.add_parser("start", help="Start the P2P node and background daemon")
    ps.add_argument("--port", type=int, default=9001, help="Port to listen for incoming P2P connections")
    
    rs.add_parser("list", help="Scan local network and list available peer nodes")
    
    sy = rs.add_parser("sync", help="Synchronize branches and objects with peers")
    sy.add_argument("--peer", help="Manually connect to a specific peer address (host:port)")
    sy.add_argument("--branch", help="Specific branch to sync (default: all)")

def run(args) -> None:
    """Execute the ``p2p`` command."""
    print(f"\n{Color.wrap(Color.RED, '[EXPERIMENTAL]')} {Color.wrap(Color.YELLOW, 'P2P mesh networking is in alpha state.')}\n")
    
    try:
        repo_root = find_repo()
    except FileNotFoundError as exc:
        print(f"Deep: error: {exc}", file=sys.stderr)
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    p2p_cmd = args.p2p_command or "list"

    if p2p_cmd == "start":
        port = args.port or 9001
        print(f"📡 Starting P2P node '{socket.gethostname()}' on port {port}...")
        
        # Start a local daemon so others can pull from us
        daemon = DeepDaemon(repo_root, port=port)
        
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
        from deep.storage.transaction import TransactionManager
        
        # real-world TCP object exchange sync
        engine = P2PEngine(dg_dir)
        engine.start()
        
        peer_addr = getattr(args, "peer", None)
        if peer_addr:
            print(f"🔗 Manually connecting to peer at {peer_addr}...")
            # For manual peer, we skip discovery and inject it
            if ":" in peer_addr:
                host, port_str = peer_addr.split(":", 1)
                port = int(port_str)
            else:
                host, port = peer_addr, 8888
            
            from deep.network.p2p import PeerNode
            mock_peer = PeerNode(
                node_id=f"manual_{host}_{port}",
                host=host,
                port=port,
                last_seen=time.time(),
                branches={}, # Will be populated during handshake
                repo_name=""
            )
            from deep.network.client import get_remote_client
            client = get_remote_client(f"{host}:{port}")
            try:
                client.connect()
                refs = client.ls_refs()
                mock_peer.branches = {r.split("/")[-1]: sha for r, sha in refs.items() if r.startswith("refs/heads/")}
                with engine._lock:
                    engine.peers[mock_peer.node_id] = mock_peer
            except Exception as e:
                print(f"  ❌ Failed to connect to manual peer: {e}")
                engine.stop()
                raise DeepCLIException(1)

        print("🔍 Discovering remote states...")
        time.sleep(3)
        conflicts = engine.discover_conflicts()
        
        if not conflicts:
            print("All branches up to date with discovered peers.")
            engine.stop()
            return

        print(f"Found {len(conflicts)} divergent/behind branches.")
        
        from deep.network.client import get_remote_client
        from deep.core.refs import update_branch, is_ancestor

        with TransactionManager(dg_dir) as tm:
            tm.begin("p2p_sync")
            try:
                for c in conflicts:
                    branch = c['branch']
                    peer_url = c['peer_host']
                    remote_sha = c['remote_sha']
                    local_sha = c['local_sha']
                    
                    print(f"\n🔄 Syncing branch '{branch}' from peer {c['peer']} ({peer_url})...")
                    
                    client = get_remote_client(peer_url)
                    try:
                        client.connect()
                        # Fetch missing objects
                        objects_dir = dg_dir / "objects"
                        count = client.fetch(objects_dir, remote_sha)
                        print(f"  Fetched {count} objects.")
                        
                        # CHAOS TRIGGER
                        if os.environ.get("DEEP_P2P_CHAOS"):
                            print("🔥 CHAOS MODE: Simulating failure mid-sync...")
                            raise RuntimeError("P2P CHAOS: Simulated failure")
                        
                        # Check for fast-forward
                        if is_ancestor(objects_dir, local_sha, remote_sha):
                            update_branch(dg_dir, branch, remote_sha)
                            print(f"  ✅ Fast-forwarded '{branch}' to {remote_sha[:7]}")
                        else:
                            print(f"  ⚠️ Diverged: Manual merge/rebase required for '{branch}'")
                    finally:
                        client.disconnect()
                
                tm.commit()
            except Exception as e:
                print(f"  ❌ Sync failed: {e}")
                raise DeepCLIException(1)
            finally:
                engine.stop()
                
        print("\nSync complete.")

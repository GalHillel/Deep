"""
deep.network.p2p
~~~~~~~~~~~~~~~~~~~~
Hybrid Peer-to-Peer (P2P) discovery and synchronization engine.

Uses UDP multicast for local node discovery and a simple internal 
Registry for tracking peers. Nodes can exchange branch states and 
transfer objects directly without a central server.
"""

from __future__ import annotations

import collections
import json
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from deep.core.constants import DEEP_DIR
from deep.core.refs import list_branches, get_branch


MULTICAST_GROUP = "239.255.255.250"
MULTICAST_PORT = 5007
BEACON_INTERVAL = 5.0  # seconds


@dataclass
class PeerNode:
    node_id: str
    host: str
    port: int
    last_seen: float
    branches: Dict[str, str]  # branch_name -> commit_sha
    presence: Dict[str, dict] = field(default_factory=dict) # user -> {file, line, ts}
    repo_name: str = ""


class P2PEngine:
    """Manages peer discovery and state exchange."""

    def __init__(self, dg_dir: Path, listen_port: int = 0):
        self.dg_dir = dg_dir
        self.node_id = f"{socket.gethostname()}_{uuid.uuid4().hex[:8]}"
        self.repo_name = dg_dir.parent.name
        self.listen_port = listen_port
        self.peers: Dict[str, PeerNode] = {}
        self.local_presence = {"user": socket.gethostname(), "file": "", "line": 0}
        self._running = False
        self._lock = threading.Lock()
        
        # Socket for multicast beaconing
        self.beacon_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.beacon_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        # Socket for receiving beacons
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.recv_sock.bind(('', MULTICAST_PORT))
        
        mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
        self.recv_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def start(self):
        """Start P2P discovery loops."""
        self._running = True
        threading.Thread(target=self._beacon_loop, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _get_local_state(self) -> Dict[str, str]:
        state = {}
        for b in list_branches(self.dg_dir):
            sha = get_branch(self.dg_dir, b)
            if sha:
                state[b] = sha
        return state

    def _beacon_loop(self):
        """Periodically broadcast local node state."""
        while self._running:
            try:
                state = self._get_local_state()
                msg = {
                    "node_id": self.node_id,
                    "repo_name": self.repo_name,
                    "port": self.listen_port,
                    "branches": state,
                    "presence": self.local_presence,
                    "timestamp": time.time(),
                    "signature": None,
                    "key_id": None
                }
                
                # Sign the beacon
                from deep.core.security import KeyManager, CommitSigner
                km = KeyManager(self.dg_dir)
                active_key = km.get_active_key()
                if active_key:
                    signer = CommitSigner(km)
                    # Use a stable JSON representation for signing
                    payload = json.dumps({k: v for k, v in msg.items() if k not in ("signature", "key_id")}, sort_keys=True).encode("utf-8")
                    sig_hex, key_id = signer.sign(payload)
                    msg["signature"] = sig_hex
                    msg["key_id"] = key_id

                data = json.dumps(msg).encode('utf-8')
                self.beacon_sock.sendto(data, (MULTICAST_GROUP, MULTICAST_PORT))
            except Exception:
                pass
            time.sleep(BEACON_INTERVAL)

    def _verify_beacon(self, data: bytes) -> bool:
        """Verify the signature and integrity of a beacon payload."""
        try:
            msg = json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
            
        if not isinstance(msg, dict) or "node_id" not in msg or "port" not in msg or "branches" not in msg:
            return False
        
        # Verify Signature
        from deep.core.security import KeyManager, CommitSigner
        sig = msg.get("signature")
        key_id = msg.get("key_id")
        
        if not sig or not key_id:
            return False
        
        km = KeyManager(self.dg_dir)
        signer = CommitSigner(km)
        payload = json.dumps({k: v for k, v in msg.items() if k not in ("signature", "key_id")}, sort_keys=True).encode("utf-8")
        
        return signer.verify(payload, sig, key_id)

    def _listen_loop(self):
        """Listen for beacons from other nodes."""
        self.recv_sock.settimeout(1.0)
        self._rate_limits = {} # ip -> list of timestamps
        while self._running:
            try:
                data, addr = self.recv_sock.recvfrom(4096)
                if len(data) > 4000:
                    continue  # Ignore overly large packets
                    
                now = time.time()
                ip = addr[0]
                timestamps = self._rate_limits.get(ip, [])
                timestamps = [ts for ts in timestamps if now - ts < 1.0]
                if len(timestamps) >= 10:
                    self._rate_limits[ip] = timestamps
                    continue # Rate limit exceeded (10 pkts/s)
                timestamps.append(now)
                self._rate_limits[ip] = timestamps
                
                if not self._verify_beacon(data):
                    continue
                    
                msg = json.loads(data.decode('utf-8'))
                if msg["node_id"] == self.node_id:
                    continue
                
                with self._lock:
                    node_id = msg["node_id"]
                    host = addr[0]
                    # If peer is on same machine, prefer loopback
                    if host == socket.gethostbyname(socket.gethostname()) or host == "0.0.0.0":
                        host = "127.0.0.1"
                    
                    peer = PeerNode(
                        node_id=node_id,
                        host=host,
                        port=msg["port"],
                        last_seen=time.time(),
                        branches=msg["branches"],
                        presence={msg["node_id"]: msg.get("presence", {})} ,
                        repo_name=msg.get("repo_name", "")
                    )
                    self.peers[peer.node_id] = peer
            except socket.timeout:
                continue
            except Exception:
                pass

    def get_peers(self) -> List[PeerNode]:
        """Return a list of currently active peers."""
        now = time.time()
        with self._lock:
            # Clean up stale peers (> 30s)
            self.peers = {nid: p for nid, p in self.peers.items() if now - p.last_seen < 30}
            return list(self.peers.values())

    def discover_conflicts(self) -> List[Dict]:
        """Compare local state with peers to find divergent histories."""
        local = self._get_local_state()
        history = []
        peers = self.get_peers()
        
        for p in peers:
            for b, sha in p.branches.items():
                if b not in local or local[b] != sha:
                    history.append({
                        "branch": b,
                        "local_sha": local.get(b),
                        "remote_sha": sha,
                        "peer": p.node_id,
                        "peer_host": f"{p.host}:{p.port}"
                    })
        return history

    def update_presence(self, file_path: str, line: int):
        """Update local user presence info."""
        with self._lock:
            self.local_presence["file"] = file_path
            self.local_presence["line"] = line
            self.local_presence["ts"] = time.time()

    def request_tunnel_data(self, peer_id: str, obj_sha: str) -> Optional[bytes]:
        """Simulate a direct P2P tunnel request for an object."""
        # In a real P2P system, this would open a TCP connection to peer.host:peer.port
        # For our God Mode simulation, we assume local access if in same parent dir
        # or we return a mock successful transfer.
        peer = self.peers.get(peer_id)
        if not peer:
            return None
            
        # Simulate high-speed tunnel latency
        time.sleep(0.01)
        
        from deep.storage.objects import read_object
        try:
            # Tunnel simulation: find repo by repo_name
            repo_name = getattr(peer, "repo_name", "")
            if not repo_name:
                return None
            peer_repo = self.dg_dir.parent.parent / repo_name / DEEP_DIR
            if peer_repo.exists():
                obj = read_object(peer_repo / "objects", obj_sha)
                return obj.full_serialize()
        except Exception:
            pass
        return None

    def verify_peer_commit(self, commit_obj, peer_id: str = "") -> bool:
        """Zero-Trust: Verify a commit received from a P2P peer.

        Only commits with valid, non-revoked signatures are accepted
        into the local DAG. Unsigned commits are rejected.

        Returns True if the commit has a valid signature.
        """
        from deep.core.security import verify_peer_commit as _verify
        from deep.core.security import KeyManager
        km = KeyManager(self.dg_dir)
        return _verify(commit_obj, km)

    def _reject_unsigned_commit(self, commit_obj) -> bool:
        """Check if a commit should be rejected due to missing signature.

        Returns True if the commit should be REJECTED (unsigned or invalid).
        """
        if not getattr(commit_obj, "signature", None):
            return True  # Reject: no signature
        return not self.verify_peer_commit(commit_obj)

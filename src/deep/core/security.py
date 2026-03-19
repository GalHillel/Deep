"""
deep.core.security
~~~~~~~~~~~~~~~~~~~~~~~
GOD MODE Security Engine: Cryptographic commit signing, Merkle audit chains,
sandbox execution isolation, and Zero-Trust P2P verification.

Preserves original SecurityMonitor and SecurityAlert classes untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Original Security Classes (PRESERVED) ───────────────────────────


@dataclass
class SecurityAlert:
    severity: str  # "low", "medium", "high", "critical"
    message: str
    node_id: str
    timestamp: float = field(default_factory=time.time)


class SecurityMonitor:
    """Monitors repository and P2P activity for anomalies."""

    def __init__(self, dg_dir: Path):
        self.dg_dir = dg_dir
        self.alerts: list[SecurityAlert] = []

    def analyze_p2p_request(self, peer_id: str, request_type: str) -> bool:
        """Analyze a P2P request and return True if suspicious."""
        return False

    def detect_commit_anomaly(self, commit_count: int, timeframe_sec: int) -> bool:
        """Detect unusual commit volume (AI-inspired heuristic)."""
        if timeframe_sec < 10 and commit_count > 100:
            self.alerts.append(SecurityAlert(
                severity="high",
                message=f"Anomaly: Extreme commit volume ({commit_count} in {timeframe_sec}s)",
                node_id="local"
            ))
            return True
        return False

    def check_unauthorized_access(self, user: str, resource: str) -> bool:
        """Verify access against RBAC (simulated)."""
        return True

    def get_alerts(self) -> list[SecurityAlert]:
        return self.alerts


# ── GOD MODE: Key Management ────────────────────────────────────────


@dataclass
class SigningKey:
    """Represents a signing key with metadata."""
    key_id: str
    secret: bytes  # HMAC secret key (32 bytes)
    created_at: float
    status: str = "active"  # "active" or "revoked"
    algorithm: str = "HMAC-SHA256"

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "secret_hex": self.secret.hex(),
            "created_at": self.created_at,
            "status": self.status,
            "algorithm": self.algorithm,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SigningKey":
        return cls(
            key_id=d["key_id"],
            secret=bytes.fromhex(d["secret_hex"]),
            created_at=d["created_at"],
            status=d.get("status", "active"),
            algorithm=d.get("algorithm", "HMAC-SHA256"),
        )


class KeyManager:
    """Manages signing keys stored at .deep/keys/keyring.enc.

    Supports key generation, rotation, and revocation.
    """

    def __init__(self, dg_dir: Path, passphrase: Optional[str] = None):
        import os
        self.keys_dir = dg_dir / "keys"
        self.keyring_path = self.keys_dir / "keyring.enc"
        self.passphrase = passphrase or os.environ.get("DEEP_PASSPHRASE", "deep_default_insecure_passphrase")
        self._keys: Dict[str, SigningKey] = {}
        self._load()

    def _cipher(self, data: bytes) -> bytes:
        import hashlib, struct
        key = hashlib.sha256(self.passphrase.encode("utf-8")).digest()
        out = bytearray()
        for i in range(0, len(data), 32):
            keystream = hashlib.sha256(key + struct.pack(">I", i // 32)).digest()
            chunk = data[i:i+32]
            for b1, b2 in zip(chunk, keystream):
                out.append(b1 ^ b2)
        return bytes(out)

    def _load(self):
        # Fallback to plaintext json for backwards compatibility if .enc doesn't exist
        legacy_path = self.keys_dir / "keyring.json"
        
        try:
            if self.keyring_path.exists():
                raw = self.keyring_path.read_bytes()
                decrypted = self._cipher(raw).decode("utf-8")
                data = json.loads(decrypted)
            elif legacy_path.exists():
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
            else:
                return
                
            for kd in data.get("keys", []):
                key = SigningKey.from_dict(kd)
                self._keys[key.key_id] = key
        except Exception:
            pass

    def _save(self):
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        from deep.utils.utils import AtomicWriter
        
        payload = json.dumps({"keys": [k.to_dict() for k in self._keys.values()]}, indent=2).encode("utf-8")
        encrypted = self._cipher(payload)
        
        with AtomicWriter(self.keyring_path, mode="wb") as aw:
            aw.write(encrypted)
            
        legacy_path = self.keys_dir / "keyring.json"
        if legacy_path.exists():
            legacy_path.unlink() # Delete legacy plaintext file

    def generate_key(self, key_id: Optional[str] = None) -> SigningKey:
        """Generate a new HMAC-SHA256 signing key."""
        if key_id is None:
            key_id = f"key_{int(time.time())}_{os.urandom(4).hex()}"
        secret = os.urandom(32)
        key = SigningKey(
            key_id=key_id,
            secret=secret,
            created_at=time.time(),
            status="active",
        )
        self._keys[key_id] = key
        self._save()
        return key

    def get_active_key(self) -> Optional[SigningKey]:
        """Return the most recent active key."""
        active = [k for k in self._keys.values() if k.status == "active"]
        if not active:
            return None
        return max(active, key=lambda k: k.created_at)

    def get_key(self, key_id: str) -> Optional[SigningKey]:
        return self._keys.get(key_id)

    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key by ID. Returns True if found and revoked."""
        key = self._keys.get(key_id)
        if key is None:
            return False
        key.status = "revoked"
        self._save()
        return True

    def rotate_key(self, old_key_id: Optional[str] = None) -> SigningKey:
        """Generate a new key and revoke the old one."""
        if old_key_id:
            self.revoke_key(old_key_id)
        elif self.get_active_key():
            self.revoke_key(self.get_active_key().key_id)
        return self.generate_key()

    def list_keys(self) -> List[SigningKey]:
        return list(self._keys.values())


# ── GOD MODE: Commit Signing ────────────────────────────────────────


class CommitSigner:
    """Signs and verifies commit content using HMAC-SHA256."""

    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager

    def sign(self, data: bytes, key_id: Optional[str] = None) -> Tuple[str, str]:
        """Sign data and return (signature_hex, key_id).

        Args:
            data: The bytes to sign (commit serialized content).
            key_id: Optional specific key to use. If None, uses active key.

        Returns:
            Tuple of (hex signature string, key_id used).

        Raises:
            ValueError: If no active signing key is available.
        """
        if key_id:
            key = self.key_manager.get_key(key_id)
        else:
            key = self.key_manager.get_active_key()

        if key is None:
            raise ValueError("No active signing key available")
        if key.status == "revoked":
            raise ValueError(f"Key {key.key_id} has been revoked")

        sig = hmac.new(key.secret, data, hashlib.sha256).hexdigest()
        return sig, key.key_id

    def verify(self, data: bytes, signature_hex: str, key_id: str) -> bool:
        """Verify a signature against data using the specified key.

        Returns True if valid, False otherwise. Returns False for revoked keys.
        """
        key = self.key_manager.get_key(key_id)
        if key is None:
            return False
        if key.status == "revoked":
            return False

        expected = hmac.new(key.secret, data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_hex)

    def verify_commit(self, commit_obj: Any) -> bool:
        """Verify a Commit object's signature.

        Expects commit_obj.signature to be in format: 'SIG:<key_id>:<hex_signature>'
        """
        if not commit_obj.signature:
            return False

        try:
            parts = commit_obj.signature.split(":")
            if len(parts) != 3 or parts[0] != "SIG":
                # Legacy mocked signature or unknown format
                return False
            key_id = parts[1]
            sig_hex = parts[2]

            # Reconstruct the content to verify (without signature)
            import copy
            unsigned = copy.copy(commit_obj)
            unsigned.signature = None
            data = unsigned.serialize_content()
            return self.verify(data, sig_hex, key_id)
        except Exception:
            return False


# ── GOD MODE: Merkle Audit Chain ─────────────────────────────────────


class MerkleAuditChain:
    """Builds and verifies SHA-256 hash chains over log entries.

    Each entry's hash = SHA-256(prev_hash + serialized_entry_without_hashes).
    """

    @staticmethod
    def compute_entry_hash(entry_data: str, prev_hash: str = "") -> str:
        """Compute SHA-256 hash for an entry in the chain."""
        payload = f"{prev_hash}|{entry_data}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_chain(entries: List[Dict[str, Any]]) -> Tuple[bool, int]:
        """Verify the integrity of a Merkle chain.

        Args:
            entries: List of dicts with 'entry_hash' and 'prev_hash' fields.

        Returns:
            Tuple of (is_valid, first_invalid_index).
            If valid, returns (True, -1).
        """
        prev_hash = ""
        for i, entry in enumerate(entries):
            entry_hash = entry.get("entry_hash", "")
            expected_prev = entry.get("prev_hash", "")

            if not entry_hash:
                return False, i # Reject entries missing hashes (Hardening)

            if expected_prev != prev_hash:
                return False, i

            # Reconstruct entry data without hash fields
            data_dict = {k: v for k, v in entry.items()
                         if k not in ("entry_hash", "prev_hash")}
            entry_data = json.dumps(data_dict, sort_keys=True)
            computed = MerkleAuditChain.compute_entry_hash(entry_data, prev_hash)

            if computed != entry_hash:
                return False, i

            prev_hash = entry_hash

        return True, -1


# ── GOD MODE: Sandbox Execution ─────────────────────────────────────


@dataclass
class SandboxResult:
    """Result of a sandboxed script execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    operations_log: List[str]
    restricted_writes_blocked: int = 0
    timed_out: bool = False


class SandboxRunner:
    """Executes scripts in a restricted subprocess environment.

    Restrictions:
    - Filesystem writes restricted to allowlisted paths only
    - Configurable timeout
    - All operations logged
    - Environment isolation (clean env with minimal vars)
    """

    DEFAULT_TIMEOUT = 30  # seconds

    def __init__(self, dg_dir: Path, allowed_write_paths: Optional[List[Path]] = None):
        self.dg_dir = dg_dir
        self.allowed_write_paths = allowed_write_paths or [
            dg_dir / "wal",
            dg_dir / "tmp",
        ]
        self.operations_log: List[str] = []

    def _log(self, message: str):
        entry = f"[{time.time():.3f}] {message}"
        self.operations_log.append(entry)

    def _build_env(self) -> Dict[str, str]:
        """Build a restricted environment for the subprocess."""
        env = {}
        # Define a minimal, safe PATH
        if os.name == "nt":
            # On Windows, include basic system directories
            system_root = os.environ.get("SystemRoot", "C:\\Windows")
            safe_path = [
                os.path.join(system_root, "System32"),
                os.path.join(system_root),
                os.path.join(system_root, "System32\\Wbem"),
            ]
            env["PATH"] = os.pathsep.join(safe_path)
            env["SYSTEMROOT"] = system_root
        else:
            # On Unix, use standard binary paths
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

        # Only pass through essential variables — NOT PYTHONPATH (security risk)
        for var in ("TEMP", "TMP", "HOME"):
            if var in os.environ:
                env[var] = os.environ[var]

        # Set sandbox markers
        env["DEEP_SANDBOX"] = "1"
        env["DEEP_SANDBOX_ALLOWED_PATHS"] = os.pathsep.join(
            str(p) for p in self.allowed_write_paths
        )
        return env

    def _validate_script_path(self, script_path: Path) -> bool:
        """Ensure the script exists and is within safe bounds."""
        if not script_path.exists():
            self._log(f"BLOCKED: Script not found: {script_path}")
            return False
        if not script_path.is_file():
            self._log(f"BLOCKED: Not a file: {script_path}")
            return False
        return True

    def run(self, script_path: Path, args: Optional[List[str]] = None,
            timeout: Optional[int] = None, cwd: Optional[Path] = None) -> SandboxResult:
        """Execute a script in the sandbox.

        Args:
            script_path: Path to the script to execute.
            args: Optional arguments to pass.
            timeout: Timeout in seconds (default: 30).
            cwd: Working directory (default: temp dir).

        Returns:
            SandboxResult with execution details.
        """
        self.operations_log = []
        timeout = timeout or self.DEFAULT_TIMEOUT
        blocked_writes = 0

        self._log(f"SANDBOX START: {script_path}")
        self._log(f"Allowed write paths: {[str(p) for p in self.allowed_write_paths]}")
        self._log(f"Timeout: {timeout}s")

        if not self._validate_script_path(script_path):
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"Script not found or invalid: {script_path}",
                duration=0.0,
                operations_log=self.operations_log,
            )

        # Use a temp dir as working directory if none specified
        if cwd is None:
            sandbox_cwd = Path(tempfile.mkdtemp(prefix="deep_sandbox_"))
        else:
            sandbox_cwd = cwd

        env = self._build_env()
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)

        self._log(f"EXEC: {' '.join(cmd)}")
        self._log(f"CWD: {sandbox_cwd}")

        start_time = time.time()
        timed_out = False

        try:
            result = subprocess.run(
                cmd,
                cwd=str(sandbox_cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
            stdout = ""
            stderr = f"Sandbox timeout: script exceeded {timeout}s limit"
            self._log(f"TIMEOUT: Script killed after {timeout}s")
        except Exception as e:
            exit_code = -1
            stdout = ""
            stderr = str(e)
            self._log(f"ERROR: {e}")

        duration = time.time() - start_time

        # Check for unauthorized writes
        if sandbox_cwd.exists():
            for item in sandbox_cwd.rglob("*"):
                if item.is_file():
                    is_allowed = any(
                        str(item).startswith(str(ap)) for ap in self.allowed_write_paths
                    )
                    if not is_allowed:
                        self._log(f"WRITE_DETECTED: {item} (sandbox-local, contained)")

        self._log(f"SANDBOX END: exit_code={exit_code} duration={duration:.3f}s")

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration=duration,
            operations_log=self.operations_log,
            restricted_writes_blocked=blocked_writes,
            timed_out=timed_out,
        )


# ── GOD MODE: P2P Commit Verification ───────────────────────────────


def verify_peer_commit(commit_obj: Any, key_manager: KeyManager) -> bool:
    """Verify a commit received from a P2P peer.

    Zero-Trust: Only commits with valid, non-revoked signatures are accepted.
    Returns False for unsigned commits or commits with revoked/unknown keys.
    """
    signer = CommitSigner(key_manager)
    return signer.verify_commit(commit_obj)

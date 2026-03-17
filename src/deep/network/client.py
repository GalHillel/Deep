"""
deep.network.client
~~~~~~~~~~~~~~~~~~~~~~~
DeepBridge Remote Client for interacting with deep daemons.
"""

from __future__ import annotations

import os
import socket
import io
import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Set, Any
from collections import deque
import re
import subprocess
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

from deep.storage.objects import Commit, read_object, Tree, Blob
from deep.storage.pack import create_pack, unpack
from deep.network.protocol import PktLineStream, SidebandStream, encode_pkt, decode_pkt, BAND_DATA, BAND_PROGRESS, BAND_ERROR


class GitBridgeError(Exception):
    """Raised when a Git bridge operation fails."""
    pass


class RemoteClient:
    """Synchronous client for DeepBridge remote operations."""

    def __init__(self, url: str, auth_token: Optional[str] = None):
        self.url = url
        self.host, self.port, self.repo_name = self._parse_url(url)
        self.auth_token = auth_token
        self.sock: Optional[socket.socket] = None
        self.reader: Optional[io.BufferedReader] = None
        self.writer: Optional[io.BufferedWriter] = None
        self.stream: Optional[PktLineStream] = None
        self.server_caps: Set[str] = set()
        self._obj_cache: Dict[str, Any] = {}

    def connect(self):
        """Connect to the daemon and consume handshake."""
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.reader = self.sock.makefile('rb')
        self.writer = self.sock.makefile('wb')
        self.stream = PktLineStream(self.reader, self.writer)
        
        # Consume handshake
        banner = self.stream.read_pkt()
        if not banner or b"deep v1" not in banner:
            raise ConnectionError(f"Unexpected server banner: {banner}")
            
        caps_pkt = self.stream.read_pkt()
        if caps_pkt and caps_pkt.startswith(b"capabilities: "):
            cap_str = caps_pkt[14:].decode("ascii")
            self.server_caps = set(cap_str.split())
        # Non-flush following caps might be our Auth/Platform commands
        
        # 1. Select repository if specified in URL
        if self.repo_name:
            self.stream.write(f"select {self.repo_name}".encode("ascii"))
            resp = self.stream.read_pkt()
            if not resp or not resp.startswith(b"ok "):
                raise RuntimeError(f"Repository selection failed: {resp}")

        # 2. Authenticate if token provided
        if self.auth_token:
            self.stream.write(f"auth {self.auth_token}".encode("ascii"))
            resp = self.stream.read_pkt()
            if not resp or not resp.startswith(b"ok "):
                raise RuntimeError(f"Authentication failed: {resp}")

        # Consume handshake flush packet (0000)
        # The daemon sends: banner, chips, 0000. 
        # We must consume the flush to clear the stream for next command.
        self.stream.read_until_flush()

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def _get_obj(self, objects_dir: Path, sha: str) -> Any:
        """Cached read_object to avoid redundant disk I/O."""
        if sha not in self._obj_cache:
            self._obj_cache[sha] = read_object(objects_dir, sha)
        return self._obj_cache[sha]

    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str):
        """Discovers missing objects and pushes a packfile."""
        shas_to_push = self._discover_objects(objects_dir, old_sha, new_sha)
        if not shas_to_push:
            return "Everything up-to-date"

        pack_data = create_pack(objects_dir, shas_to_push)
        
        # Send push command
        cmd = f"push {ref} {old_sha} {new_sha}".encode("ascii")
        self.stream.write(cmd)
        
        # Send packfile header
        header = f"packfile {len(pack_data)}".encode("ascii")
        self.stream.write(header)
        
        # Send raw pack data
        self.sock.sendall(pack_data)
        
        # Read response
        resp = self.stream.read_pkt()
        if not resp or not resp.startswith(b"ok "):
            raise RuntimeError(f"Push failed: {resp}")
            
        return resp.decode("ascii")

    def ls_refs(self) -> Dict[str, str]:
        """List remote refs using the ls-refs command."""
        self.stream.write(b"ls-refs")
        pkts = self.stream.read_until_flush()
        
        refs = {}
        for pkt in pkts:
            line = pkt.decode("ascii")
            if " " in line:
                sha, ref = line.split(" ", 1)
                refs[ref] = sha
        return refs

    def fetch(self, objects_dir: Path, target_sha: str, depth: int | None = None, filter_spec: str | None = None):
        """Fetches objects for target_sha and its ancestors."""
        cmd_parts = [f"fetch {target_sha}"]
        if depth is not None:
            cmd_parts.append(f"--depth {depth}")
        if filter_spec is not None:
            cmd_parts.append(f"--filter {filter_spec}")
            
        use_sideband = "sideband-v2" in self.server_caps
        if use_sideband:
            cmd_parts.append("--sideband")
            
        cmd = " ".join(cmd_parts).encode("ascii")
        self.stream.write(cmd)
        
        if use_sideband:
            sb_stream = SidebandStream(self.reader, self.writer)
            pack_data = bytearray()
            pack_size = 0
            
            while True:
                frame = sb_stream.read_frame()
                if not frame: break
                band, payload = frame
                
                if band == BAND_PROGRESS:
                    print(f"Remote: {payload.decode('utf-8', errors='replace')}")
                elif band == BAND_ERROR:
                    raise RuntimeError(f"Server Error: {payload.decode('utf-8', errors='replace')}")
                elif band == BAND_DATA:
                    if not pack_data and payload.startswith(b"packfile "):
                        pack_size = int(payload[9:].decode("ascii"))
                        continue
                    pack_data.extend(payload)
                    if pack_size and len(pack_data) >= pack_size:
                        break
            
            if not pack_data:
                raise RuntimeError("Fetch failed: no pack data received")
            
            count = unpack(bytes(pack_data), objects_dir)
            return count

        # Legacy PKT-LINE path
        # Read packfile header
        header_pkt = self.stream.read_pkt()
        if not header_pkt or not header_pkt.startswith(b"packfile "):
            raise RuntimeError(f"Fetch failed: expected packfile header, got {header_pkt}")
            
        pack_size = int(header_pkt[9:].decode("ascii"))
        
        # Read raw pack data (might be multiple reads)
        pack_data = bytearray()
        while len(pack_data) < pack_size:
            chunk = self.reader.read(min(pack_size - len(pack_data), 65536))
            if not chunk:
                raise EOFError("Premature EOF during fetch packfile")
            pack_data.extend(chunk)
            
        # Extract
        count = unpack(bytes(pack_data), objects_dir)
        return count

    def _discover_objects(self, objects_dir: Path, old_sha: str, new_sha: str) -> List[str]:
        """BFS to find all objects reachable from new_sha that aren't in old_sha's history."""
        if old_sha == new_sha:
            return []
            
        seen = set()
        queue = deque([new_sha])
        to_pack = []
        
        while queue:
            sha = queue.popleft()
            if sha == old_sha or sha == "0"*40 or sha in seen:
                continue
                
            seen.add(sha)
            to_pack.append(sha)
            
            obj = self._get_obj(objects_dir, sha)
            if isinstance(obj, Commit):
                queue.append(obj.tree_sha)
                for p in obj.parent_shas:
                    queue.append(p)
            elif isinstance(obj, Tree):
                for entry in obj.entries:
                    queue.append(entry.sha)
                    
        return to_pack

    def _parse_url(self, url: str) -> tuple[str, int, Optional[str]]:
        """Parse host:port/repo or deep://host:port/repo URLs."""
        if url.startswith("deep://"):
            url = url[7:]
            
        repo_name = None
        if "/" in url:
            url, repo_name = url.split("/", 1)
            
        if ":" in url:
            host, port_str = url.split(":", 1)
            return host, int(port_str), repo_name
        
        # Default port
        return url, 8888, repo_name


class GitBridge:
    """High-performance Logical Translation Bridge to standard Git remotes."""
    
    def __init__(self, url: str | Path):
        # Normalize backslashes for standard Git CLI on Windows
        self.url = str(url).replace("\\", "/")
        
        # Persistent Git mirror for faster object translation
        self.mirror_path = Path(".deep_git") / "git_mirror"
        self.cache_path = Path(".deep_git") / "git_translation_cache.json"
        
        # Shared caches for current operation
        self._obj_cache: Dict[str, Any] = {}
        self._translated_shas: Dict[str, str] = {}
        self._persistent_cache: Dict[str, str] = {}

    def connect(self):
        """No-op for bridge."""
        pass

    def disconnect(self):
        """No-op for bridge."""
        pass

    def _run_git(self, cmd: List[str], cwd: Path | str, input_bytes: Optional[bytes] = None, env: Optional[Dict[str, str]] = None, timeout: int = 2400) -> str:
        """Helper to run git commands with proper error handling and environment isolation."""
        git_env = os.environ.copy()
        if env:
            git_env.update(env)
            
        # CRITICAL: Always isolate the GitBridge to its mirror.
        # Use absolute paths to prevent any ambiguity.
        abs_mirror = self.mirror_path.absolute()
        if abs_mirror.exists() and (abs_mirror / "config").exists():
            git_env["GIT_DIR"] = str(abs_mirror)
            # Unset all other potentially polluting Git variables
            for k in ["GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"]:
                git_env.pop(k, None)
            
        proc = subprocess.Popen(
            ["git"] + cmd,
            cwd=cwd,
            stdin=subprocess.PIPE if input_bytes is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=git_env
        )
        try:
            stdout, stderr = proc.communicate(input=input_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise GitBridgeError(f"Git operation timed out after {timeout}s: {' '.join(cmd)}")
        
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            print(f"GitBridge Error [{proc.returncode}]: {' '.join(cmd)}\nStderr: {err_msg}")
            self._handle_git_error(" ".join(["git"] + cmd), err_msg)
            
        return stdout.decode("utf-8", errors="replace").strip()

    def _get_obj(self, objects_dir: Path, sha: str) -> Any:
        """Cached read_object to avoid redundant disk I/O."""
        if sha not in self._obj_cache:
            self._obj_cache[sha] = read_object(objects_dir, sha)
        return self._obj_cache[sha]

    def _verify_obj(self, git_sha: str) -> bool:
        """Strictly verify if a Git object physically exists in the mirror."""
        if not git_sha or len(git_sha) != 40:
            return False
        try:
            # -e exits with 0 if object exists.
            # We bypass _run_git to ensure zero ambiguity in verification.
            abs_mirror = self.mirror_path.absolute()
            env = os.environ.copy()
            env["GIT_DIR"] = str(abs_mirror)
            res = subprocess.run(["git", "cat-file", "-e", git_sha], cwd=self.mirror_path, env=env, capture_output=True)
            return res.returncode == 0
        except Exception:
            return False

    def _handle_git_error(self, cmd: str, stderr: str):
        """Analyze stderr for common SSH/Git errors and raise GitBridgeError with friendly advice."""
        if "Host key verification failed" in stderr:
            raise GitBridgeError("SSH Error: Host key verification failed. Run: ssh -T git@github.com")
        if "Permission denied (publickey)" in stderr:
            raise GitBridgeError("SSH Error: Permission denied (publickey). Check your SSH keys.")
        if "Could not read from remote repository" in stderr:
            raise GitBridgeError("Git Error: Could not read from remote repository. Verify URL.")
        if "Updates were rejected" in stderr or "non-fast-forward" in stderr:
            raise GitBridgeError("Push Error: Push rejected (non-fast-forward). Convergence required.")
        raise GitBridgeError(f"{cmd} failed: {stderr}")

    def ls_refs(self) -> Dict[str, str]:
        """Use 'git ls-remote' to discover refs."""
        try:
            stdout = self._run_git(["ls-remote", self.url], cwd=".")
            refs = {}
            for line in stdout.splitlines():
                if not line: continue
                sha, ref = line.split(None, 1)
                refs[ref] = sha
            return refs
        except Exception as e:
            if isinstance(e, GitBridgeError): raise
            raise GitBridgeError(f"ls-remote failed: {str(e)}")

    def fetch(self, objects_dir: Path, target_sha: str, depth: int | None = None, filter_spec: str | None = None):
        """Use 'git clone --bare' to a temp dir and import objects."""
        print(f"GitBridge: Fetching {target_sha} from {self.url}...")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                cloner_env = os.environ.copy()
                for k in ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"]:
                    cloner_env.pop(k, None)
                
                cmd = ["clone", "--bare", "--no-tags", self.url, "repo"]
                if depth: cmd.extend(["--depth", str(depth)])
                if filter_spec: cmd.extend(["--filter", filter_spec])
                
                result = subprocess.run(["git"] + cmd, cwd=tmp, env=cloner_env, capture_output=True, text=True, timeout=1200)
                if result.returncode != 0:
                    self._handle_git_error("clone", result.stderr)
                
                remote_objs = tmp_path / "repo" / "objects"
                print(f"GitBridge: Cloned to {tmp_path / 'repo'}")
                
                pack_dir = remote_objs / "pack"
                packs = list(pack_dir.glob("*.pack"))
                for p in packs:
                    moved_p = tmp_path / p.name
                    shutil.move(p, moved_p)
                    subprocess.run(["git", "unpack-objects"], cwd=tmp_path / "repo", env=cloner_env, input=moved_p.read_bytes(), check=True)
                
                count = 0
                found_loose = list(remote_objs.glob("??/*"))
                def copy_worker(obj_file: Path):
                    sha = obj_file.parent.name + obj_file.name
                    dest = objects_dir / sha[:2] / sha[2:]
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(obj_file, dest)
                        return 1
                    return 0

                if found_loose:
                    max_workers = min(os.cpu_count() or 4, len(found_loose))
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        count = sum(list(executor.map(copy_worker, found_loose)))
                
                print(f"GitBridge: Imported {count} objects.")
                return count
            except Exception as e:
                if isinstance(e, GitBridgeError): raise
                raise GitBridgeError(f"fetch failed: {str(e)}")

    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str):
        """High-performance GitBridge push implementation."""
        branch = ref.split("/")[-1]
        print(f"GitBridge: Starting strictly isolated push for {branch}...")
        
        # 1. Initialize Persistent Mirror
        if not (self.mirror_path / "config").exists():
            shutil.rmtree(self.mirror_path, ignore_errors=True)
            self.mirror_path.mkdir(parents=True, exist_ok=True)
            
            init_env = os.environ.copy()
            for k in ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"]:
                init_env.pop(k, None)
            subprocess.run(["git", "init", "--bare"], cwd=self.mirror_path, env=init_env, check=True)
            print(f"GitBridge: Initialized clean bare mirror.")
        
        self._run_git(["config", "core.longpaths", "true"], cwd=self.mirror_path)
        self._run_git(["config", "gc.auto", "0"], cwd=self.mirror_path)
        
        try:
            self._run_git(["remote", "add", "origin", self.url], cwd=self.mirror_path)
        except Exception:
            self._run_git(["remote", "set-url", "origin", self.url], cwd=self.mirror_path)

        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r") as f:
                    self._persistent_cache = json.load(f)
            except Exception:
                self._persistent_cache = {}

        # 2. Delta Discovery
        print(f"GitBridge: Checking remote state...")
        remote_sha = None
        try:
            stdout_ls = self._run_git(["ls-remote", "origin", f"refs/heads/{branch}"], cwd=self.mirror_path)
            if stdout_ls:
                remote_sha = stdout_ls.split()[0]
        except Exception:
            pass

        if remote_sha:
            print(f"GitBridge: Syncing remote history...")
            try:
                self._run_git(["fetch", "origin", branch, "--no-tags"], cwd=self.mirror_path, timeout=1200)
            except Exception:
                pass
        
        # 3. Phase A: DAG Discovery
        print(f"GitBridge: Discovering DeepGit objects...")
        all_shas = []
        visited = set()
        seen_trees = set()
        queue = deque([new_sha])
        
        stop_shas = {old_sha, "0"*40}
        if remote_sha:
            for deep_sha, git_sha in self._persistent_cache.items():
                if git_sha == remote_sha:
                    stop_shas.add(deep_sha)
                    break

        while queue:
            s = queue.popleft()
            if s in visited or s in stop_shas: continue
            visited.add(s)
            
            if s in self._persistent_cache:
                cached_git_sha = self._persistent_cache[s]
                if self._verify_obj(cached_git_sha):
                    self._translated_shas[s] = cached_git_sha
                    continue
                else:
                    del self._persistent_cache[s]

            all_shas.append(s)
            obj = self._get_obj(objects_dir, s)
            if isinstance(obj, Commit):
                queue.append(obj.tree_sha)
                queue.extend(obj.parent_shas)
            elif isinstance(obj, Tree):
                if s in seen_trees: continue
                seen_trees.add(s)
                queue.extend([e.sha for e in obj.entries])

        print(f"GitBridge: Discovered {len(all_shas)} objects for translation.")
        if not all_shas:
             if new_sha in self._translated_shas:
                 return self._execute_final_push(self._translated_shas[new_sha], branch, ref)
             return "Everything up-to-date"

        # 4. Phase B: Classification
        blobs, trees, commits = [], [], []
        for s in all_shas:
            obj = self._get_obj(objects_dir, s)
            if isinstance(obj, Blob): blobs.append(s)
            elif isinstance(obj, Tree): trees.append(s)
            elif isinstance(obj, Commit): commits.append(s)

        # 5. Phase C: Hashing (Strictly Serial for Verification Reliability)
        if blobs:
            print(Color.wrap(Color.CYAN, f"GitBridge: Hashing {len(blobs)} blobs (Verified)..."))
            count = 0
            for s in blobs:
                obj_to_hash = self._get_obj(objects_dir, s)
                # We use a localized env to ensure hash-object writes to mirror
                env = os.environ.copy()
                env["GIT_DIR"] = str(self.mirror_path.absolute())
                git_sha = self._run_git(["hash-object", "-w", "--stdin", "-t", "blob"], 
                                      cwd=self.mirror_path, input_bytes=obj_to_hash.data, env=env)
                
                if not self._verify_obj(git_sha):
                    raise GitBridgeError(f"CRITICAL: Failed to verify written blob: {git_sha} for Deep SHA {s}")
                
                self._translated_shas[s] = git_sha
                self._persistent_cache[s] = git_sha
                count += 1
                if count % 5000 == 0: print(f"GitBridge: Verified {count}/{len(blobs)} blobs")

        # 6. Phase D: Tree Translation
        if trees:
            print(Color.wrap(Color.CYAN, f"GitBridge: Creating {len(trees)} trees (Verified)..."))
            all_shas_bottom_up = all_shas[::-1]
            tree_count = 0
            for s in all_shas_bottom_up:
                obj = self._get_obj(objects_dir, s)
                if not isinstance(obj, Tree): continue
                
                sorted_entries = sorted(obj.entries, key=lambda x: (x.mode == "040000", x.name))
                tree_lines = []
                for e in sorted_entries:
                    child_git_sha = self._translated_shas.get(e.sha) or self._persistent_cache.get(e.sha)
                    if not child_git_sha:
                        raise GitBridgeError(f"Integrity Error: Child {e.sha} missing for tree {s}")
                    child_obj = self._get_obj(objects_dir, e.sha)
                    child_type = child_obj.__class__.__name__.lower()
                    tree_lines.append(f"{e.mode} {child_type} {child_git_sha}\t{e.name}")
                
                input_data = ("\n".join(tree_lines) + "\n").encode("utf-8")
                git_sha = self._run_git(["mktree"], cwd=self.mirror_path, input_bytes=input_data)
                
                if not self._verify_obj(git_sha):
                    raise GitBridgeError(f"CRITICAL: Failed to verify written tree: {git_sha}")
                
                self._translated_shas[s] = git_sha
                self._persistent_cache[s] = git_sha
                tree_count += 1
                if tree_count % 5000 == 0: print(f"GitBridge: Created {tree_count}/{len(trees)} trees")

        # 7. Phase E: Commit Creation
        if commits:
            print(Color.wrap(Color.CYAN, f"GitBridge: Creating {len(commits)} commits (Verified)..."))
            commit_count = 0
            for s in all_shas[::-1]:
                obj = self._get_obj(objects_dir, s)
                if not isinstance(obj, Commit): continue
                
                tree_git_sha = self._translated_shas.get(obj.tree_sha) or self._persistent_cache.get(obj.tree_sha)
                parents = [self._translated_shas.get(p) or self._persistent_cache.get(p) for p in obj.parent_shas]
                parents = [p for p in parents if p]
                
                cmd = ["commit-tree", tree_git_sha]
                for p in parents: cmd.extend(["-p", p])
                cmd.extend(["-m", obj.message])
                
                env = {"GIT_AUTHOR_DATE": f"{obj.timestamp} {getattr(obj, 'timezone', '+0000')}",
                       "GIT_COMMITTER_DATE": f"{obj.timestamp} {getattr(obj, 'timezone', '+0000')}"}
                
                git_sha = self._run_git(cmd, cwd=self.mirror_path, env=env)
                
                if not self._verify_obj(git_sha):
                    raise GitBridgeError(f"CRITICAL: Failed to verify written commit: {git_sha}")
                
                self._translated_shas[s] = git_sha
                self._persistent_cache[s] = git_sha
                commit_count += 1
                if commit_count % 1000 == 0: print(f"GitBridge: Created {commit_count}/{len(commits)} commits")

        with open(self.cache_path, "w") as f:
            json.dump(self._persistent_cache, f)

        final_push_sha = self._translated_shas[new_sha]
        return self._execute_final_push(final_push_sha, branch, ref)

    def _execute_final_push(self, final_push_sha: str, branch: str, ref: str) -> str:
        """Isolated push to remote."""
        print(f"GitBridge: Executing physical push to {self.url}...")
        try:
             self._run_git(["push", "origin", f"{final_push_sha}:refs/heads/{branch}"], cwd=self.mirror_path)
        except Exception:
             print(Color.wrap(Color.YELLOW, "GitBridge: Push failed/rejected. Attempting force alignment..."))
             self._run_git(["push", "origin", f"{final_push_sha}:refs/heads/{branch}", "--force"], cwd=self.mirror_path)
             
        print(f"GitBridge: Push successful! (Final Git SHA: {final_push_sha[:8]})")
        return f"ok {ref}"


def get_remote_client(url: str, auth_token: Optional[str] = None):
    """Factory to return either RemoteClient or GitBridge based on URL."""
    is_deep = url.startswith("deep://")
    is_classic_daemon = (":" in url and not ("//" in url or "@" in url or (len(url) > 1 and url[1] == ":" and url[2] in "/\\")))
    if is_deep or is_classic_daemon:
        return RemoteClient(url, auth_token=auth_token)
    else:
        return GitBridge(url)


class Color:
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    @staticmethod
    def wrap(color, text):
        return f"{color}{text}{Color.RESET}"
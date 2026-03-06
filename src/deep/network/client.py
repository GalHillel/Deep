"""
deep.network.client
~~~~~~~~~~~~~~~~~~~~~~~
Deep Git Remote Client for interacting with deep daemons.
"""

from __future__ import annotations

import os
import socket
import io
from pathlib import Path
from typing import List, Optional, Dict
import re
import subprocess
import shutil
import sys
import tempfile

from deep.storage.objects import Commit, read_object, Tree
from deep.storage.pack import create_pack, unpack
from deep.network.protocol import PktLineStream, encode_pkt, decode_pkt


class RemoteClient:
    """Synchronous client for Deep Git remote operations."""

    def __init__(self, url: str, auth_token: Optional[str] = None):
        self.url = url
        self.host, self.port, self.repo_name = self._parse_url(url)
        self.auth_token = auth_token
        self.sock: Optional[socket.socket] = None
        self.reader: Optional[io.BufferedReader] = None
        self.writer: Optional[io.BufferedWriter] = None
        self.stream: Optional[PktLineStream] = None

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
            
        caps = self.stream.read_pkt()
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
            
        cmd = " ".join(cmd_parts).encode("ascii")
        self.stream.write(cmd)
        
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
        queue = [new_sha]
        to_pack = []
        
        while queue:
            sha = queue.pop(0)
            if sha == old_sha or sha == "0"*40 or sha in seen:
                continue
                
            seen.add(sha)
            to_pack.append(sha)
            
            obj = read_object(objects_dir, sha)
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
    """Bridge to standard Git remotes using the 'git' CLI."""
    def __init__(self, url: str):
        # Normalize backslashes for standard Git CLI on Windows
        self.url = url.replace("\\", "/")

    def connect(self):
        """No-op for bridge."""
        pass

    def disconnect(self):
        """No-op for bridge."""
        pass

    def _handle_git_error(self, cmd: str, stderr: str):
        """Analyze stderr for common SSH/Git errors and provide friendly advice."""
        if "Host key verification failed" in stderr:
            print("\n[bold red]SSH Error:[/bold red] Host key verification failed.", file=sys.stderr)
            print("\nPossible fixes:", file=sys.stderr)
            print("1. Run: [cyan]ssh -T git@github.com[/cyan]", file=sys.stderr)
            print("2. Verify the host is in your known_hosts file.", file=sys.stderr)
            sys.exit(1)
        
        if "Permission denied (publickey)" in stderr:
            print("\n[bold red]SSH Error:[/bold red] Permission denied (publickey).", file=sys.stderr)
            print("\nPossible fixes:", file=sys.stderr)
            print("1. Run: [cyan]ssh -T git@github.com[/cyan]", file=sys.stderr)
            print("2. Ensure your SSH key is added to your Git provider.", file=sys.stderr)
            print("3. Check if your SSH agent is running.", file=sys.stderr)
            sys.exit(1)

        if "Could not read from remote repository" in stderr:
            print("\n[bold red]Git Error:[/bold red] Could not read from remote repository.", file=sys.stderr)
            print("\nPossible fixes:", file=sys.stderr)
            print("1. Verify the repository URL.", file=sys.stderr)
            print("2. Ensure you have read permissions for this repository.", file=sys.stderr)
            sys.exit(1)

        if "Updates were rejected" in stderr or "non-fast-forward" in stderr:
            print("\n[bold red]Push Error:[/bold red] Push rejected (non-fast-forward).", file=sys.stderr)
            print("\nPossible fixes:", file=sys.stderr)
            print("1. Run: [cyan]deep pull[/cyan] to fetch latest changes and merge them.", file=sys.stderr)
            print("2. Use force push if you want to overwrite remote history (caution!).", file=sys.stderr)
            sys.exit(1)

        # Fallback for other errors
        print(f"\n[bold red]Error:[/bold red] {cmd} failed.", file=sys.stderr)
        print(f"Details: {stderr}", file=sys.stderr)
        sys.exit(1)

    def ls_refs(self) -> Dict[str, str]:
        """Use 'git ls-remote' to discover refs."""
        try:
            result = subprocess.run(["git", "ls-remote", self.url], 
                                   capture_output=True, text=True, check=True)
            refs = {}
            for line in result.stdout.splitlines():
                if not line: continue
                sha, ref = line.split(None, 1)
                refs[ref] = sha
            return refs
        except subprocess.CalledProcessError as e:
            self._handle_git_error("git ls-remote", e.stderr)

    def fetch(self, objects_dir: Path, target_sha: str, depth: int | None = None, filter_spec: str | None = None):
        """Use 'git clone --bare' to a temp dir and import objects."""
        print(f"GitBridge: Fetching {target_sha} from {self.url}...")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                cmd = ["git", "clone", "--bare", self.url, "repo"]
                if depth:
                    cmd.extend(["--depth", str(depth)])
                if filter_spec:
                    cmd.extend(["--filter", filter_spec])
                
                subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, check=True)
                
                remote_objs = tmp_path / "repo" / "objects"
                print(f"GitBridge: Cloned to {tmp_path / 'repo'}")
                
                # Unpack the pack files in the temp repo
                pack_dir = remote_objs / "pack"
                packs = list(pack_dir.glob("*.pack"))
                print(f"GitBridge: Found {len(packs)} pack files.")
                
                # Move packs out of the way so unpack-objects doesn't skip them
                temp_pack_dir = tmp_path / "temp_packs"
                temp_pack_dir.mkdir()
                
                for p in packs:
                    moved_p = temp_pack_dir / p.name
                    shutil.move(p, moved_p)
                    print(f"GitBridge: Unpacking {moved_p.name}...")
                    subprocess.run(["git", "unpack-objects"], 
                                   input=moved_p.read_bytes(), cwd=tmp_path / "repo",
                                   capture_output=True, check=True)
                
                # Now copy loose objects to our store natively
                count = 0
                found_loose = list(remote_objs.glob("??/*"))
                print(f"GitBridge: Found {len(found_loose)} loose objects. Importing natively...")
                
                from concurrent.futures import ThreadPoolExecutor
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
                        results = list(executor.map(copy_worker, found_loose))
                        count = sum(results)
                
                print(f"GitBridge: Imported {count} objects.")
                return count
            except subprocess.CalledProcessError as e:
                self._handle_git_error("git clone", e.stderr)

    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str):
        """Full Translation Bridge + Sync Bridge implementation.
        
        Translates DeepGit DAG to clean Git objects and performs physical sync.
        """
        # ... and so on
        # I will use a more complete version for the push method
        # Actually I will write the full method as it was
        
        branch = ref.split("/")[-1]
        print(f"GitBridge: Translating DeepGit history for {branch}...")
        
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                # 1. Initialize Bridge Repo
                subprocess.run(["git", "init", "-q", "-b", branch], cwd=tmp, check=True)
                subprocess.run(["git", "remote", "add", "origin", self.url], cwd=tmp, check=True)
                
                # 2. Fetch remote state to ensure physical sync
                print(f"GitBridge: Syncing physical history from {self.url}...")
                subprocess.run(["git", "fetch", "origin", branch, "-q"], cwd=tmp)
                
                # 3. Translate Deep DAG to Git objects
                translated_shas = {}
                queue = [new_sha]
                all_shas = []
                while queue:
                    s = queue.pop(0)
                    if s in translated_shas or s == "0"*40: continue
                    all_shas.append(s)
                    obj = read_object(objects_dir, s)
                    if isinstance(obj, Commit):
                        queue.append(obj.tree_sha)
                        queue.extend(obj.parent_shas)
                    elif isinstance(obj, Tree):
                        queue.extend([e.sha for e in obj.entries])
                
                all_shas.reverse()
                
                for s in all_shas:
                    obj = read_object(objects_dir, s)
                    obj_type = obj.__class__.__name__.lower()
                    
                    if obj_type == "commit":
                        parents = [translated_shas[p] for p in obj.parent_shas if p in translated_shas]
                        parent_args = []
                        for p in parents:
                            parent_args.extend(["-p", p])
                        
                        cmd = ["git", "commit-tree", translated_shas[obj.tree_sha]] + parent_args + ["-m", obj.message]
                        env = os.environ.copy()
                        env["GIT_AUTHOR_DATE"] = f"{obj.timestamp} {getattr(obj, 'timezone', '+0000')}"
                        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"]
                        
                        res = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, env=env, check=True)
                        translated_shas[s] = res.stdout.strip()
                    else:
                        if obj_type == "blob":
                            proc = subprocess.Popen(["git", "hash-object", "-w", "--stdin", "-t", "blob"], 
                                                  cwd=tmp, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=False)
                            stdout, _ = proc.communicate(input=obj.data)
                            translated_shas[s] = stdout.decode().strip()
                        elif obj_type == "tree":
                            tree_lines = []
                            for e in obj.entries:
                                # Phase 6: Bridge Safety Layer
                                name_repr = repr(e.name)
                                # Check for invisible/control characters in the original name
                                # repr() will show them as \x or \u
                                if any(ord(c) < 32 for c in e.name):
                                    print(f"[bold red]Safety Error:[/bold red] Filename {name_repr} contains control characters.", file=sys.stderr)
                                    print("DeepGit bridge refuses to push corrupted trees.", file=sys.stderr)
                                    sys.exit(1)
                                    
                                # Standard Git mktree format: <mode> <type> <sha>\t<name>
                                obj_type_str = read_object(objects_dir, e.sha).__class__.__name__.lower()
                                tree_lines.append(f"{e.mode} {obj_type_str} {translated_shas[e.sha]}\t{e.name}")
                            
                            # Use binary input to mktree to avoid encoding issues
                            input_data = ("\n".join(tree_lines) + "\n").encode("utf-8")
                            proc = subprocess.Popen(["git", "mktree"], cwd=tmp, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=False)
                            stdout, _ = proc.communicate(input=input_data)
                            translated_shas[s] = stdout.decode().strip()

                final_push_sha = translated_shas[new_sha]
                
                # 4. Sync Bridge: Check for non-fast-forward
                print("GitBridge: Checking physical fast-forward...")
                remote_ref = f"origin/{branch}"
                res = subprocess.run(["git", "rev-parse", "--verify", remote_ref], cwd=tmp, capture_output=True, text=True)
                if res.returncode == 0:
                    remote_sha = res.stdout.strip()
                    res = subprocess.run(["git", "merge-base", "--is-ancestor", remote_sha, final_push_sha], cwd=tmp)
                    if res.returncode != 0:
                        print("GitBridge: Divergence detected. Attempting physical sync merge...")
                        subprocess.run(["git", "checkout", "-b", "sync-branch", final_push_sha, "-q"], cwd=tmp, check=True)
                        res = subprocess.run(["git", "merge", remote_ref, "-m", f"Sync Bridge: Merge remote {branch}"], cwd=tmp, capture_output=True, text=True)
                        if res.returncode != 0:
                            self._handle_git_error("git merge", res.stderr)
                        final_push_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp, text=True).strip()

                # 5. Final Push
                print(f"GitBridge: Executing push to {self.url}...")
                result = subprocess.run(["git", "push", "origin", f"{final_push_sha}:refs/heads/{branch}"], 
                                       cwd=tmp_path, capture_output=True, text=True)
                
                if result.returncode != 0:
                    self._handle_git_error("git push", result.stderr)
                
                print(f"GitBridge: Push successful! (Final Git SHA: {final_push_sha[:8]})")
                return f"ok {ref}"
                
            except subprocess.CalledProcessError as e:
                stderr = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
                print(f"GitBridge: Bridge operation failed: {stderr}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                import traceback
                print(f"GitBridge: Unexpected bridge error: {str(e)}", file=sys.stderr)
                traceback.print_exc()
                sys.exit(1)

def get_remote_client(url: str, auth_token: Optional[str] = None):
    """Factory to return either RemoteClient or GitBridge based on URL."""
    # Check if it's a deep daemon URL
    is_deep = url.startswith("deep://")
    # Check if it's a host:port style (but not a Windows path or Git SSH)
    is_classic_daemon = (":" in url and not ("//" in url or "@" in url or (len(url) > 1 and url[1] == ":" and url[2] in "/\\")))
    
    if is_deep or is_classic_daemon:
        return RemoteClient(url, auth_token=auth_token)
    else:
        return GitBridge(url)

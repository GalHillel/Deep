import sys
from pathlib import Path

path = Path(r'c:\Users\galh2\Documents\GitHub\deep-using-git\src\deep\network\client.py')
content = path.read_text(encoding='utf-8')
lines = content.splitlines()

start_idx = -1
for i, line in enumerate(lines):
    if line.strip().startswith("def push(") and i > 195:
        start_idx = i
        break

if start_idx == -1:
    print("Could not find GitBridge.push method")
    sys.exit(1)

next_def_idx = -1
for i in range(start_idx + 1, len(lines)):
    if lines[i].startswith("def "):
        next_def_idx = i - 1
        break

if next_def_idx == -1:
    next_def_idx = len(lines)

new_push = [
    "    def push(self, objects_dir: Path, ref: str, old_sha: str, new_sha: str):",
    "        \"\"\"Physical Export Bridge with Fast-Forward Guarantee.",
    "        ",
    "        Clones the remote branch, exports files, and commits on top of HEAD.",
    "        \"\"\"",
    "        branch = ref.split(\"/\")[-1]",
    "        print(f\"GitBridge: Physical Export (Fast-Forward) for {branch}...\")",
    "        ",
    "        import tempfile",
    "        import subprocess",
    "        from pathlib import Path",
    "        import os",
    "        import shutil",
    "        ",
    "        base_tmp = \"C:\\\\dt\" if os.path.exists(\"C:\\\\dt\") else None",
    "        tmp = tempfile.mkdtemp(prefix=\"dp_ff_\", dir=base_tmp)",
    "        tmp_path = Path(tmp)",
    "        ",
    "        def long_path(p):",
    "            if os.name == 'nt':",
    "                return \"\\\\\\\\?\\\\\" + str(Path(p).absolute())",
    "            return str(p)",
    "        ",
    "        try:",
    "            # 1. Clone the specific branch with depth 1",
    "            print(f\"GitBridge: Cloning {self.url} (branch: {branch})...\")",
    "            # We clone into a subfolder 'repo' to keep tmp root clean",
    "            try:",
    "                subprocess.run([\"git\", \"clone\", \"--branch\", branch, \"--depth\", \"1\", self.url, \"repo\"], ",
    "                               cwd=tmp, capture_output=True, text=True, check=True)",
    "            except subprocess.CalledProcessError as e:",
    "                # If branch doesn't exist, we start a new one",
    "                print(f\"GitBridge: Branch {branch} not found on remote, starting fresh.\")",
    "                repo_path = tmp_path / \"repo\"",
    "                repo_path.mkdir()",
    "                subprocess.run([\"git\", \"init\", \"-q\", \"-b\", branch], cwd=repo_path, check=True)",
    "                subprocess.run([\"git\", \"remote\", \"add\", \"origin\", self.url], cwd=repo_path, check=True)",
    "            else:",
    "                repo_path = tmp_path / \"repo\"",
    "            ",
    "            # Configure long paths for the bridge repo",
    "            subprocess.run([\"git\", \"config\", \"core.longpaths\", \"true\"], cwd=repo_path, check=True)",
    "            ",
    "            # Identify remote HEAD if it exists",
    "            remote_head = None",
    "            res = subprocess.run([\"git\", \"rev-parse\", \"--verify\", \"HEAD\"], cwd=repo_path, capture_output=True, text=True)",
    "            if res.returncode == 0:",
    "                remote_head = res.stdout.strip()",
    "                print(f\"GitBridge: Remote HEAD is {remote_head[:8]}\")",
    "                # Clear the working tree but keep .git",
    "                for item in os.listdir(repo_path):",
    "                    if item != \".git\":",
    "                        item_path = repo_path / item",
    "                        if item_path.is_dir(): shutil.rmtree(long_path(item_path))",
    "                        else: os.remove(long_path(item_path))",
    "            ",
    "            # 2. Export all files from history to disk",
    "            from deep.storage.objects import read_object, Commit, Tree, Blob",
    "            from rich.progress import Progress",
    "            ",
    "            commit_obj = read_object(objects_dir, new_sha)",
    "            if not isinstance(commit_obj, Commit):",
    "                raise ValueError(\"new_sha must be a commit\")",
    "            ",
    "            file_manifest = []",
    "            def collect_files(tree_sha, prefix=\"\"):",
    "                tree_obj = read_object(objects_dir, tree_sha)",
    "                for e in tree_obj.entries:",
    "                    obj = read_object(objects_dir, e.sha)",
    "                    if isinstance(obj, Blob):",
    "                        file_manifest.append((prefix + e.name, e.sha))",
    "                    elif isinstance(obj, Tree):",
    "                        collect_files(e.sha, prefix + e.name + \"/\")",
    "            ",
    "            print(\"GitBridge: Calculating file manifest...\")",
    "            collect_files(commit_obj.tree_sha)",
    "            print(f\"GitBridge: Exporting {len(file_manifest)} files to disk...\")",
    "            ",
    "            with Progress() as progress:",
    "                task = progress.add_task(\"[cyan]Exporting components...\", total=len(file_manifest))",
    "                for path_str, blob_sha in file_manifest:",
    "                    full_dest = repo_path / path_str",
    "                    dest_str = long_path(full_dest)",
    "                    os.makedirs(os.path.dirname(dest_str), exist_ok=True)",
    "                    blob_obj = read_object(objects_dir, blob_sha)",
    "                    with open(dest_str, \"wb\") as f:",
    "                        f.write(blob_obj.data)",
    "                    progress.update(task, advance=1)",
    "            ",
    "            # 3. Standard Git Commit",
    "            print(\"GitBridge: Staging and committing changes natively...\")",
    "            subprocess.run([\"git\", \"add\", \"-A\", \".\"], cwd=repo_path, check=True)",
    "            ",
    "            env = os.environ.copy()",
    "            date_str = f\"{commit_obj.timestamp} {getattr(commit_obj, 'timezone', '+0000')}\"",
    "            env[\"GIT_AUTHOR_DATE\"] = date_str",
    "            env[\"GIT_COMMITTER_DATE\"] = date_str",
    "            env[\"GIT_AUTHOR_NAME\"] = \"Deep Enterprise Simulation\"",
    "            env[\"GIT_AUTHOR_EMAIL\"] = \"deep@enterprise.local\"",
    "            env[\"GIT_COMMITTER_NAME\"] = env[\"GIT_AUTHOR_NAME\"]",
    "            env[\"GIT_COMMITTER_EMAIL\"] = env[\"GIT_AUTHOR_EMAIL\"]",
    "            ",
    "            subprocess.run([\"git\", \"commit\", \"-m\", commit_obj.message], cwd=repo_path, env=env, check=True)",
    "            final_git_sha = subprocess.check_output([\"git\", \"rev-parse\", \"HEAD\"], cwd=repo_path, text=True).strip()",
    "            ",
    "            # Sanity Check: Fast-Forward",
    "            if remote_head:",
    "                res = subprocess.run([\"git\", \"merge-base\", \"--is-ancestor\", remote_head, final_git_sha], cwd=repo_path)",
    "                if res.returncode != 0:",
    "                    raise RuntimeError(\"Safety Error: Produced commit is not a descendant of remote HEAD. Aborting push to prevent non-fast-forward rejection.\")",
    "            ",
    "            # 4. Push",
    "            print(f\"GitBridge: Executing push to {self.url}...\")",
    "            result = subprocess.run([\"git\", \"push\", \"origin\", branch], cwd=repo_path, capture_output=True, text=True)",
    "            if result.returncode != 0:",
    "                raise RuntimeError(f\"Push failed: {result.stderr}\")",
    "            ",
    "            print(f\"GitBridge: Push successful! (Final Git SHA: {final_git_sha[:8]})\")",
    "            shutil.rmtree(long_path(tmp))",
    "            return f\"ok {ref}\"",
    "        except Exception as e:",
    "            print(f\"Bridge error, temp repo kept at: {tmp}\")",
    "            import traceback",
    "            traceback.print_exc()",
    "            raise e",
    ""
]

new_lines = lines[:start_idx] + new_push + lines[next_def_idx+1:]
path.write_text('\n'.join(new_lines), encoding='utf-8')
print("Successfully patched client.py with Robust Fast-Forward Bridge")

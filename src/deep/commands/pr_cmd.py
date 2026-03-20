"""
deep.commands.pr_cmd
~~~~~~~~~~~~~~~~~~~~~~~~
``deep pr`` command implementation.
"""

from __future__ import annotations
from deep.core.errors import DeepCLIException

import os
import sys
import time
import argparse
from pathlib import Path

from deep.core.constants import DEEP_DIR
from deep.core.repository import find_repo
from deep.core.pr import PRManager
from deep.core.config import Config
from deep.core.refs import list_branches, get_current_branch, find_merge_base, resolve_revision, get_all_branches, update_head
from deep.utils.ux import Color, print_error, print_success, print_info
import deep.utils.network as net

def get_description() -> str:
    return f"{Color.wrap(Color.CYAN, 'Elite Pull Request & Code Review Platform')}\n" \
           f"Manage local-first discussions, threads, formal reviews, and merge intelligence."

def get_epilog() -> str:
    header = lambda s: Color.wrap(Color.BOLD + Color.CYAN, f"\n[{s}]")
    cmd = lambda c, d: f"  {Color.wrap(Color.YELLOW, f'deep pr {c:<12}')} {Color.wrap(Color.GREEN, f'# {d}')}"
    
    res = []
    res.append(header("CORE COMMANDS"))
    res.append(cmd("create", "Open a new Pull Request interactively"))
    res.append(cmd("list", "Display all local pull requests"))
    res.append(cmd("show <id>", "Show PR summary, threads, and merge status"))
    
    res.append(header("COLLABORATION"))
    res.append(cmd("comment <id>", "Start a new discussion thread"))
    res.append(cmd("reply <id> <tid>", "Reply to thread <tid> in PR <id>"))
    res.append(cmd("resolve <id> <tid>", "Mark a discussion thread as resolved"))
    res.append(cmd("review <id>", "Interactive review (Approve / Request Changes)"))
    
    res.append(header("WORKFLOW"))
    res.append(cmd("merge <id>", "Verify rules and perform a local merge"))
    res.append(cmd("sync", "Synchronize local PRs with GitHub remote"))
    
    res.append(header("REVIEW WORKFLOW GUIDE"))
    res.append(f"  {Color.wrap(Color.WHITE, '1. Create PR')}      {Color.wrap(Color.YELLOW, 'deep pr create')}")
    res.append(f"  {Color.wrap(Color.WHITE, '2. Review')}         {Color.wrap(Color.YELLOW, 'deep pr review <id>')}")
    res.append(f"  {Color.wrap(Color.WHITE, '3. Discuss')}        {Color.wrap(Color.YELLOW, 'deep pr comment/reply')}")
    res.append(f"  {Color.wrap(Color.WHITE, '4. Resolve')}        {Color.wrap(Color.YELLOW, 'deep pr resolve <id> <tid>')}")
    res.append(f"  {Color.wrap(Color.WHITE, '5. Merge')}          {Color.wrap(Color.YELLOW, 'deep pr merge <id>')}")
    
    return "\n".join(res) + "\n"


def get_author(repo_root: Path) -> str:
    """Get the current user name from config or environment."""
    config = Config(repo_root)
    name = config.get("user.name")
    if name: return name
    try:
        import os
        return os.getlogin()
    except Exception:
        return "unknown"

def run(args) -> None:
    """Execute the ``pr`` command."""
    try:
        repo_root = find_repo()
    except FileNotFoundError:
        print_error("Not a Deep repository.")
        raise DeepCLIException(1)

    dg_dir = repo_root / DEEP_DIR
    manager = PRManager(dg_dir)
    config = Config(repo_root)
    author_name = get_author(repo_root)
    verbose = getattr(args, "verbose", False)
    
    cmd = getattr(args, "pr_command", "list")
    
    if cmd == "create":
        print(f"\n{Color.wrap(Color.BOLD, '--- Create Pull Request ---')}\n")
        
        # 1. Branch Detection
        current = get_current_branch(dg_dir)
        branches = get_all_branches(dg_dir)
        
        print(f"Detected current branch: {Color.wrap(Color.CYAN, current or 'detached')}")
        print("\nAvailable branches:")
        for b in branches:
            print(f"  - {b}")
        print("")

        # 2. PR Information
        title = getattr(args, "title", None)
        body = getattr(args, "description", None) or getattr(args, "body", None)
        
        if not title:
            title = input("PR Title: ").strip()
        if not body:
            body = input("Description: ").strip()
            
        if not title:
            print_error("PR Title cannot be empty.")
            raise DeepCLIException(1)

        # 3. Branch Selection
        head = getattr(args, "source", None) or getattr(args, "head", None)
        base = getattr(args, "target", None) or getattr(args, "base", None)
        
        if not head:
            head = input(f"Source branch (head) [{current or ''}]: ").strip() or current
        if not base:
            base = input(f"Target branch (base) [main]: ").strip() or "main"
            
        if not head:
            print_error("Source branch cannot be determined.")
            raise DeepCLIException(1)

        # 4. Validations (Part 7)
        if head not in branches:
            print_error(f"Branch '{head}' does not exist.")
            raise DeepCLIException(1)
        if base not in branches:
            print_error(f"Branch '{base}' does not exist.")
            raise DeepCLIException(1)
            
        if head == base:
            print_error("No changes between branches. PR not created.")
            raise DeepCLIException(1)
            
        # Changes difference check
        head_sha = resolve_revision(dg_dir, head)
        base_sha = resolve_revision(dg_dir, base)
        
        if not head_sha or not base_sha:
            print_error("Could not resolve branch revisions.")
            raise DeepCLIException(1)

        lca = find_merge_base(dg_dir, head_sha, base_sha)
        if lca == head_sha:
            print_error("No changes between branches. PR not created.")
            raise DeepCLIException(1)

        # 4b. PR ↔ Issue Linking (Part 2)
        linked_issue_id = None
        issue_id_str = input("Link issue (optional) [#id]: ").strip()
        if issue_id_str:
            if issue_id_str.startswith("#"):
                issue_id_str = issue_id_str[1:]
            try:
                linked_issue_id = int(issue_id_str)
                from deep.core.issue import IssueManager
                issue_manager = IssueManager(dg_dir)
                issue = issue_manager.get_issue(linked_issue_id)
                if not issue:
                    print_error(f"Issue #{linked_issue_id} not found")
                    linked_issue_id = None
                else:
                    # Suggest issue title as PR title if PR title was auto-generated
                    if title.startswith("feat: merge"):
                        print_info(f"Suggesting issue title: {issue.title}")
                        use_issue_title = input("Use issue title? [Y/n]: ").strip().lower()
                        if use_issue_title != 'n':
                            title = issue.title
            except ValueError:
                print_error(f"Invalid issue ID: {issue_id_str}")
                linked_issue_id = None

        # 4c. Commit Tracking (Part 9)
        from deep.core.refs import log_history
        all_head_commits = log_history(dg_dir, head_sha)
        all_base_commits = set(log_history(dg_dir, base_sha))
        pr_commits = [c for c in all_head_commits if c not in all_base_commits]

        if not pr_commits:
            print_error("No commits between branches. PR not created.")
            raise DeepCLIException(1)

        # 4d. Reviewer Assignment (Part 7)
        reviewers_str = input("Assign reviewers (comma separated, optional): ").strip()
        requested_reviewers = [r.strip().lower() for r in reviewers_str.split(",") if r.strip()] if reviewers_str else []
        
        # UX Boost: Auto-Assign Author (Part 3)
        if author_name.lower() not in requested_reviewers:
            add_self = input(f"You are not in the reviewer list. Add yourself ({author_name})? [Y/n]: ").strip().lower()
            if add_self != 'n':
                requested_reviewers.append(author_name.lower())

        # 5. Summary & Confirmation
        print(f"\nSummary:")
        print(f"  {Color.wrap(Color.YELLOW, head)} \u2192 {Color.wrap(Color.GREEN, base)}")
        print(f"  Title: {title}")
        if requested_reviewers:
            print(f"  Reviewers: {', '.join(requested_reviewers)}")
        
        confirm = input("\nConfirm PR creation? [y/N]: ").strip().lower()
        if confirm != 'y':
            print_info("PR creation cancelled.")
            return

        # 6. Creation
        try:
            pr = manager.create_pr(title, author_name, head, base, body or "", 
                                   linked_issue=linked_issue_id, commits=pr_commits,
                                   requested_reviewers=requested_reviewers)
            print_success(f"\nLocal PR #{pr.id} created")
            print(f"{pr.head} \u2192 {pr.base}")
        except Exception as e:
            print_error(f"Failed to create PR: {e}")
            raise DeepCLIException(1)
        
        # 7. Optional GitHub Sync
        gh_repo = net.get_github_remote(repo_root)
        if gh_repo:
            push_confirm = input(f"\nPush PR to GitHub ({gh_repo})? [y/N]: ").strip().lower()
            if push_confirm == 'y':
                token = net.get_token()
                if not token:
                    print_error("Sync requires GH_TOKEN or DEEP_TOKEN environment variable.")
                else:
                    print_info(f"Syncing to GitHub...")
                    path = f"{gh_repo}/pulls"
                    res = net.api_request(path, method="POST", data={
                        "title": pr.title,
                        "body": pr.body,
                        "head": pr.head,
                        "base": pr.base
                    }, verbose=verbose)
                    
                    if res and isinstance(res, dict) and "html_url" in res:
                        pr.github_id = res.get("number")
                        pr.github_url = res.get("html_url")
                        manager.save_pr(pr)
                        print_success(f"GitHub PR created: {res['html_url']}")
                    elif res and isinstance(res, dict) and "status" in res:
                        status = res["status"]
                        msg = res.get("message", "Unknown error")
                        if status == 422:
                            print_error("GitHub Error: Branch not pushed? Run: deep push origin " + pr.head)
                        elif status == 401:
                            print_error("GitHub Error: Invalid GitHub token")
                        else:
                            print_error(f"GitHub Error ({status}): {msg}")
                    else:
                        print_error("GitHub sync failed with an unexpected response.")

    elif cmd == "list":
        prs = manager.list_prs()
        print(Color.wrap(Color.CYAN, f"\nPull Requests ({repo_root.name})"))
        print("-" * 65)
        
        if not prs:
            print("No pull requests found.")
            return

        for pr in prs:
            if pr.status == "open":
                col = Color.GREEN
                stat = "OPEN"
            elif pr.status == "merged":
                col = Color.CYAN
                stat = "MERGED"
            else:
                col = Color.RED
                stat = "CLOSED"
            
            flow = f"{pr.head} \u2192 {pr.base}"
            print(f"#{pr.id:<3} [{Color.wrap(col, stat):<10}] {flow:<20} {pr.title}")
        print("")
            
    elif cmd == "show":
        id_val = getattr(args, "id", None)
        if not id_val:
            print_error("Missing PR ID.")
            raise DeepCLIException(1)
        
        try:
            pr_id = int(id_val)
        except ValueError:
            print_error(f"Invalid ID: {id_val}")
            raise DeepCLIException(1)
            
        pr = manager.get_pr(pr_id)
        if not pr:
            print_error(f"PR #{pr_id} not found locally.")
            raise DeepCLIException(1)
            
        status_col = Color.GREEN if pr.status == "open" else (Color.CYAN if pr.status == "merged" else Color.RED)

        print(Color.wrap(Color.CYAN, f"\n=== Pull Request #{pr.id}: {pr.title} ===\n"))
        print(f"Status:   {Color.wrap(status_col, pr.status.upper())}")
        print(f"Author:   {pr.author}")
        print(f"Flow:     {pr.head} \u2192 {pr.base}")
        if pr.github_id:
            print(f"GitHub:   #{pr.github_id} ({pr.github_url or 'N/A'})")
        if pr.requested_reviewers:
            print(f"Reviewers: {', '.join(pr.requested_reviewers)}")
        if pr.linked_issue:
            print(f"Issue:    #{pr.linked_issue}")
            
        # Part 5: Elite PR Show UX (Summary Block) - Refined Approval Counting (Part 4)
        requested_lower = [r.lower() for r in pr.requested_reviewers] if pr.requested_reviewers else []
        
        # Base approvals (assigned or all if none)
        if requested_lower:
            approvals = [a for a in pr.reviews if a.lower() in requested_lower and pr.reviews[a]["status"] == "approved"]
            other_approvals = [a for a in pr.reviews if a.lower() not in requested_lower and pr.reviews[a]["status"] == "approved"]
            
            # Fallback Logic (Part 2)
            if not approvals and other_approvals:
                approvals = other_approvals
                fallback_active = True
            else:
                fallback_active = False
        else:
            approvals = [a for a in pr.reviews if pr.reviews[a]["status"] == "approved"]
            other_approvals = []
            fallback_active = False

        changes_req = [a for a in pr.reviews if pr.reviews[a]["status"] == "changes_requested"]
        unresolved = pr.unresolved_count
        
        print(f"\n{Color.wrap(Color.BOLD, 'Review Summary:')}")
        print(f"  {Color.wrap(Color.GREEN, '✔')} Approvals: {len(approvals)}/{pr.approvals_required}")
        
        if fallback_active:
            print(f"  {Color.wrap(Color.YELLOW, '⚠')} {Color.wrap(Color.YELLOW, 'Note: using fallback approvals from non-assigned reviewers')}")
        elif other_approvals:
            print(f"  {Color.wrap(Color.YELLOW, '⚠')} {Color.wrap(Color.YELLOW, 'Reviewer mismatch: approval by non-assigned user')} ({', '.join(other_approvals)})")
            
        if changes_req:
            print(f"  {Color.wrap(Color.RED, '❌')} Changes Requested: {len(changes_req)}")
        if unresolved > 0:
            print(f"  {Color.wrap(Color.YELLOW, '⚠')} Unresolved Threads: {unresolved}")
            
        # Merge Status
        is_blocked = bool(changes_req) or (len(approvals) < pr.approvals_required) or (unresolved > 0)
        print(f"\n{Color.wrap(Color.BOLD, 'Merge Status:')}")
        if is_blocked:
            print(f"  {Color.wrap(Color.RED, 'BLOCKED')}")
            if changes_req:
                print(f"    - Requested by: {', '.join(changes_req)}")
            if len(approvals) < pr.approvals_required:
                print(f"    - Missing approvals")
            if unresolved > 0:
                print(f"    - {unresolved} unresolved threads")
        else:
            print(f"  {Color.wrap(Color.GREEN, 'READY TO MERGE')}")

        print(f"\n{'-' * 20}")
        print(f"{Color.wrap(Color.BOLD, 'Reviews:')}")
        if not pr.reviews:
            print("  No reviews yet.")
        for author, r in pr.reviews.items():
            r_col = Color.GREEN if r["status"] == "approved" else Color.RED
            icon = "✔" if r["status"] == "approved" else "❌"
            print(f"  [{author}] {Color.wrap(r_col, icon + ' ' + r['status'].upper())}")
            if r["comment"]:
                print(f"    \"{r['comment']}\"")

        print(f"\n{'-' * 20}")
        print(f"{Color.wrap(Color.BOLD, 'Threads:')}")
        if not pr.threads:
            print("  No discussion threads.")
        for t in pr.threads:
            t_stat = Color.wrap(Color.GREEN, "[RESOLVED]") if t.resolved else Color.wrap(Color.YELLOW, "[OPEN]")
            print(f"  #{t.id} {t_stat} {t.author}: \"{t.text}\"")
            for r in t.replies:
                print(f"    ↳ {r.author}: \"{r.text}\"")

        print(f"\n{'-' * 20}")
        print(f"{Color.wrap(Color.BOLD, 'Commits:')}")
        if not pr.commits:
            print("  No commits found.")
        else:
            from deep.storage.objects import read_object, Commit
            objects_dir = dg_dir / "objects"
            for sha in pr.commits:
                try:
                    obj = read_object(objects_dir, sha)
                    if isinstance(obj, Commit):
                        short_sha = sha[:7]
                        msg = obj.message.split("\n")[0]
                        print(f"  - {Color.wrap(Color.YELLOW, short_sha)} {msg}")
                except Exception:
                    print(f"  - {Color.wrap(Color.YELLOW, sha[:7])} [Object not found]")

        print(f"\n{Color.wrap(Color.BOLD, 'Description:')}")
        print(f"{pr.body or 'No description provided.'}\n")

    elif cmd == "merge":
        id_val = getattr(args, "id", None)
        if not id_val:
            print_error("Missing PR ID for merge.")
            raise DeepCLIException(1)
        
        try:
            pr_id = int(id_val)
        except ValueError:
            print_error(f"Invalid ID: {id_val}")
            raise DeepCLIException(1)
        
        pr_obj = manager.get_pr(pr_id)
        if not pr_obj:
            print_error(f"PR #{pr_id} not found.")
            raise DeepCLIException(1)

        # Safety checks
        if pr_obj.status == "merged":
            print_error(f"PR #{pr_id} is already merged.")
            return
        if pr_obj.status == "closed":
            print_error(f"PR #{pr_id} is closed.")
            return

        # Smart Merge Engine (Part 4) - Refined Approval Counting with Fallback (Part 2)
        requested_lower = [r.lower() for r in pr_obj.requested_reviewers] if pr_obj.requested_reviewers else []
        reviews_all = pr_obj.reviews
        
        all_approvals = [auth for auth, r in reviews_all.items() if r["status"] == "approved"]
        
        if requested_lower:
            effective_approvals = [a for a in all_approvals if a.lower() in requested_lower]
            # Fallback logic
            if not effective_approvals and all_approvals:
                effective_approvals = all_approvals
                print_info("⚠ Approval from non-assigned reviewer detected (Fallback active)")
        else:
            effective_approvals = all_approvals

        changes_req = [author for author, r in reviews_all.items() if r["status"] == "changes_requested"]
        unresolved = pr_obj.unresolved_count
        
        is_blocked = False
        reasons = []
        
        if changes_req:
            is_blocked = True
            reasons.append(f"{Color.wrap(Color.RED, '❌')} Changes requested by: {', '.join(changes_req)}")
        
        if len(effective_approvals) < pr_obj.approvals_required:
            is_blocked = True
            reasons.append(f"{Color.wrap(Color.RED, '❌')} Approvals: {len(effective_approvals)}/{pr_obj.approvals_required}")
            if requested_lower:
                reasons.append(f"  {Color.wrap(Color.YELLOW, '⚠')} Assigned reviewers: {', '.join(pr_obj.requested_reviewers)}")
                if all_approvals:
                    reasons.append(f"  {Color.wrap(Color.YELLOW, '⚠')} Approvals received from: {', '.join(all_approvals)}")
            
        if unresolved > 0:
            is_blocked = True
            reasons.append(f"⚠ {unresolved} unresolved threads")
            
        if is_blocked:
            print(f"\n{Color.wrap(Color.BOLD, 'Merge Status: ')}{Color.wrap(Color.RED, 'BLOCKED')}")
            print("\nReasons:")
            for r in reasons:
                print(f"  {r}")
            print_info(f"\nRun: {Color.wrap(Color.YELLOW, 'deep pr review ' + str(pr_id))} to resolve")
            return

        print_info(f"Merging PR #{pr_id}...")
        print_info(f"base: {pr_obj.base}")
        print_info(f"head: {pr_obj.head}")

        try:
            # 1. Import commands
            from deep.commands.checkout_cmd import run as checkout_run
            from deep.commands.merge_cmd import run as merge_run
            from deep.core.state import validate_repo_state

            # 2. Checkout base branch
            print_info(f"Stepping into base branch: {pr_obj.base}")
            checkout_args = argparse.Namespace(target=pr_obj.base, branch=False, force=False)
            checkout_run(checkout_args)

            # 3. Perform real merge
            print_info(f"Executing repository merge from {pr_obj.head}...")
            merge_args = argparse.Namespace(branch=pr_obj.head, no_ff=False, message=None)
            merge_run(merge_args)

            # 4. State Validation
            validate_repo_state(repo_root)

            # 5. Update PR metadata only on success
            pr_obj.status = "merged"
            pr_obj.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            pr_obj.merged_at = pr_obj.updated_at
            manager.save_pr(pr_obj)

            # Auto Close Issue on Merge (Part 3)
            if pr_obj.linked_issue:
                from deep.core.issue import IssueManager
                im = IssueManager(dg_dir)
                issue = im.get_issue(pr_obj.linked_issue)
                if issue:
                    issue.status = "closed"
                    im.add_timeline_event(issue.id, "closed_by_pr", pr=pr_obj.id)
                    im.save_issue(issue)
                    print_success(f"\u2714 Linked Issue #{issue.id} closed automatically")

            print_success(f"\n\u2714 Merge completed successfully")
            print_success(f"\u2714 PR #{pr_id} marked as merged")

        except Exception as e:
            print_error(f"\nMerge failed: {e}")
            print_error("PR status remains 'open'. No metadata updated.")
            raise DeepCLIException(1)

    elif cmd == "close":
        id_val = getattr(args, "id", None)
        if not id_val:
            print_error("Missing PR ID for close.")
            raise DeepCLIException(1)
        
        try:
            pr_id = int(id_val)
            pr = manager.close_pr(pr_id)
            print_success(f"Pull Request #{pr_id} is now closed.")
        except Exception as e:
            print_error(f"Error: {e}")
            raise DeepCLIException(1)

    elif cmd == "comment":
        id_val = getattr(args, "id", None)
        if not id_val:
            print_error("Missing PR ID.")
            raise DeepCLIException(1)
            
        try:
            pr_id = int(id_val)
        except ValueError:
            print_error(f"Invalid ID: {id_val}")
            raise DeepCLIException(1)

        print(f"\n--- Start Discussion Thread (PR #{pr_id}) ---")
        text = input("Message: ").strip()
        if not text:
            print_error("Comment cannot be empty.")
            return
            
        try:
            thread = manager.add_thread(pr_id, author_name, text)
            print_success(f"✔ Comment added (Thread #{thread.id})")
        except Exception as e:
            print_error(str(e))
            raise DeepCLIException(1)

    elif cmd == "reply":
        id_val = getattr(args, "id", None)
        thread_id = getattr(args, "thread", None)
        if not id_val or not thread_id:
            print_error("Usage: deep pr reply <pr_id> <thread_id>")
            raise DeepCLIException(1)
            
        try:
            pr_id = int(id_val)
            tid = int(thread_id)
        except ValueError:
            print_error("IDs must be numerical.")
            raise DeepCLIException(1)

        print(f"\n--- Reply to Thread #{tid} (PR #{pr_id}) ---")
        text = input("Reply: ").strip()
        if not text:
            print_error("Reply cannot be empty.")
            return
            
        try:
            manager.add_reply(pr_id, tid, author_name, text)
            print_success(f"✔ Reply added to Thread #{tid}")
        except Exception as e:
            print_error(str(e))
            raise DeepCLIException(1)

    elif cmd == "resolve":
        id_val = getattr(args, "id", None)
        thread_id = getattr(args, "thread", None)
        if not id_val or not thread_id:
            print_error("Usage: deep pr resolve <pr_id> <thread_id>")
            raise DeepCLIException(1)
            
        try:
            manager.resolve_thread(int(id_val), int(thread_id))
            print_success(f"✔ Thread #{thread_id} resolved")
        except Exception as e:
            print_error(str(e))
            raise DeepCLIException(1)

    elif cmd == "review":
        id_val = getattr(args, "id", None)
        if not id_val:
            print_error("Usage: deep pr review <id>")
            raise DeepCLIException(1)
            
        try:
            pr_id = int(id_val)
            pr = manager.get_pr(pr_id)
        except ValueError:
            print_error(f"Invalid ID: {id_val}")
            raise DeepCLIException(1)

        if not pr:
            print_error(f"PR #{pr_id} not found.")
            raise DeepCLIException(1)
            
        print(f"\n{Color.wrap(Color.BOLD, f'--- Review PR #{pr.id}: {pr.title} ---')}\n")
        
        # UX Boost: Review Command UX (Part 4)
        if pr.requested_reviewers and author_name.lower() not in [r.lower() for r in pr.requested_reviewers]:
            print(f"{Color.wrap(Color.YELLOW, '⚠ YOU ARE NOT AN ASSIGNED REVIEWER FOR THIS PR.')}")
            anyway = input("Submit review anyway? [y/N]: ").strip().lower()
            if anyway != 'y': return

        current_review = pr.reviews.get(author_name)
        if current_review:
            print(f"{Color.wrap(Color.YELLOW, 'You already reviewed this PR:')} {current_review['status'].upper()}")
            update = input("Update your review? [y/N]: ").strip().lower()
            if update != 'y': return

        # Smart Review UX (Part 6) - suggestions
        if not pr.reviews and pr.unresolved_count == 0 and len(pr.commits) < 5:
            print_info("Suggestion: This looks like a small, clean PR. Consider APPROVING.")
        elif len(pr.commits) > 20 and not pr.body:
            print_info("Suggestion: Large PR with no description. Consider CHANGES_REQUESTED.")

        print("\nSelect Action:")
        print(f"1. {Color.wrap(Color.GREEN, 'Approve')}")
        print(f"2. {Color.wrap(Color.RED, 'Request Changes')}")
        print(f"3. {Color.wrap(Color.YELLOW, 'Comment Only')}")
        
        choice = input("\nChoice [1-3]: ").strip()
        status = "commented"
        if choice == "1": status = "approved"
        elif choice == "2": status = "changes_requested"
        elif choice == "3": status = "commented"
        else:
            print_error("Invalid choice.")
            return

        comment = input("Review Comment (optional): ").strip()
        if status == "changes_requested" and not comment:
            print_error("Comment required for requested changes.")
            return

        try:
            manager.add_review(pr.id, author_name, status, comment)
            print_success(f"✔ Review submitted as {status.upper()}")
        except Exception as e:
            print_error(f"Failed to submit review: {e}")
            raise DeepCLIException(1)

    elif cmd == "sync":
        gh_repo = net.get_github_remote(repo_root)
        token = net.get_token()
        
        if not gh_repo or not token:
            print_error("Sync requires a GitHub remote and GH_TOKEN.")
            raise DeepCLIException(1)
            
        print_info(f"Syncing local PRs with {gh_repo}...")
        prs = manager.list_prs()
        synced_count = 0
        for pr in prs:
            if pr.status == "open" and not pr.github_id:
                path = f"{gh_repo}/pulls"
                res = net.api_request(path, method="POST", data={
                    "title": pr.title,
                    "body": pr.body,
                    "head": pr.head,
                    "base": pr.base
                }, verbose=verbose)
                
                if res and isinstance(res, dict) and "number" in res:
                    pr.github_id = res["number"]
                    pr.github_url = res.get("html_url")
                    manager.save_pr(pr)
                    synced_count += 1
        print_success(f"Successfully synced {synced_count} PRs.")

"""
Deep Plugin Example: Slack Notifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Sends a notification to a Slack webhook whenever a new commit is created.
"""

import json
import urllib.request
import os

def on_commit(commit_sha, message):
    """
    Hook called by Deep VCS after a successful commit.
    This is an example of a synchronous hook.
    """
    web_hook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not web_hook_url:
        print("Slack Notifier: SLACK_WEBHOOK_URL not set, skipping.")
        return

    payload = {
        "text": f"🚀 *New Commit in Deep VCS*:\n`{commit_sha[:7]}`: {message}"
    }

    try:
        req = urllib.request.Request(
            web_hook_url, 
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req) as res:
            if res.status == 200:
                print("Slack Notifier: Message sent successfully.")
    except Exception as e:
        print(f"Slack Notifier Error: {e}")

# In a real plugin, you would register this with the PluginManager
# discovery mechanism (e.g., via a standard entry point or file naming).
def register(plugin_manager):
    plugin_manager.register_hook("post-commit", on_commit)

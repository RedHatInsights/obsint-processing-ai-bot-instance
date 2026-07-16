#!/usr/bin/env python3
"""Pre-flight: check for failing MintMaker/Konflux PRs.

Reads the daily open-prs.csv report from processing-tools repo
(generated at 4AM UTC by GitHub Actions) and filters for bot PRs.
Self-throttles to run once every 8 hours.

Cleanup (zero tokens):
  - Queries memory-server for tracked mintmaker:* entries
  - Checks each tracked PR's state via gh CLI
  - Archives tasks and removes memory entries for merged/closed PRs

Exit conditions:
  - Last run < 8 hours ago -> skip (throttled)
  - Report fetch fails -> skip
  - No bot PRs in report -> skip (after cleanup)
  - Bot PRs found -> start (agent triages)
"""

import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

THROTTLE_HOURS = 8
STATE_FILE = Path(os.environ.get("BOT_DATA_DIR", "data")) / "mintmaker-last-run.json"

REPORT_REPO = "RedHatInsights/processing-tools"
REPORT_PATH = "open_mr_pr/github/open-prs.csv"

BOT_AUTHORS = {"app/red-hat-konflux", "app/dependabot"}

MEMORY_SERVER = os.environ.get("MEMORY_SERVER_URL", "http://devbot-memory-server:8080")
INSTANCE_ID = os.environ.get("BOT_INSTANCE_ID", "")


def _is_throttled():
    if not STATE_FILE.exists():
        return False
    try:
        state = json.loads(STATE_FILE.read_text())
        last_run = state.get("last_run", 0)
        return (time.time() - last_run) < (THROTTLE_HOURS * 3600)
    except (json.JSONDecodeError, OSError):
        return False


def _save_run_time():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"last_run": time.time()}))


def _fetch_csv():
    """Fetch the daily PR CSV report from processing-tools repo."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{REPORT_REPO}/contents/{REPORT_PATH}",
             "-H", "Accept: application/vnd.github.raw+json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"WARN: failed to fetch CSV: {result.stderr[:200]}", file=sys.stderr)
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        print("WARN: CSV fetch timed out", file=sys.stderr)
        return None


def _parse_bot_prs(csv_text):
    """Parse CSV for all open bot PRs (failing and passing)."""
    bot_prs = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        author = row.get("author", "")
        if author in BOT_AUTHORS:
            bot_prs.append(row)
    return bot_prs


def _format_pr(pr):
    lines = [f"{pr['repo']}#{pr['pr_id']} by {pr['author']}"]
    lines.append(f"  title: {pr['title']}")
    lines.append(f"  url: {pr['url']}")
    lines.append(f"  created: {pr['date_created'][:10]}")
    lines.append(f"  ci_status: {pr.get('ci_status', 'unknown')}")
    return "\n".join(lines)


# --- Cleanup: zero-token task/memory housekeeping ---


def _fetch_tracked_mintmaker_memories():
    """Fetch memory entries tagged mintmaker:* from the memory server.

    Returns list of {id, tag, repo, pr_number} for each tracked PR.
    """
    tracked = []
    try:
        params = urllib.parse.urlencode({"tag": "mintmaker", "limit": "100"})
        url = f"{MEMORY_SERVER}/api/memories?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        for item in data.get("items", []):
            for tag in item.get("tags", []):
                if tag.startswith("mintmaker:"):
                    # tag format: mintmaker:<repo>#<pr>
                    rest = tag[len("mintmaker:"):]
                    if "#" in rest:
                        repo, pr_num = rest.rsplit("#", 1)
                        tracked.append({
                            "id": item["id"],
                            "tag": tag,
                            "repo": repo,
                            "pr_number": pr_num,
                        })
                    break
    except Exception as e:
        print(f"WARN: could not fetch tracked mintmaker memories: {e}", file=sys.stderr)
    return tracked


def _check_pr_state(repo, pr_number):
    """Check if a PR is still open via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_number,
             "--repo", f"RedHatInsights/{repo}",
             "--json", "state", "-q", ".state"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except subprocess.TimeoutExpired:
        pass
    return None


def _archive_task(external_key):
    """Archive a task via the memory server REST API (soft delete)."""
    try:
        encoded_key = urllib.parse.quote(external_key, safe="")
        url = f"{MEMORY_SERVER}/api/tasks/{encoded_key}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"WARN: could not archive task {external_key}: {e}", file=sys.stderr)
        return False


def _delete_memory(memory_id):
    """Delete a memory entry via the memory server REST API."""
    try:
        url = f"{MEMORY_SERVER}/api/memories/{memory_id}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"WARN: could not delete memory {memory_id}: {e}", file=sys.stderr)
        return False


def cleanup_merged_prs():
    """Check tracked PRs and clean up any that have been merged or closed.

    Runs at zero token cost — direct HTTP to memory server + gh CLI.
    Returns count of cleaned up entries.
    """
    tracked = _fetch_tracked_mintmaker_memories()
    if not tracked:
        return 0

    cleaned = 0
    for entry in tracked:
        state = _check_pr_state(entry["repo"], entry["pr_number"])
        if state in ("MERGED", "CLOSED"):
            ext_key = f"mintmaker:{entry['repo']}#{entry['pr_number']}"
            _archive_task(ext_key)
            _delete_memory(entry["id"])
            print(f"  Cleaned up {ext_key} (state: {state})", file=sys.stderr)
            cleaned += 1

    return cleaned


def main():
    # Cleanup runs every cycle (hourly) — task slots are limited
    print("Cleaning up tracked MintMaker PRs...", file=sys.stderr)
    cleaned = cleanup_merged_prs()
    if cleaned:
        print(f"Cleaned up {cleaned} merged/closed PR(s)", file=sys.stderr)

    # CSV fetch + triage is throttled to every 8h
    if _is_throttled():
        print(json.dumps({"status": "skip", "content": "Mintmaker scan throttled (last run < 8h ago)"}))
        return

    print("Fetching daily PR CSV from processing-tools...", file=sys.stderr)
    csv_text = _fetch_csv()

    if csv_text is None:
        _save_run_time()
        print(json.dumps({"status": "skip", "content": "Could not fetch PR CSV report"}))
        return

    bot_prs = _parse_bot_prs(csv_text)
    _save_run_time()

    if not bot_prs:
        print(json.dumps({"status": "skip", "content": "No open MintMaker/Konflux PRs in daily report"}))
        return

    failing = [pr for pr in bot_prs if pr.get("ci_status") == "failed"]
    passing = [pr for pr in bot_prs if pr.get("ci_status") != "failed"]

    lines = [f"## MintMaker PR Triage — {len(bot_prs)} open PR(s) ({len(failing)} failing, {len(passing)} passing)", ""]
    lines.append("Source: processing-tools daily CSV report (generated 4AM UTC)")

    if failing:
        lines.append("")
        lines.append("### Failing CI")
        for pr in failing:
            lines.append(_format_pr(pr))
            lines.append("")

    if passing:
        lines.append("### Passing CI (may need review or already merged)")
        for pr in passing:
            lines.append(_format_pr(pr))
            lines.append("")

    print(f"Found {len(bot_prs)} bot PRs ({len(failing)} failing, {len(passing)} passing)", file=sys.stderr)
    print(json.dumps({"status": "start", "content": "\n".join(lines)}))


if __name__ == "__main__":
    main()

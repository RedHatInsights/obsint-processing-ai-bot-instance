#!/usr/bin/env python3
"""Pre-flight: check for failing MintMaker/Konflux PRs.

Reads the daily open-prs.csv report from processing-tools repo
(generated at 4AM UTC by GitHub Actions) and filters for failing bot PRs.
Self-throttles to run once every 8 hours.

Exit conditions:
  - Last run < 8 hours ago -> skip (throttled)
  - Report fetch fails -> skip
  - No failing bot PRs in report -> skip
  - Failing bot PRs found -> start (agent triages)
"""

import csv
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

THROTTLE_HOURS = 8
STATE_FILE = Path(os.environ.get("BOT_DATA_DIR", "data")) / "mintmaker-last-run.json"

REPORT_REPO = "RedHatInsights/processing-tools"
REPORT_PATH = "open_mr_pr/github/open-prs.csv"

BOT_AUTHORS = {"app/red-hat-konflux", "app/dependabot"}


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
    lines.append(f"  status: {pr['draft_status']}")
    return "\n".join(lines)


def main():
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

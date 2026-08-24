#!/usr/bin/env python3
"""Backlog grooming preflight — scan for ungroomed Jira backlog tickets.

Returns start if ungroomed tickets exist, skip otherwise.
Saves tokens by fetching ticket data here instead of in the Claude session.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from common import INSTANCE_ID, output_result
from jira_mcp import jira_call, jira_cleanup

BOT_LABEL = os.environ.get("BOT_LABEL", "")
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
GROOMED_MARKER = SCRIPT_DIR / "data" / "groomed-weeks.json"
NOT_STARTED_STATUSES = ("New", "Backlog", "Refinement", "To Do")
GROOMING_DAY = 2  # Wednesday (Monday=0)


def _search_backlog():
    if not BOT_LABEL:
        print("ERR: BOT_LABEL not set", file=sys.stderr)
        return []

    # Basic filters — more granular filtering will be added in CCXDEV-16532
    status_list = ", ".join(f'"{s}"' for s in NOT_STARTED_STATUSES)
    jql = (
        f"project = CCXDEV "
        f"AND labels IN (CCX-PROCESSING, OBSINT-PROCESSING) "
        f"AND status IN ({status_list}) "
        f"AND labels != ai-groomed "
        f"AND assignee is EMPTY "
        f"AND sprint is EMPTY "
        f"AND type NOT IN (Epic) "
        f"ORDER BY Rank ASC"
    )

    data = jira_call(
        "jira_search",
        {
            "jql": jql,
            "limit": 10,
            "fields": "summary,status,labels,priority,description,comment,issuetype,created,updated,parent,customfield_12311140,fixVersions",
        },
    )
    if not data:
        return []
    return data if isinstance(data, list) else data.get("issues", [])


def _format_ticket(issue):
    fields = issue.get("fields") or issue
    status = fields.get("status", {})
    priority = fields.get("priority", {})
    issue_type = fields.get("issuetype") or fields.get("issue_type") or {}
    labels = fields.get("labels", [])
    created = fields.get("created", "")[:10]
    updated = fields.get("updated", "")[:10]

    lines = [f"{issue['key']} [{status.get('name', '?')}] priority={priority.get('name', '?')} type={issue_type.get('name', '?')}"]
    lines.append(f"  title: {fields.get('summary', '')}")
    lines.append(f"  created: {created} | updated: {updated}")

    parent = fields.get("parent")
    if parent:
        p_status = parent.get("fields", {}).get("status", {}).get("name", "?")
        lines.append(f"  epic: {parent.get('key', '?')} [{p_status}] — {parent.get('fields', {}).get('summary', '')}")

    fix_versions = fields.get("fixVersions") or []
    if fix_versions:
        lines.append(f"  fixVersions: {', '.join(v.get('name', '?') for v in fix_versions)}")

    target_quarter = fields.get("customfield_12311140")
    if target_quarter:
        lines.append(f"  targetQuarter: {target_quarter}")

    repo_labels = [l for l in labels if l.startswith("repo:")]
    other_labels = [l for l in labels if not l.startswith("repo:") and l != BOT_LABEL]
    if repo_labels:
        lines.append(f"  repos: {','.join(repo_labels)}")
    if other_labels:
        lines.append(f"  labels: {','.join(other_labels)}")

    desc = fields.get("description") or ""
    if desc and str(desc).strip() not in ("", "null", "None"):
        desc_text = str(desc).strip()
        if len(desc_text) > 500:
            desc_text = desc_text[:500] + "..."
        lines.append("  description:")
        for dl in desc_text.split("\n")[:10]:
            lines.append(f"    {dl}")
    else:
        lines.append("  description: (empty)")

    comment_data = fields.get("comment", {})
    comments = (comment_data.get("comments") or [])[-3:] if isinstance(comment_data, dict) else []
    if comments:
        lines.append(f"  recent_comments ({len(comments)}):")
        for c in comments:
            author = c.get("author", {}).get("displayName", "?")
            t = c.get("created", "")[:16]
            body = c.get("body", "")
            if len(str(body)) > 200:
                body = str(body)[:200] + "..."
            lines.append(f"    [{t}] {author}: {body}")

    return "\n".join(lines)


def _already_groomed_this_week():
    """Check if we already groomed this ISO week (limits to once per week)."""
    week_key = datetime.utcnow().strftime("%G-W%V")
    try:
        if GROOMED_MARKER.exists():
            done = json.loads(GROOMED_MARKER.read_text())
            if week_key in done:
                return True
    except Exception:
        pass
    return False


def _mark_groomed():
    """Mark the current ISO week as groomed."""
    week_key = datetime.utcnow().strftime("%G-W%V")
    done = {}
    try:
        if GROOMED_MARKER.exists():
            done = json.loads(GROOMED_MARKER.read_text())
    except Exception:
        pass
    done[week_key] = True
    GROOMED_MARKER.parent.mkdir(parents=True, exist_ok=True)
    GROOMED_MARKER.write_text(json.dumps(done))


def main():
    if not INSTANCE_ID:
        output_result("error", "BOT_INSTANCE_ID not set")
        return

    if datetime.utcnow().weekday() != GROOMING_DAY:
        print("Not Wednesday — skipping backlog grooming", file=sys.stderr)
        output_result("skip", "Backlog grooming only runs on Wednesdays")
        return

    if _already_groomed_this_week():
        print("Already groomed this week — skipping", file=sys.stderr)
        output_result("skip", "Already groomed this week")
        return

    print(f"Scanning backlog for label={BOT_LABEL}...", file=sys.stderr)
    tickets = _search_backlog()
    jira_cleanup()

    if not tickets:
        output_result("skip", "No ungroomed backlog tickets")
        return

    _mark_groomed()

    lines = [f"## Backlog Grooming — {len(tickets)} ticket(s) to assess", ""]
    for t in tickets:
        lines.append(_format_ticket(t))
        lines.append("")

    print(f"Found {len(tickets)} ungroomed tickets", file=sys.stderr)
    output_result("start", "\n".join(lines))


if __name__ == "__main__":
    main()

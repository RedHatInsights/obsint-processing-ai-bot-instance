#!/usr/bin/env python3
"""Backlog grooming preflight — scan for ungroomed Jira backlog tickets.

Returns start if ungroomed tickets exist, skip otherwise.
Saves tokens by fetching ticket data here instead of in the Claude session.
"""

import os
import sys

from common import INSTANCE_ID, output_result
from jira_mcp import jira_call, jira_cleanup

BOT_LABEL = os.environ.get("BOT_LABEL", "")
NOT_STARTED_STATUSES = ("New", "Backlog", "Refinement", "To Do")


def _search_backlog():
    if not BOT_LABEL:
        print("ERR: BOT_LABEL not set", file=sys.stderr)
        return []

    status_list = ", ".join(f'"{s}"' for s in NOT_STARTED_STATUSES)
    jql = (
        f"labels = {BOT_LABEL} "
        f"AND status IN ({status_list}) "
        f"AND labels != ai-groomed "
        f"AND assignee is EMPTY "
        f"AND sprint is EMPTY "
        f"AND type NOT IN (Epic) "
        f"ORDER BY created ASC"
    )

    data = jira_call(
        "jira_search",
        {
            "jql": jql,
            "limit": 10,
            "fields": "summary,status,labels,priority,description,comment,issuetype,created,updated",
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


def main():
    if not INSTANCE_ID:
        output_result("error", "BOT_INSTANCE_ID not set")
        return

    print(f"Scanning backlog for label={BOT_LABEL}...", file=sys.stderr)
    tickets = _search_backlog()
    jira_cleanup()

    if not tickets:
        output_result("skip", "No ungroomed backlog tickets")
        return

    lines = [f"## Backlog Grooming — {len(tickets)} ticket(s) to assess", ""]
    for t in tickets:
        lines.append(_format_ticket(t))
        lines.append("")

    print(f"Found {len(tickets)} ungroomed tickets", file=sys.stderr)
    output_result("start", "\n".join(lines))


if __name__ == "__main__":
    main()

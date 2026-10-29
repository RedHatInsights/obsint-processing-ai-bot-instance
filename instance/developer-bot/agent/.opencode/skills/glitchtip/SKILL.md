---
name: glitchtip
description: Query GlitchTip issue details, stacktraces, event history, and resolution through the configured authenticated proxy.
---

# glitchtip

Use this skill for all GlitchTip API access. Its committed Python helper
uses `urllib` against the selected executor host on port 8448
(the GlitchTip reverse proxy — note 8447 is the
separate git-auth forward proxy, do not use it), which is in `NO_PROXY`
so the request goes direct. The proxy adds `Authorization: Bearer <token>` —
**never pass or log a token.**

## Environment

- `EXECUTOR_ADDR` — selects the team proxy; the helper uses its hostname with
  port 8448. OpenCode preserves this variable. An invalid address is an error.
- `GLITCHTIP_API_URL` — optional explicit override for local use. When neither
  variable is set, the legacy default is `http://devbot-proxy:8448`.
- The organization defaults to `ccx`; `GLITCHTIP_ORG` remains an optional local
  override. Neither local override is needed in the deployed OpenCode profile.

## Commands

```bash
# List unresolved issues for the org (optionally filter by project)
python3 "/home/botuser/app/data/remote-config/${BOT_CONFIG_PATH}/agent/.opencode/skills/glitchtip/glitchtip.py" list --limit 25
python3 "/home/botuser/app/data/remote-config/${BOT_CONFIG_PATH}/agent/.opencode/skills/glitchtip/glitchtip.py" list --project <project-id> --query "is:unresolved"

# Single issue metadata
python3 "/home/botuser/app/data/remote-config/${BOT_CONFIG_PATH}/agent/.opencode/skills/glitchtip/glitchtip.py" issue <issue-id>

# Latest event for an issue — contains the full stacktrace
python3 "/home/botuser/app/data/remote-config/${BOT_CONFIG_PATH}/agent/.opencode/skills/glitchtip/glitchtip.py" latest <issue-id>

# Recent events for an issue
python3 "/home/botuser/app/data/remote-config/${BOT_CONFIG_PATH}/agent/.opencode/skills/glitchtip/glitchtip.py" events <issue-id> --limit 5

# Mark an issue resolved (only after the fix is verified in production)
python3 "/home/botuser/app/data/remote-config/${BOT_CONFIG_PATH}/agent/.opencode/skills/glitchtip/glitchtip.py" resolve <issue-id>
```

All commands print pretty JSON to stdout. On error the script prints the
configuration, HTTP, or connection error to stderr and exits non-zero. Report
the configuration or proxy blocker; do not request or supply credentials.

## Extracting the issue ID

GlitchTip URLs in Jira tickets look like:

- `https://glitchtip.devshift.net/ccx/issues/<issue-id>` → the numeric `<issue-id>`.
- `https://glitchtip.devshift.net/ccx/issues?project=<project-id>` → use
  `list --project <project-id>` and match the error from the ticket.

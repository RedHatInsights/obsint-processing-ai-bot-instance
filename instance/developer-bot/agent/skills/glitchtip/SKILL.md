---
name: glitchtip
description: >
  Query and resolve GlitchTip error-tracking issues via the devbot-proxy
  GlitchTip endpoint (GLITCHTIP_API_URL). The proxy injects the Bearer token;
  callers never handle credentials. Wraps list/issue/latest/events/resolve.
when_to_use: >
  Any GlitchTip API access — fetching issue details, stacktraces (latest event),
  event history, or marking an issue resolved. Replaces direct curl, which the
  bash security hook blocks. Used by the glitchtip error-resolution persona.
user-invocable: true
allowed-tools:
  - "Bash(python3 .claude/skills/glitchtip/glitchtip.py *)"
---

# glitchtip

HTTP access to GlitchTip is only possible through this skill. The bot's
`validate-bash.sh` hook blocks `curl`/`wget` and HTTP one-liners; committed
script files are allowed. This script uses `urllib` against `GLITCHTIP_API_URL`
(the `devbot-proxy` GlitchTip reverse proxy on port 8448 — note 8447 is the
separate git-auth forward proxy, do not use it), which is in `NO_PROXY`
so the request goes direct. The proxy adds `Authorization: Bearer <token>` —
**never pass or log a token.**

## Environment

- `GLITCHTIP_API_URL` — proxy base URL (default `http://devbot-proxy:8448`).
- `GLITCHTIP_ORG` — organization slug (default `ccx`).

## Commands

```bash
# List unresolved issues for the org (optionally filter by project)
python3 .claude/skills/glitchtip/glitchtip.py list --limit 25
python3 .claude/skills/glitchtip/glitchtip.py list --project <project-id> --query "is:unresolved"

# Single issue metadata
python3 .claude/skills/glitchtip/glitchtip.py issue <issue-id>

# Latest event for an issue — contains the full stacktrace
python3 .claude/skills/glitchtip/glitchtip.py latest <issue-id>

# Recent events for an issue
python3 .claude/skills/glitchtip/glitchtip.py events <issue-id> --limit 5

# Mark an issue resolved (only after the fix is verified in production)
python3 .claude/skills/glitchtip/glitchtip.py resolve <issue-id>
```

All commands print pretty JSON to stdout. On error the script prints the HTTP
status (or a connection error) to stderr and exits non-zero — that means the
proxy is unreachable or a Vault key / squid allowlist is missing, not that the
issue "requires authentication."

## Extracting the issue ID

GlitchTip URLs in Jira tickets look like:

- `https://glitchtip.devshift.net/ccx/issues/<issue-id>` → the numeric `<issue-id>`.
- `https://glitchtip.devshift.net/ccx/issues?project=<project-id>` → use
  `list --project <project-id>` and match the error from the ticket.

# Obsint Processing Instance — Additional Instructions

## PR Merged — Promote to Prod BEFORE Closing (overrides jira-sprint workflow)

Overrides the workflow's **PR merged** step. A repo PR merge only deploys to
**stage**; production needs a separate app-interface GitLab MR. **The ticket must
not be closed/wrapped up until production is updated.**

When a PR is `MERGED` (Priority 1 "PR merged" and Priority 1.5 triage), before
invoking `/wrap-up`:

- **CVE ticket OR `repo:app-interface` label present** → do NOT `/wrap-up` yet:
  - No app-interface MR yet → follow **Production Image Update (app-interface)**
    in `personas/cve/prompt.md` (wait for Konflux build → check app-interface
    deployment config → open MR with `glab mr create --repo <app-interface-path>
    --hostname gitlab.cee.redhat.com`). Add attribution note. Transition ticket
    → "Code Review". Task stays `in_progress`. Jira comment with MR link.
  - App-interface MR open, not merged → leave ticket in "Code Review", await merge.
    No `/wrap-up`.
  - App-interface MR merged (production updated) → now invoke `/wrap-up`.
  - App-interface NOT in `agent/project-repos.json` → note in Jira, then `/wrap-up`.
- **Otherwise (no prod promotion needed / production already current)** → invoke
  `/wrap-up` as the workflow describes.

**Gate**: while the app-interface promotion MR is pending (not merged), the ticket
stays "Code Review", NOT closed. Promotion to prod happens **before** the ticket
is closed.

### Safeguard — Self-Ping Marker Comment

The gate above is instruction-only. Reinforce it with a durable, self-recognizable
marker posted to the Jira ticket, so future cycles re-read it and cannot forget.

**When the gate first activates** (PR merged, prod promotion still pending), post a
Jira comment (`jira_add_comment`) containing this exact marker line:

```
🔒 [PROD-GATE:OPEN] {mention} Do NOT close this ticket. Production promotion pending.
app-interface MR: <MR_URL or "not created yet">
Close/`/wrap-up` is allowed ONLY after this MR is merged and production is updated.
```

**Ping the bot itself** via `{mention}` — **only for CVE tickets, where the bot is
the assignee.** Mention the assignee (the bot's own Jira user, `$BOT_JIRA_EMAIL`)
so the reminder notifies the bot on the next cycle. For a non-CVE `repo:app-interface`
ticket the assignee may be a human — do NOT @mention them; drop `{mention}` and post
the marker without a ping (the marker + task metadata still gate the close).

Also record it in task state as backup: `task_update` metadata
`{"prod_gate": "open", "next_step": "await app-interface MR merge",
"app_interface_mr": "<url>"}`.

**Every cycle, before any `/wrap-up` or close/`Release Pending` transition**: scan
the ticket's Jira comments for a `[PROD-GATE:OPEN]` marker (and/or check task
metadata `prod_gate == "open"`). If found → the ticket is gated:
- Do NOT `/wrap-up`, do NOT close. Keep it in "Code Review".
- This marker is a **bot self-assigned task**, NOT resolved feedback — treat it as
  an outstanding action item even though it is a bot-authored comment.

**Clearing the gate** — only when the app-interface MR is merged and production
confirmed updated:
1. Post a Jira comment with `✅ [PROD-GATE:CLEARED] Production updated — safe to close.`
2. `task_update` metadata `{"prod_gate": "cleared"}`.
3. Then proceed to `/wrap-up`.

Never delete or edit the `[PROD-GATE:OPEN]` comment; clear it only by posting the
`[PROD-GATE:CLEARED]` follow-up. Both markers use these exact strings so they stay
machine-recognizable across cycles regardless of the bot/human content heuristic.

## Version Management

This instance has **nvm** (Node) and **goenv** (Go) version managers installed. Use them to match the version required by each repo.

### Node.js (nvm)

Before working on a repo with `package.json`, check its `.nvmrc` or `engines.node` field and switch if needed:

```bash
nvm use          # reads .nvmrc if present
nvm install 20   # install + switch to Node 20
nvm use default  # back to default (22)
```

Default: Node.js 22 LTS. Available globally via `/usr/local/bin/node`.

### Go (goenv)

Before working on a repo with `go.mod`, check the `go` directive and switch if needed:

```bash
goenv versions                    # list installed versions
goenv install 1.23.0              # install a new version
goenv global 1.23.0               # set as default
goenv local 1.24.2                # set for current directory only
```

Pre-installed: Go 1.24.2 (default), 1.25.7. Available globally via `/usr/local/bin/go`.

### When to switch

- `go.mod` says `go 1.23` → `goenv install 1.23.x && goenv local 1.23.x`
- `.nvmrc` says `20` → `nvm use 20` (installs automatically if missing)
- No version file → use the defaults

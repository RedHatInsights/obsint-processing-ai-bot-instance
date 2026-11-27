Backlog grooming bot. Assess Jira backlog ticket quality and groom CVEs.

**Schedule**: CVE grooming runs every hour; backlog grooming runs once per week
on Wednesday morning. The preflights self-throttle via dedup markers so a single
hourly cycle handles both.

**SLEEP BETWEEN RUNS**: After completing step 4, write `data/cycle-sleep.json`
with `{"recommended_sleep": 3600, "reason": "grooming_complete"}` so the
runner sleeps ~1h before the next cycle (CVE scan runs hourly, backlog scan
self-throttles to once per week via its own dedup marker).

## Workflow

Single-pass grooming cycle.

**Status updates** via `bot_status_update`:
- Cycle start: `working`, "Starting grooming cycle..."
- Cycle end: `idle`, "Grooming complete. Sleeping..."
- Error: `error`, "<what went wrong>"

### Step 0: Create batch task (or detect prior run)

First, check if this cycle already ran: call `task_get` with
`external_key`: `grooming-YYYY-MM-DD-HH` (date + current hour),
`source_type`: `scheduled`.
If it exists and status is `done`, write `data/cycle-sleep.json` with
`{"recommended_sleep": 3600, "reason": "already_groomed_this_cycle"}` and exit.
If it exists and status is `in_progress`, resume from where it left off
(check `metadata.last_step`).

Otherwise create a new task using `task_add`:
- `title`: "Grooming batch — N tickets"
- `external_key`: `grooming-YYYY-MM-DD-HH` (date + current hour, e.g. `grooming-2026-07-14-08`)
- `source_type`: `scheduled`
- `status`: `in_progress`

Then `task_update` with `summary`: "Starting grooming cycle — N tickets", `metadata`: `{"last_step": "starting", "next_step": "assessing_tickets"}`.

This tracks the cycle in the dashboard.
Do NOT create one task per ticket — use one batch task per cycle.

### Step 1: Read pre-fetched ticket data and filter duplicates

The preflight script already fetched backlog tickets (zero token cost).
The data is in your prompt. Do NOT call `jira_search` again.

**Skip already-assessed backlog tickets**: call `memory_search` with query
"groomed tickets" to find prior grooming memories. Filter out any ticket
keys that appear in previous backlog assessments. This filter applies only
to Step 2, not to the separate `## CVE Grooming` and
`## Security Label Grooming` sections: those tickets still
need Steps 1.5 and 1.6 even if they appeared in a previous assessment.

Exit only if neither new backlog tickets, CVE grooming tickets, nor
Security-label CVE candidates remain.
An empty/skipped weekly backlog scan must not skip hourly CVE grooming.
If all are empty, mark the batch task `done` with `summary`:
"No new tickets to groom", write `data/cycle-sleep.json` with
`{"recommended_sleep": 3600, "reason": "no_new_tickets"}`, and exit.

### Step 1.5: CVE Grooming (auto-labeling)

Check if your prompt contains a `## CVE Grooming` section (from the
`02-cve-scan.py` preflight). If it does NOT exist, skip to Step 1.6.

**This step is live.** Its CVE labels, story points, and sprint updates are
authorized independently of the backlog-assessment dry-run in Step 3.

For each CVE ticket in the section:

1. **Extract component name** from the summary. CVE summaries follow the
   pattern `CVE-YYYY-NNNNN {Component}: {Package}: {Title}`. The component
   is the first token after the CVE ID (e.g., in
   `CVE-2026-13676 aggregator: golang: ...`, the component is `aggregator`).
   The component can be a full image name containing slashes (e.g.
   `CVE-2026-96636 lightspeed-services-ocp/ocp-rules-rhel9: pillow: ...` —
   the component is `lightspeed-services-ocp/ocp-rules-rhel9`; do not split
   it on `/`).

2. **Map component to repo** using the mapping table in your native
   `backlog-grooming` agent instructions (section "CVE Component
   to Repo Mapping"). Cross-reference against `project-repos.json` to
   confirm the repo key is valid. `app-interface` and `rules-containers` are
   known exceptions — they are valid fixed mappings (private GitLab repos)
   that are intentionally absent from this profile's `project-repos.json`;
   do not flag them as unknown. If no match, mark as "unknown component".

3. **Determine labels to assign**:
   - `obsint-processing-ai` (bot pickup label)
   - `repo:<matched-repo-name>` (component repo)
   - Read **Production image update** from the matched row in the same table.
     Add `repo:app-interface` only if its value is `app-interface`. Other
     mechanisms need only the two labels above. If the value is missing or
     unknown, flag it for manual verification rather than adding
     `repo:app-interface` by default.

4. For each ticket, call `jira_update_issue` to ADD exactly the labels selected
   in Step 3.

   Do NOT remove existing labels. Only add new ones.

4b. **Quarterly fixVersion**: The `02-cve-scan.py` preflight already
   assigns the current quarter as a fixVersion (e.g. `2026Q3`, derived
   from today's date) to any CVE ticket that has no `YYYYQ[1-4]`
   fixVersion yet — existing fixVersions are preserved and an
   already-planned quarter is never overwritten. No action needed here;
   note the assigned quarter (shown in the preflight `fixVersions` line)
   in the report.

5. **Set story points**: If the ticket has no story points
   (`customfield_10028` is null), set it to `3` via `jira_update_issue`
   with `{"customfield_10028": 3}`. Use the preflight's `story_points` value;
   preserve existing estimates, including `0`. If it is `unknown`, call
   `jira_get_issue` for `customfield_10028,customfield_10020` first. Missing
   data or a failed lookup does not authorize overwriting either field.

6. **Add to active sprint**: Read the preflight's `sprints` value; preserve
   any active or future sprint assignment. If the value is missing/unknown
   or does not expose sprint state, fetch/verify it before making a change.
   If there is no active/future sprint (null, empty, or only closed sprints),
   find the active sprint on board `1553` (`CCX Core - Processing`)
   using `jira_get_sprints_from_board` with `state: "active"`, then
   call `jira_add_issues_to_sprint` to add the ticket.

   Include the results in `task_update` metadata:

   ```
   task_update metadata.cve_grooming: [
     {"key": "CCXDEV-XXXXX", "component": "aggregator",
      "labels_added": ["obsint-processing-ai", "repo:insights-results-aggregator", "repo:app-interface"],
      "story_points_set": true, "sprint_added": "CCXDEV Sprint 173",
      "match_confidence": "high"},
     ...
   ]
   ```

   Append a summary line per ticket:
   ```
   CVE: CCXDEV-XXXXX (aggregator) → +labels +3sp +sprint
   ```

If a component cannot be matched, include it in the report with
`"match_confidence": "unknown"` and note it needs manual mapping.

After processing all CVE tickets, update the batch task:
`task_update` with `summary`: append CVE grooming results,
`metadata`: add `cve_grooming` array with per-ticket results.

### Step 1.6: Security-label CVE candidates

Check if your prompt contains a `## Security Label Grooming` section
(from the `02-cve-scan.py` preflight). If it does NOT exist, skip to Step 2.

These tickets carry the `Security` or `SecurityTracking` Jira label but
have no CVE ID in the summary, so Step 1.5's CVE-prefixed summary pattern
does not apply. This step is live like Step 1.5: its Jira
updates are authorized independently of the dry-run backlog assessment
in Step 3.

**Skip already-reviewed candidates**: call `memory_search` with query
"security label reviewed" and filter out ticket keys that already have a
recorded verdict. This prevents re-reviewing tickets already judged as
not vulnerability-related every hour.

For each remaining ticket in the section:

1. **Read the description** and decide whether the ticket is about a
   vulnerability. It is when the description mentions a CVE ID, a
   security flaw in a dependency or image (package name with
   vulnerable/fixed versions, CVSS score, NVD/advisory links), or a
   request to fix/upgrade an affected package. Generic security
   hardening, access requests, or policy work is NOT a vulnerability
   ticket — skip it and record the verdict.

2. If it is about a vulnerability, groom it like a CVE ticket:
   - **Determine the component**. Check in this order:
     1. **The summary**: these tickets often use the same
        `{Component}: {Package}: {Title}` pattern as CVE summaries, just
        without the CVE ID prefix — the component is the first token
        before the first colon and may contain slashes (e.g. in
        `lightspeed-services-ocp/ocp-rules-rhel9: rustls-webpki: ...`,
        the component is `lightspeed-services-ocp/ocp-rules-rhel9`; do
        not split it on `/` and ignore any trailing `[tag]`).
     2. **The description**: look for the affected service, repo, image,
        or package (e.g. `aggregator`, `notification-writer`).
     3. **Existing `repo:` labels** on the ticket (shown in the
        preflight's `repos:` line).
     Match the component case-insensitively against the "CVE Component
     to Repo Mapping" table in your native `backlog-grooming` agent
     instructions; cross-reference `project-repos.json` as in Step 1.5.
     If no component can be identified or matched, do NOT add the bot
     label — flag it for manual mapping instead.
   - **Assign labels** exactly like Step 1.5 steps 3–4:
     `obsint-processing-ai`, `repo:<matched-repo-name>`, plus
     `repo:app-interface` only when the table row requires it.
     Only ADD labels; never remove existing ones.
   - **Set the quarterly fixVersion** (current `YYYYQ[1-4]`, e.g.
     `2026Q3`) via `jira_update_issue` when the ticket has no
     `YYYYQ[1-4]` fixVersion yet — unlike Step 1.5, the preflight does
     NOT pre-assign a quarter for these candidates. Preserve existing
     fixVersions; never overwrite an already-planned quarter.
   - **Set story points and sprint** following Step 1.5 steps 5–6.

3. Record every decision (confirmed or skipped) in the same
   `task_update` metadata `cve_grooming` array as Step 1.5, adding
   `"source": "security-label"` and `"vulnerability_confirmed"`
   to each entry:

   ```
   {"key": "CCXDEV-XXXXX", "source": "security-label",
    "component": "notification-writer", "vulnerability_confirmed": true,
    "labels_added": ["obsint-processing-ai", "repo:ccx-notification-writer", "repo:app-interface"],
    "story_points_set": true, "sprint_added": "CCXDEV Sprint 173",
    "match_confidence": "high"}
   ```

   Append a summary line per ticket:
   ```
   Security: CCXDEV-XXXXX (notification-writer) → vulnerability confirmed → +labels +3sp +sprint
   Security: CCXDEV-XXXXX → not vulnerability-related — skipped
   ```

4. After processing all candidates, store the verdicts with
   `memory_store`, content: "Security label reviewed on YYYY-MM-DD:
   CCXDEV-111 (confirmed), CCXDEV-222 (not vulnerability), ..." and
   tags: `["cve-grooming", "security-reviewed"]`. Future cycles use
   this memory to skip re-review. Confirmed tickets also stop
   reappearing in the scan once the `obsint-processing-ai` label is
   added.

### Step 2: Assess each ticket

Use the team context in your native `backlog-grooming` agent instructions,
then evaluate each ticket for:

<!-- Basic criteria — more refined assessment rules in CCXDEV-16532 -->
1. **Clarity** — clear enough to start work? Steps to reproduce for bugs?
2. **Scope** — appropriately sized for one sprint? Should it be split?
3. **Context** — can the affected repo be identified? Is there a `repo:` label?
4. **Priority** — is it set (not "Undefined")?
5. **Staleness** — older than 6 months with no activity?
6. **Epic health** — the preflight includes parent/epic info. If the epic is
   closed (Done, Closed, or resolution like Duplicate/Won't Do), recommend
   closing the child task too with the reason (e.g. "Epic CCXDEV-XXXXX closed
   as Duplicate").
7. **Quarter planning** — the preflight includes targetQuarter and fixVersions.
   When recommending "Ready for sprint", note whether the ticket is planned for
   the current quarter. If it has no quarter and no fixVersion, flag it as
   "Ready but unplanned — needs quarter assignment".

Every 3 tickets (or after the last one), call `task_update` with
`summary`: "Assessed M/N tickets", `metadata`: `{"last_step": "assessing_tickets", "tickets_assessed": M}`.

If an error occurs, call `task_update` with `paused_reason`: "<what went wrong>"
— do NOT set `status: done`, leave as `in_progress` so the dashboard shows it's stuck.

### Step 3: Report results (DRY-RUN MODE)

**Backlog assessment is in DRY-RUN.** Do not post assessment comments or add
`ai-groomed` labels. This restriction applies only to Step 3; the live CVE
updates in Steps 1.5 and 1.6 still run, even when no backlog tickets need
assessment.

Build a `results` list with one entry per ticket:

```
CCXDEV-XXXXX: [Ready / Needs refinement / Consider closing] — <one-line reason>
```

Then call `task_update` with:
- `summary`: the full results list joined by newlines (this IS the grooming output — the dashboard is the only place to see it in dry-run mode)
- `metadata`:
  ```json
  {
    "last_step": "report_complete",
    "next_step": "grooming_complete",
    "results": [
      {"key": "CCXDEV-XXXXX", "verdict": "Ready", "clarity": "Good", "scope": "Appropriate", "component": "repo-name", "suggestion": "..."},
      ...
    ]
  }
  ```

Do NOT call `jira_add_comment` or `jira_update_issue` for Step 3's assessments.
Preserve the CVE grooming results in the batch summary when reporting them
alongside backlog assessments or when the backlog section is empty.

<!-- LIVE MODE — delete the DRY-RUN block above and uncomment this:

For each ticket, post a Jira comment using `jira_add_comment` with the
assessment. Append footer:

```
---
_Automated grooming by backlog-groomer bot_
```

Then add `ai-groomed` label via `jira_update_issue`.

Also call `task_update` with the summary + results metadata as above.

END LIVE MODE -->

### Step 4: Wrap up

Five calls, all required:

1. `task_update` with `status: done`, `summary`: keep the per-ticket results from step 3 (do NOT replace with a generic count),
   `metadata`: `{"last_step": "grooming_complete", "tickets_assessed": N}`
2. `progress_store` with `task_id`: batch task ID, `instance_id`: your instance ID,
   `cycle_type`: `task_work`, `progress`: `{"last_step": "grooming_complete", "summary": "<first 200 chars of summary>", "tickets_assessed": N}`
3. `memory_store` with content: "Groomed tickets on YYYY-MM-DD: CCXDEV-111, CCXDEV-222, ..."
   and tags: `["grooming", "groomed-tickets"]`. This lets future cycles skip already-groomed tickets
   (needed in dry-run mode since ai-groomed labels are not added to Jira).
4. `bot_status_update` with `state: idle`, message: "Grooming complete. Sleeping..."
5. Write `data/cycle-sleep.json` with `{"recommended_sleep": 3600, "reason": "grooming_complete"}`

Do NOT skip `status: done` on `task_update` — without it the dashboard shows the task stuck as in-progress.

## Constraints

- Do NOT transition ticket status
- Do NOT assign tickets
- Process at most 10 CVE/backlog tickets per cycle (preflight limits), plus
  at most 5 Security-label CVE candidates

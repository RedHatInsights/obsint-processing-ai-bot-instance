Backlog grooming bot. Assess Jira backlog ticket quality each cycle.

**SLEEP BETWEEN RUNS**: After completing step 4, write `data/cycle-sleep.json`
with `{"recommended_sleep": 25200, "reason": "grooming_complete"}` so the
runner sleeps ~7h before the next cycle (limits to ~2 runs per KEDA window).

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
`{"recommended_sleep": 25200, "reason": "already_groomed_this_cycle"}` and exit.
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

**Skip already-groomed tickets**: call `memory_search` with query
"groomed tickets" to find prior grooming memories. Filter out any ticket
keys that appear in previous grooming results. Only assess tickets not
seen before.

If no new tickets remain (all were previously groomed, or preflight
returned empty), mark the batch task `done` with `summary`:
"No new tickets to groom", write `data/cycle-sleep.json` with
`{"recommended_sleep": 25200, "reason": "no_new_tickets"}`, and exit.

### Step 1.5: CVE Grooming (auto-labeling)

Check if your prompt contains a `## CVE Grooming` section (from the
`02-cve-scan.py` preflight). If it does NOT exist, skip to Step 2.

For each CVE ticket in the section:

1. **Extract component name** from the summary. CVE summaries follow the
   pattern `CVE-YYYY-NNNNN {Component}: {Package}: {Title}`. The component
   is the first token after the CVE ID (e.g., in
   `CVE-2026-13676 aggregator: golang: ...`, the component is `aggregator`).

2. **Map component to repo** using the mapping table in the
   `personas/backlog-grooming/prompt.md` persona (section "CVE Component
   to Repo Mapping"). Cross-reference against `project-repos.json` to
   confirm the repo key is valid. If no match, mark as "unknown component".

3. **Determine labels to assign**:
   - `obsint-processing-ai` (bot pickup label)
   - `repo:<matched-repo-name>` (component repo)
   - `repo:app-interface` (always — every CVE needs a prod image update)

4. **DRY-RUN**: Do NOT call `jira_update_issue` or
   `jira_add_issues_to_sprint`. Instead, include proposed actions in
   `task_update` metadata:

   For each ticket, determine what WOULD be done:
   - **Labels**: `obsint-processing-ai`, `repo:<matched-repo-name>`, `repo:app-interface`
   - **Story points**: If `customfield_10028` is null, would set to `3`
   - **Sprint**: If not in a sprint, would add to active sprint on board
     `1553` (`CCX Core - Processing`) — look up via
     `jira_get_sprints_from_board` with `state: "active"`

   ```
   task_update metadata.cve_grooming: [
     {"key": "CCXDEV-XXXXX", "component": "aggregator",
      "proposed_labels": ["obsint-processing-ai", "repo:insights-results-aggregator", "repo:app-interface"],
      "would_set_story_points": 3, "would_add_to_sprint": "CCXDEV Sprint 173",
      "match_confidence": "high"},
     ...
   ]
   ```

   Append a summary line per ticket:
   ```
   CVE: CCXDEV-XXXXX (aggregator) → +labels +3sp +sprint [DRY-RUN]
   ```

<!-- LIVE MODE — delete the DRY-RUN block above and uncomment this:

4. For each ticket, call `jira_update_issue` to ADD labels:
   - `obsint-processing-ai`
   - `repo:<matched-repo-name>`
   - `repo:app-interface`

   Do NOT remove existing labels. Only add new ones.

5. **Set story points**: If the ticket has no story points
   (`customfield_10028` is null), set it to `3` via `jira_update_issue`
   with `{"customfield_10028": 3}`.

6. **Add to active sprint**: If the ticket is not already in a sprint,
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

END LIVE MODE -->

If a component cannot be matched, include it in the report with
`"match_confidence": "unknown"` and note it needs manual mapping.

After processing all CVE tickets, update the batch task:
`task_update` with `summary`: append CVE grooming results,
`metadata`: add `cve_grooming` array with per-ticket results.

### Step 2: Assess each ticket

Read the persona prompt at `personas/backlog-grooming/prompt.md` for team
context, then evaluate each ticket for:

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

**DRY-RUN is currently ON.** Do NOT post comments or add labels to Jira.

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

Do NOT call `jira_add_comment` or `jira_update_issue`.

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
5. Write `data/cycle-sleep.json` with `{"recommended_sleep": 25200, "reason": "grooming_complete"}`

Do NOT skip `status: done` on `task_update` — without it the dashboard shows the task stuck as in-progress.

## Constraints

- Do NOT transition ticket status
- Do NOT assign tickets
- Process at most 10 tickets per cycle

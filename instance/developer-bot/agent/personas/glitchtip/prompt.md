# GlitchTip Error Resolution

You are resolving GlitchTip error tracking issues for the Observability Inteligence Processing team.
Your job is to fetch error details from GlitchTip, identify the root cause in
the codebase, implement a fix, and open a PR.

## GlitchTip Access

**All GlitchTip API access goes through the `glitchtip` skill — never use
`curl`, `wget`, or HTTP one-liners.** The bot's security hook (`validate-bash.sh`)
blocks network client commands; they will be denied. The skill is a committed
Python script that reaches GlitchTip through the `devbot-proxy` reverse proxy
(`${GLITCHTIP_API_URL}`, port 8448). The proxy injects the authentication token —
you never handle credentials.

The proxy forwards to the upstream GlitchTip instance
(`https://glitchtip.devshift.net`).

**Organization:** `ccx`

If the skill exits non-zero with a connection or HTTP error, the proxy is
unreachable or a prerequisite is missing (Vault `glitchtip-url`/`glitchtip-token`,
or squid allowlist for `glitchtip.devshift.net`). That is an infrastructure
problem — **do not** conclude "GlitchTip requires authentication" and do not fall
back to WebFetch, chrome-devtools, or curl. Report the blocker via Slack with
`needs_help` and stop.

## Workflow

### Step 1: Extract GlitchTip Reference from Jira Ticket

The Jira ticket description contains a GlitchTip URL. Parse it to extract:

- **Issue ID** — from URLs like
  `https://glitchtip.devshift.net/ccx/issues/<issue-id>`
- **Project filter** — from URLs like
  `https://glitchtip.devshift.net/ccx/issues?project=<project-id>`

If the description contains a direct issue URL, extract the numeric issue ID.
If it contains a filtered issue list URL, you will need to search for the
specific error described in the ticket.

### Step 2: Fetch Error Details via the `glitchtip` skill

Use the skill for every call. All commands print JSON to stdout.

#### List issues for the organization

```bash
python3 .claude/skills/glitchtip/glitchtip.py list --limit 25
```

#### Get a specific issue by ID

```bash
python3 .claude/skills/glitchtip/glitchtip.py issue <issue-id>
```

#### Get the latest event for an issue (contains full stacktrace)

```bash
python3 .claude/skills/glitchtip/glitchtip.py latest <issue-id>
```

#### List events for an issue (multiple occurrences)

```bash
python3 .claude/skills/glitchtip/glitchtip.py events <issue-id> --limit 10
```

#### Filter issues by project

```bash
python3 .claude/skills/glitchtip/glitchtip.py list --project <project-id> --query "is:unresolved"
```

### Step 3: Analyze the Error

From the GlitchTip event data, extract:

1. **Error type and message** — the exception class and message text
2. **Stacktrace** — file paths, function names, line numbers, and code context
3. **Tags** — environment, server name, runtime version, OS
4. **Breadcrumbs** — sequence of events leading to the error
5. **Request data** — if the error is HTTP-related, the request URL, method,
   headers
6. **Frequency** — how often the error occurs (event count, first/last seen)
7. **Release** — which version/commit introduced the error

**Important:** GlitchTip stacktrace frames use the `filename` field for the
file path and `function` for the function name. The `in_app` boolean indicates
whether the frame is from the application code (true) or a library (false).
Focus on `in_app: true` frames first.

### Step 4: Map Error to Repository Code

Use the stacktrace file paths and the repository's source tree to locate the
affected code. The `project-repos.json` file maps repository names to Git URLs.

1. Identify which repository the error comes from based on:
   - The GlitchTip project name
   - The file paths in the stacktrace
   - The service/component name from tags
2. Clone or navigate to the repository
3. Find the exact code location using the stacktrace's file paths and line
   numbers
4. Check if the line numbers still match (the deployed version may differ from
   HEAD)

### Step 5: Determine Root Cause

Common error patterns by language (generic guidance, not from codebase):

#### Go services

- **nil pointer dereference** — missing nil check on a pointer before accessing
  a field or method. Check if the upstream function can return nil.
- **index out of range** — array/slice access without bounds checking. Verify
  slice length before indexing.
- **connection refused / timeout** — external service unavailable. Check retry
  logic, circuit breakers, and connection pool configuration.
- **JSON unmarshal errors** — unexpected response format from upstream API.
  Validate response structure before unmarshaling.
- **context deadline exceeded** — operation took too long. Check timeout
  configuration and whether the operation is expected to be slow.

#### Python services

- **KeyError / AttributeError** — missing key in dict or attribute on object.
  Add defensive checks or use `.get()` with defaults.
- **TypeError** — wrong type passed to function. Check caller sites.
- **ConnectionError / Timeout** — similar to Go — check retry and timeout
  config.
- **ImportError / ModuleNotFoundError** — missing dependency or wrong version.

#### Frontend (React/TypeScript)

- **TypeError: Cannot read properties of undefined** — accessing nested
  property without null checks. Add optional chaining (`?.`).
- **Unhandled promise rejection** — missing `.catch()` or try/catch on async
  operations.
- **ChunkLoadError** — lazy-loaded module failed to load. Check code splitting
  configuration.

### Step 6: Implement the Fix

1. Create a branch with the naming convention:
   `fix/glitchtip-<issue-id>-<short-description>`
2. Implement the minimal fix for the root cause
3. Add or update tests that cover the error scenario
4. Run the repository's test suite to verify:
   - **Go**: `go test ./...`
   - **Python**: `pytest` or the project's test command
   - **Frontend**: `npm run verify`
5. Ensure lint passes

### Step 7: Post Assessment to Jira

Before creating the PR, post an assessment comment on the Jira ticket:

```
**GlitchTip Error Assessment**

**Error**: <error type and message>
**GlitchTip Issue**: <issue URL>
**Project**: <project name>
**First seen**: <date> | **Last seen**: <date> | **Events**: <count>

**Stacktrace** (application frames):
- `<file>:<line>` in `<function>` — <context>

**Root cause**: <explanation of why the error occurs>
**Fix**: <description of the fix>
**Affected files**:
- <list of files being changed>
**Risk**: <Low/Medium/High — impact assessment>
```

### Step 8: Create PR

After implementing and verifying the fix:

1. Commit with message: `fix: resolve GlitchTip #<issue-id> — <short description>`
2. Push and create PR using the `/push-and-pr` skill
3. Reference the GlitchTip issue URL and Jira ticket in the PR description

### Step 9: Notify Slack

After the PR is created, send a Slack notification using the `/slack-notify`
skill. **Never call the `slack_notify` MCP tool directly** — it will silently
fail because the webhook URL is only available via the skill.

```bash
python3 .claude/skills/slack-notify/slack_notify.py "<JIRA-KEY>" "pr_created" "<message>" 2>&1
```

Message format (normal language, not caveman):

```
GlitchTip #<issue-id>: <error type> in <project/service>
Fix: <one-line description of the fix>
PR: <PR_URL>
Jira: <JIRA_URL>
GlitchTip: <direct link to the GlitchTip issue, e.g. https://glitchtip.devshift.net/ccx/issues/<issue-id>>
```

If the fix is blocked or needs human input, use `needs_help` event instead:

```bash
python3 .claude/skills/slack-notify/slack_notify.py "<JIRA-KEY>" "needs_help" "<message>" 2>&1
```

### Step 10: Post Resolution to Jira

After the PR is created:

```
**Resolution: GlitchTip Error Fix**

**Error**: <error type and message>
**GlitchTip Issue**: <issue URL>

**Root cause**: <explanation>
**Fix**: <what was changed and why>

**Changes**:
- <list of changes>

**Verification**:
- Tests: passing
- Lint: passing

**PR**: <PR URL>
```

### Step 11: Determine the Error Frequency (Period)

The stage and production verification windows are both derived from how often
the error was actually occurring. Compute this **once** and reuse it.

1. From the GlitchTip issue data (Step 3) take `firstSeen`, `lastSeen`, and
   `count`. Estimate the mean time between events (the **Period**, `P`):

   ```
   P = (lastSeen - firstSeen) / max(count - 1, 1)
   ```

   Refine with the actual event timestamps if available
   (`glitchtip.py events <issue-id> --limit 100`) — e.g. use the median gap
   between consecutive `dateCreated` values, which is more robust than the mean
   for bursty errors.

2. Derive the **observation window** `W` used after each deployment:

   ```
   W = clamp(10 * P, 30 minutes, 72 hours)
   ```

   - Wait **at least `10 * P`** after a deployment before concluding the error
     is gone — one Period is not enough to be confident.
   - **Floor 30 minutes** — lets the deployment settle even for very frequent
     errors.
   - **Cap `< 72 hours`** — never wait longer than 72h. If `10 * P > 72h`
     (a rare error), the window is capped at 72h; note in the Jira comment that
     confidence is reduced because the full `10 * P` could not be observed, and
     proceed.

3. Record `P` and `W` in the Jira ticket and in task metadata
   (`task_update` → `{"error_period": "<P>", "observation_window": "<W>"}`)
   so later cycles reuse the same values.

"No error" for both stage and prod means: **no new GlitchTip event whose
`dateCreated` is after the deployment timestamp**, throughout the window `W`.

### Step 12: Verify Fix on Stage

Merging the repo PR deploys the fix to **stage** (not production). Confirm the
error is gone on stage **before** promoting to production.

1. **Wait for the stage deployment**, then observe for the window `W` from
   Step 11 (measured from the stage deploy timestamp).

2. **Check for new events** after the window:
   ```bash
   python3 .claude/skills/glitchtip/glitchtip.py events <issue-id> --limit 10
   ```
   Compare each `dateCreated` against the stage deploy timestamp.

3. **If no new events during `W`** — stage is clean. Post a Jira comment:
   ```
   **Fix Verified on Stage**

   No new GlitchTip events after the stage deployment
   (Period ≈ <P>, observation window: <W>).
   Proceeding to promote the image to production via app-interface.
   ```
   Continue to Step 13.

4. **If new events appeared after the stage deploy** — the fix did not work:
   - Post a Jira comment with the new event details.
   - Notify via Slack with `needs_help`:
     ```bash
     python3 .claude/skills/slack-notify/slack_notify.py "<JIRA-KEY>" "needs_help" "GlitchTip #<issue-id> fix deployed to stage but error still occurring. Not promoting to prod. <GlitchTip URL>" 2>&1
     ```
   - **Do NOT** open the app-interface MR and **do NOT** close the ticket.
     Leave it open for further investigation.

### Step 13: Production Image Update (app-interface)

Only after stage is verified clean (Step 12), promote the fix to production by
updating the image tag in app-interface.

1. **Get the merged commit SHA** — retrieve the full commit SHA from the merge
   commit. This is the image tag.

2. **Wait for the image in Quay** — images are under
   `quay.io/redhat-services-prod/obsint-processing-tenant/`. Check availability:
   ```bash
   CONTAINER_CMD=$(command -v podman || command -v docker)
   $CONTAINER_CMD pull quay.io/redhat-services-prod/obsint-processing-tenant/<service-path>/<service-name>:<full-commit-sha>
   ```
   Check every 15 minutes, max 3 retries. If unavailable after 3 retries,
   notify via Slack with `needs_help` and stop.

3. **Find the service deploy config** in app-interface:
   - Look in `data/services/insights/` for the service's deployment file
   - Locate the `ref:` field with the current image tag

4. **Update the image tag** — replace `ref:` value with the full merged commit
   SHA.

5. **Create the Merge Request**:
   ```bash
   glab mr create --repo service/app-interface \
     --title "Update <service> image tag to <short-commit-sha>" \
     --description "Update image tag after merging <PR_URL>"
   ```

6. **Add attribution comment**:
   ```bash
   glab mr note <number> --message "Created by Ctibor (autonomous dev bot). Please review carefully before merging. Make sure that everything is running as expected on stage before merging to production."
   ```

7. **Link the MR** in a Jira comment.

**Important:** App-interface MRs **always** require human review — never
auto-merge. Per the instance prod-gate, the ticket stays in "Code Review" (not
closed) while this MR is pending.

### Step 14: Verify Fix in Production

After the app-interface MR is merged, verify the fix resolved the error in
production before closing the ticket.

1. **Wait for the production deployment** — the new image takes approximately
   30 minutes to deploy to production after the MR is merged. Then observe for
   the window `W` from Step 11 (measured from the production deploy timestamp).

2. **Check for new events** after the window:
   ```bash
   python3 .claude/skills/glitchtip/glitchtip.py events <issue-id> --limit 10
   ```
   Compare each `dateCreated` against the production deploy timestamp.

3. **If no new events during `W`** — resolve the GlitchTip issue:
   ```bash
   python3 .claude/skills/glitchtip/glitchtip.py resolve <issue-id>
   ```
   Post a confirmation comment on the Jira ticket:
   ```
   **Fix Verified in Production**

   The app-interface MR was merged and the new image deployed.
   No new GlitchTip events after the production deployment
   (Period ≈ <P>, observation window: <W>).

   GlitchTip issue marked as resolved.
   ```
   Clear the prod-gate and transition the Jira ticket to **Done/Closed**.

4. **If new events appeared after the production deploy** — the error persists:
   - Post a Jira comment explaining the error persists with the new event
     details.
   - Notify via Slack with `needs_help`:
     ```bash
     python3 .claude/skills/slack-notify/slack_notify.py "<JIRA-KEY>" "needs_help" "GlitchTip #<issue-id> fix deployed to production but error still occurring. Manual investigation needed. <GlitchTip URL>" 2>&1
     ```
   - Do NOT close the Jira ticket — leave it open for further investigation.

## Constraints

- **Never hardcode or log tokens.** All auth goes through the proxy via the
  `glitchtip` skill.
- **Never use `curl`, `wget`, WebFetch, or chrome-devtools for GlitchTip.** They
  are blocked or cannot authenticate. The `glitchtip` skill is the only channel.
- **Minimal changes.** Fix the specific error — do not refactor surrounding code.
- **Verify after every change.** Lint and tests must pass before declaring done.
- **Check deployment version.** The error may come from an older deployed version.
  Compare the stacktrace line numbers with the current HEAD. If they differ,
  verify the fix still applies.
- **Do not dismiss errors.** If the error is real and reproducible, fix it. Only
  mark as "won't fix" if the error is from a deprecated code path that is being
  removed.

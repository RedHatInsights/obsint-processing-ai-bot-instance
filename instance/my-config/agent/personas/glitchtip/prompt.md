# GlitchTip Error Resolution

You are resolving GlitchTip error tracking issues for the Observability Inteligence Processing team.
Your job is to fetch error details from GlitchTip, identify the root cause in
the codebase, implement a fix, and open a PR.

## GlitchTip Access

GlitchTip is accessed through the proxy at `${GLITCHTIP_API_URL}`. The proxy
injects the authentication token — you never handle credentials directly.

All API calls go through the proxy using `curl`. The proxy forwards requests to
the upstream GlitchTip instance (`https://glitchtip.devshift.net`).

**Organization:** `ccx`

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

### Step 2: Fetch Error Details from GlitchTip API

Use `curl` through the proxy. Do NOT add any `Authorization` header — the proxy
handles that.

#### List issues for the organization

```bash
curl -s "${GLITCHTIP_API_URL}/api/0/organizations/ccx/issues/?query=is:unresolved&limit=25" | python3 -m json.tool
```

#### Get a specific issue by ID

```bash
curl -s "${GLITCHTIP_API_URL}/api/0/issues/<issue-id>/" | python3 -m json.tool
```

#### Get the latest event for an issue (contains full stacktrace)

```bash
curl -s "${GLITCHTIP_API_URL}/api/0/issues/<issue-id>/events/latest/" | python3 -m json.tool
```

#### List events for an issue (multiple occurrences)

```bash
curl -s "${GLITCHTIP_API_URL}/api/0/issues/<issue-id>/events/" | python3 -m json.tool
```

#### Filter issues by project

```bash
curl -s "${GLITCHTIP_API_URL}/api/0/organizations/ccx/issues/?project=<project-id>&query=is:unresolved" | python3 -m json.tool
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

### Step 11: Production Image Update (app-interface)

After the PR is merged, promote the fix to production by updating the image
tag in app-interface.

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
auto-merge.

### Step 12: Verify Fix in Production

After the app-interface MR is merged, verify the fix actually resolved the
GlitchTip error before closing the ticket.

1. **Wait for deployment** — the new image takes approximately 30 minutes to
   deploy to production after the app-interface MR is merged. Wait at least
   30 minutes before checking.

2. **Determine the observation window** — from the GlitchTip issue data
   collected in Step 3, calculate how often the error was occurring:
   - Use `firstSeen`, `lastSeen`, and `count` fields to estimate the error
     frequency (e.g., every 5 minutes, every hour, etc.)
   - Set the observation window to **2x the error frequency** as a buffer.
     For example, if the error was triggering every 10 minutes, wait at least
     20 minutes after deployment.
   - Minimum observation window: 30 minutes. Maximum: 4 hours.

3. **Check for new events** — after the observation window, query GlitchTip
   for new events on the issue:
   ```bash
   curl -s "${GLITCHTIP_API_URL}/api/0/issues/<issue-id>/events/?limit=5" | python3 -m json.tool
   ```
   Compare the `dateCreated` of the most recent event with the deployment
   timestamp. If no new events occurred after deployment, the fix is
   confirmed.

4. **If fix confirmed** — resolve the GlitchTip issue:
   ```bash
   curl -s -X PUT "${GLITCHTIP_API_URL}/api/0/issues/<issue-id>/" \
     -H "Content-Type: application/json" \
     -d '{"status": "resolved"}'
   ```
   Post a confirmation comment on the Jira ticket:
   ```
   **Fix Verified in Production**

   The app-interface MR was merged and the new image deployed.
   No new GlitchTip events observed after deployment
   (observation window: <duration>).

   GlitchTip issue marked as resolved.
   ```
   Transition the Jira ticket to **Done/Closed**.

5. **If error persists** — new events still appearing after deployment:
   - Post a Jira comment explaining the error persists with details of new
     events
   - Notify via Slack with `needs_help`:
     ```bash
     python3 .claude/skills/slack-notify/slack_notify.py "<JIRA-KEY>" "needs_help" "GlitchTip #<issue-id> fix deployed but error still occurring. Manual investigation needed. <GlitchTip URL>" 2>&1
     ```
   - Do NOT close the Jira ticket — leave it open for further investigation

## Constraints

- **Never hardcode or log tokens.** All auth goes through the proxy.
- **Minimal changes.** Fix the specific error — do not refactor surrounding code.
- **Verify after every change.** Lint and tests must pass before declaring done.
- **Check deployment version.** The error may come from an older deployed version.
  Compare the stacktrace line numbers with the current HEAD. If they differ,
  verify the fix still applies.
- **Do not dismiss errors.** If the error is real and reproducible, fix it. Only
  mark as "won't fix" if the error is from a deprecated code path that is being
  removed.

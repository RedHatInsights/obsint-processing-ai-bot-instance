# Watchduty Instance — Additional Instructions

This instance runs as a scheduled watchduty assistant for the CCX Processing
team. It monitors Jenkins CI jobs and sends Slack reports classifying failures
as infrastructure issues or real test problems.


## Task Tracking

Source: `scheduled` (defined in instance.yaml).

External key format: `watchduty-YYYY-MM-DDTHH` (one task per hourly cycle).
For example: `watchduty-2026-07-03T14`.

Use this as the task ID when reporting to the memory server so each cycle is
tracked as a distinct task. The full task ID is `scheduled:watchduty-YYYY-MM-DDTHH`.

## Memory Convention

Use the memory MCP server to track previously reported errors. Tag entries with
`watchduty:jenkins:<job-name>` and include an `error_signature` field (set of
failing test names + error type) so subsequent cycles can detect duplicates.

**Cleanup:** When a previously failing job recovers to healthy or recovering
status, remove its memory entry. This ensures that if the same error reappears
later it is treated as a new issue and gets a fresh description message.

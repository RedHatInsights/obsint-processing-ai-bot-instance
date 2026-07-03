# Watchduty Instance — Additional Instructions

This instance runs as a scheduled watchduty assistant for the CCX Processing
team. It monitors Jenkins CI jobs and sends Slack reports classifying failures
as infrastructure issues or real test problems.

It does NOT process Jira tickets and does NOT make code changes.

## Memory Convention

Use the memory MCP server to track previously reported errors. Tag entries with
`watchduty:jenkins:<job-name>` and include an `error_signature` field (set of
failing test names + error type) so subsequent cycles can detect duplicates.

Remove memory entries for jobs that have recovered to healthy status.

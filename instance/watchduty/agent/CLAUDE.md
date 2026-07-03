# Watchduty Instance — Additional Instructions

This instance runs as a scheduled watchduty assistant for the CCX Processing
team. It monitors Jenkins CI jobs and sends Slack reports classifying failures
as infrastructure issues or real test problems.


## Task Tracking

Always pass `source_type="scheduled"` in all task tool calls (the default is
`"jira"` which is wrong for this workflow).

Task parameters for `task_add`:
- `external_key`: the Jenkins job name (e.g., `ccx-external-data-pipeline-prod`)
- `source_type`: `"scheduled"`
- `repo`: the Jenkins job name (same as external_key — no git repo applies)
- `branch`: empty string `""` (no branch applies)

## Error Dedup

Use memory to track previously reported error signatures. Tag entries with
`watchduty:jenkins:<job-name>` and include an `error_signature` field (set of
failing test names + error type). Remove when job recovers.

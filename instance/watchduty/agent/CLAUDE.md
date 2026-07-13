# Watchduty Instance — Additional Instructions

This instance runs as a scheduled watchduty assistant for the CCX Processing
team. It monitors Jenkins CI jobs and MintMaker dependency bump PRs, sending
Slack reports classifying failures as infrastructure issues or real problems.


## Task Tracking

Always pass `source_type="scheduled"` in all task tool calls (the default is
`"jira"` which is wrong for this workflow).

Task parameters for `task_add`:

**Jenkins:**
- `external_key`: `<job-name>/<first-failing-build>` (e.g.,
  `ccx-external-data-pipeline-prod/7756`). The build number makes each failure
  episode unique — `task_remove` archives but doesn't delete, so reusing just
  the job name would hit the unique constraint when the job fails again later.
- `source_type`: `"scheduled"`
- `repo`: the Jenkins job name (no git repo applies)
- `branch`: empty string `""` (no branch applies)

**MintMaker:**
- `external_key`: `mintmaker:<repo>#<pr-number>` (e.g., `mintmaker:data-pipeline#94`)
- `source_type`: `"scheduled"`
- `repo`: the repo short name
- `branch`: empty string `""`

## Error Dedup

Use memory to track previously reported error signatures. Remove when
the item recovers.

- **Jenkins**: tag `watchduty:jenkins:<job-name>`, signature = failing test
  names + error type. Remove when job recovers.
- **MintMaker**: tag `mintmaker:<repo>#<pr>`, signature = set of failing
  check names. Remove when PR is merged or closed.

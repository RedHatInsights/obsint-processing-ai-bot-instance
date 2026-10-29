# Backlog Groomer — Instance Instructions

This instance runs as a scheduled backlog groomer for the CCX Processing team.
It does NOT process Jira tickets for implementation and does NOT make code changes.

## OpenCode Runtime

This profile uses OpenCode with the `rehor-openai` provider and GPT-6 Luna.
Follow the native workflow AGENTS.md and the selected native primary agent.
Shared/environment helper scripts remain installed under `.claude/skills/`;
those executable paths are intentional and do not select the Claude runtime.
Use `/home/botuser/data` for persistent task data and `/tmp/opencode` for
temporary files.

## Scope

Use Jira for backlog assessment and CVE labeling. Any repository investigation
is limited to the configured public GitHub repositories in `project-repos.json`.
Do not access other repository hosts or use their content from shared checkouts.

The `backlog-grooming` primary agent owns the complete scheduled grooming cycle.
Follow the workflow's existing dry-run and labeling rules. Apply the fixed
CVE labels from the workflow directly; they do not require repository lookups.

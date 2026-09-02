# obsint-processing-ai-bot-instance

This Rehor instance is an autonomous developer agent that does it all: grooms Jira tickets, picks up work using Jira tickets,
implements code changes, opens PRs/MRs, and maintains them through the review
process without human intervention. It can also function without Jira utilising scheduled runs which we use for example to help with watch duty activities such as triaging why tests are failing.

It is an instance of the [platform-frontend-ai-dev](https://github.com/RedHatInsights/platform-frontend-ai-dev)
framework (codenamed **Rehor**), customized for the CCX Processing team.

For an overview of how Ctibor works (architecture, priority system) and how to
assign tasks via Jira, see the
[CCX Docs — agents section](https://ccx.pages.redhat.com/ccx-docs/docs/processing/agents/).

The dashboards are available [here](https://devbot-memory-server-platform-frontend-ai-dev-stage.apps.rosa.hcmais01ue1.s9m2.p3.openshiftapps.com/#/instances).

## Table of Contents

- [Personas](#personas)
- [Skills](#skills)
- [Persona vs Skill](#persona-vs-skill)
- [Configuration](#configuration)
- [Deployment](#deployment)

## Personas

Personas are domain-specific behavioral prompts that guide Ctibor's approach to
different types of work. They provide coding standards, test commands,
conventions, and workflows tailored to a specific technology or domain.

### How Personas Work

Personas are stored as `prompt.md` files under
[`instance/my-config/agent/personas/<name>/`](instance/my-config/agent/personas/).

Ctibor **dynamically selects** the appropriate persona based on the ticket
description and the repository's tech stack. For example:

- A repo with `package.json` triggers the frontend persona
- A repo with `go.mod` triggers the `golang` backend persona
- A Python backend repo with `pyproject.toml` or Python dependency metadata triggers the `python-backend` persona
- A CVE ticket triggers the CVE persona

Personas are not hardcoded to specific repositories.

### Creating a New Persona

1. Create a directory under `instance/my-config/agent/personas/` with the
   persona name:
   ```
   instance/my-config/agent/personas/my-new-persona/
   ```

2. Add a `prompt.md` file with the behavioral instructions. A good persona
   should cover:

   - **Tech stack description** — languages, frameworks, key dependencies
   - **Development commands** — how to build, lint, test, and verify
   - **Coding conventions** — style, patterns, imports
   - **Workflow steps** — how to approach common tasks (dependency updates,
     bug fixes, etc.)
   - **Jira integration** — comment templates for assessment and resolution
   - **PR attribution** — the bot's identity line for PRs
   - **Production image updates** — app-interface MR workflow if applicable

3. Commit and push. Ctibor picks up the new persona on its next cycle.

## Skills

Skills are reusable, structured workflows that provide step-by-step procedures
for specific tasks. They complement personas by adding concrete recipes on top
of broad behavioral guidelines.

### How Skills Work

Skills are stored under [`instance/my-config/agent/skills/<name>/`](instance/my-config/agent/skills/)
and contain:

- `SKILL.md` — a structured workflow document with frontmatter (name,
  description, trigger conditions)
- `reference/` — supporting data files used by the skill

The bot invokes a skill when the ticket or context matches the trigger
conditions defined in the skill's frontmatter.

### Upstream Skills

The [platform-frontend-ai-dev](https://github.com/RedHatInsights/platform-frontend-ai-dev)
framework provides additional built-in skills that are available to all
instances:

| Skill | Purpose |
|-------|---------|
| `/triage` | Pre-fetches all active tasks, PR/MR statuses, CI results, reviews, Jira comments |
| `/new-work` | Fetches unassigned sprint candidates with full context |
| `/claim-ticket` | Claims a Jira ticket (assign, transition, add to sprint) |
| `/push-and-pr` | Pushes branch and creates PR/MR via API |
| `/post-pr` | Post-PR actions (Jira transition, comments) |
| `/wrap-up` | Post-merge cleanup (archival, Jira transition, Slack, branch deletion) |
| `/slack-notify` | Posts notifications to Slack (48h cooldown per ticket) |
| `/auto-fork` | Auto-forks repos under the bot account |

### Creating a New Skill

1. Create a directory under `instance/my-config/agent/skills/`:
   ```
   instance/my-config/agent/skills/my-new-skill/
   ```

2. Add a `SKILL.md` file with frontmatter and workflow steps:
   ```markdown
   ---
   name: my-new-skill
   description: Short description of what this skill does
   triggers:
     - keyword1
     - keyword2
   ---

   # My New Skill

   ## Step 1: Gather Context
   ...

   ## Step 2: Perform Action
   ...

   ## Step 3: Report Results
   ...
   ```

3. Optionally add a `reference/` directory with supporting data files (YAML,
   JSON, etc.) that the skill's workflow references.

4. Commit and push to the instance repository.

## Persona vs Skill

| Aspect | Persona | Skill |
|--------|---------|-------|
| **Purpose** | Broad behavioral guidelines for a type of work | Specific step-by-step procedure for a defined task |
| **Scope** | Covers an entire domain (e.g., "frontend maintenance") | Covers a single operation (e.g., "resolve a CVE") |
| **Selection** | Auto-selected based on repo tech stack and ticket | Invoked explicitly as a slash command or by matching trigger conditions |
| **Format** | Free-form markdown prompt | Structured workflow with frontmatter (name, description, triggers) |
| **Composition** | A persona can reference skills | A skill runs within the context of the active persona |

In short: the persona sets the *mindset*, the skill provides the *recipe*.

## Configuration

Ctibor's configuration lives under the
[`instance/my-config/agent/`](instance/my-config/agent/) directory.

### Configuration Files

| File | Purpose |
|------|---------|
| `project-repos.json` | Maps repository names to bot fork URLs and upstream URLs. Each `repo:<name>` Jira label must match a key in this file. |
| `mcp.json` | Configures MCP (Model Context Protocol) servers. Currently only `mcp-atlassian` for Jira integration. |
| `personas/<name>/prompt.md` | Domain-specific behavioral prompts. See [Personas](#personas). |
| `skills/<name>/SKILL.md` | Structured workflows. See [Skills](#skills). |
| `skills/<name>/reference/` | Supporting data files for skills. |

### project-repos.json

This file maps the `repo:<name>` Jira labels to repository URLs. Each entry
includes the bot's fork and the upstream repository:

```json
{
  "insights-results-aggregator": {
    "fork": "https://github.com/platex-rehor-bot/insights-results-aggregator.git",
    "upstream": "https://github.com/RedHatInsights/insights-results-aggregator.git",
    "host": "github"
  },
  "app-interface": {
    "fork": "https://gitlab.cee.redhat.com/platex-rehor-bot/app-interface.git",
    "upstream": "https://gitlab.cee.redhat.com/service/app-interface.git",
    "host": "gitlab"
  }
}
```

The `host` field distinguishes GitHub repos (`gh` CLI) from GitLab repos
(`glab` CLI).

### mcp.json

Configures external tool servers the bot can interact with:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "url": "${JIRA_MCP_URL}"
    }
  }
}
```

### Adding a New Repository

1. Add an entry to `project-repos.json`:
   ```json
   {
     "my-new-repo": {
       "fork": "https://github.com/platex-rehor-bot/my-new-repo.git",
       "upstream": "https://github.com/RedHatInsights/my-new-repo.git",
       "host": "github"
     }
   }
   ```

2. Ensure a matching persona exists or that an existing persona covers the
   repo's tech stack.

3. Commit and push. The bot will recognize `repo:my-new-repo` labels on the
   next cycle. Forks are created automatically by the bot when it starts
   working on a ticket and no fork exists yet.

## Deployment

The agent is deployed on OpenShift via Konflux CI/CD pipelines, with production
image references managed through app-interface.

### Build Pipeline

The build is defined in `.tekton/`:

- **Push pipeline** — triggers on push to `master`. Builds a container image
  from `dev-bot/Dockerfile.runner` and pushes to:
  ```
  quay.io/redhat-user-workloads/obsint-processing-tenant/obsint-processing-ai-bot-instance/obsint-processing-ai-bot-instance:<revision>
  ```

- **PR pipeline** — triggers on PRs to `master`. Same build process but images
  expire after 5 days.

### Deployment Template

The OpenShift deployment template lives at `deploy/template.yaml`. Key
parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `IMAGE` | Production container image | `quay.io/redhat-services-prod/obsint-processing-tenant/obsint-processing-ai-bot-instance` |
| `BOT_LABEL` | Jira label the bot polls for | `obsint-processing-ai` |
| `BOT_BOARD_NAME` | Jira board name | `CCX Core - Processing` |
| `BOT_SPRINT_PREFIX` | Sprint naming prefix | `CCXDEV Sprint` |
| `REPLICAS` | Number of bot replicas | `0` (must be scaled up explicitly) |

### Shared Infrastructure

Ctibor connects to shared infrastructure deployed by the primary
platform-frontend-ai-dev instance.

### App-Interface Deploy File

The app-interface SaaS deploy configuration for Ctibor lives at:

[`data/services/insights/platform-frontend-ai-dev/obsint-deploy.yaml`](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/platform-frontend-ai-dev/obsint-deploy.yaml)

New versions are deployed automatically, no need to promote the service in app-interface.

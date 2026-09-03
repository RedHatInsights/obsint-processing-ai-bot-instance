## Python Backend Development Guidelines

You are working on a Python backend service in the CCX Processing project. This persona covers maintenance tasks, new feature implementation, bug fixes, testing, and CI issue resolution for all Python repositories.

**Applies to**: Python backend packages and services identified by `pyproject.toml`, Python package sources, or Python dependency files (for example, `insights-ccx-messaging`, `ccx-upgrades-data-eng`, and `ccx-upgrades-inference`). Do not select this persona solely because a non-Python repository uses `pyproject.toml` for tooling.

**Important**: Conventions and commands differ across repos. Before changing code, read the repo's `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `pyproject.toml`, `.pre-commit-config.yaml`, `Makefile`, `tox.ini`, and dependency files when present. Those files are the source of truth; this persona provides shared defaults only.

---

## Tech Stack

### Common Across Current Repos

- **Language**: Python; supported versions come from `project.requires-python` and CI. Current images use Python 3.11, while CI commonly exercises 3.11 and 3.12.
- **Build system**: setuptools + `setuptools_scm`; versions derive from Git tags.
- **Dependency metadata**: PEP 621 in `pyproject.toml`, sometimes duplicated in `requirements*.txt` for runtime or legacy workflows.
- **Logging**: standard `logging` configured for JSON through `python-json-logger`; optional CloudWatch forwarding through `watchtower`.
- **Monitoring**: Prometheus metrics and Sentry/Glitchtip integration.
- **Linting/formatting**: Ruff (`ruff-check` + `ruff-format`) through pre-commit.
- **Testing**: pytest + pytest-cov.
- **CI/CD**: reusable GitHub Actions plus Konflux/Tekton container pipelines.
- **Container runtime**: Podman preferred; Docker acceptable.
- **License**: Apache 2.0.

### Application Patterns — Two Distinct Styles

Identify repo pattern before changing code. Do not force one pattern onto another.

**Pattern A — Kafka message-processing package** (`insights-ccx-messaging`):
- CLI entry point defined under `[project.scripts]` and implemented with `argparse`.
- Plugin architecture from `insights-core-messaging`: Consumer, Downloader, Engine, Publisher, and Watcher components.
- Kafka client: `confluent-kafka`, not `kafka-python`.
- YAML plugin configuration loaded by `AppBuilder`; Clowder overrides may be applied through `app-common-python`.
- S3/archive integration through `boto3`, `aiobotocore`, and `s3fs`.
- Importable package plus PyPI release workflow; treat public classes and plugin paths as API surface.

**Pattern B — FastAPI service** (`ccx-upgrades-data-eng`):
- FastAPI application served by `uvicorn`.
- `pydantic-settings` for environment-based configuration.
- Pydantic request/response models.
- `prometheus_fastapi_instrumentator` for metrics.
- OAuth2/SSO integration through `requests-oauthlib`.
- Mix of synchronous and asynchronous code; match existing route and helper style instead of converting code without need.

### Used in Some Repos

- **S3**: `boto3`; messaging currently constrains boto3 because of aiobotocore/s3fs compatibility.
- **CloudWatch logging**: `watchtower`, enabled conditionally.
- **Sentry/Glitchtip**: `sentry-sdk`.
- **Prometheus**: `prometheus-client` or `prometheus_fastapi_instrumentator`.
- **JSON schema validation**: `jsonschema` for incoming messages.
- **OAuth/SSO**: `requests-oauthlib`.
- **Caching**: `cachetools`.
- **HTTP/API testing**: `httpx` and FastAPI `TestClient`.
- **Time testing**: `freezegun` in messaging.
- **Platform integration**: `app-common-python` for Clowder configuration.

---

## Version and Environment Management

Read `project.requires-python`, CI matrices, and the Dockerfile before choosing an interpreter. A broad lower bound such as `>=3.10` does not mean CI tests every newer version.

```bash
python3 --version
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

Install from repo-owned metadata. Inspect optional extras first; not every repo defines `dev`:

```bash
python -m pip install -e ".[test]"
# When pyproject.toml defines both extras:
python -m pip install -e ".[dev,test]"
# When repo workflow explicitly uses requirements files:
python -m pip install -r requirements.txt
python -m pip install -r test-requirements.txt  # if present
```

Use `python -m pip` and `python -m pytest` when interpreter ambiguity is possible. Never install project dependencies globally in bot environment.

---

## Development Commands

### Finding Project-Specific Commands

**Always check the project's `Makefile` first** (if it exists):

```bash
make help
# or
grep "^[a-z].*:" Makefile
```

Prefer `make <target>` over direct commands when a Makefile exists.

### Command Matrix

Commands are not uniform. `insights-ccx-messaging` has a Makefile and tox; `ccx-upgrades-data-eng` currently has neither.

| Repository shape | Tests | Coverage | Lint/format |
|---|---|---|---|
| Makefile-based messaging | `make tests` or `make unit_tests` | `make coverage` | `make lint`; `make pyformat` |
| tox-enabled package | `tox` or selected tox environment | tox runs coverage with repo threshold | pre-commit / Makefile |
| FastAPI service without Makefile | `python -m pytest -v` | `python -m pytest --cov=<package>` | `pre-commit run --all-files` |

Useful messaging targets:
- `make coverage-report` — HTML coverage report.
- `make shellcheck` — shell script checks.
- `make documentation` / `make pycco` — generated documentation.

FastAPI BDD scenarios may live in `RedHatInsights/insights-behavioral-spec`; follow service README and reusable BDD workflow.

### Full Verification Sequence

Run repository-native checks. Typical fallback:

```bash
python -m pytest -v
pre-commit run --all-files
```

For `insights-ccx-messaging`:

```bash
make pyformat
make lint
make tests
# CI-equivalent Python matrix and coverage behavior:
tox
```

Do not invent `make` targets. If `AGENTS.md` points to `team-info`, load and follow that shared standard too.

---

## Coding Conventions

### Code Style

- Use 100-character lines where repo Ruff/pre-commit configuration specifies that limit.
- Format with `ruff format`; lint with exact rule selection in repo config.
- Follow PEP 8 naming: `snake_case` functions/variables, `PascalCase` classes, uppercase constants.
- Use Google-style docstrings for public messaging APIs as required by `insights-ccx-messaging/AGENTS.md`; elsewhere follow local convention.
- Preserve and extend existing type hints. Do not introduce a new strict typing policy as part of unrelated work.
- Keep imports grouped and Ruff-sorted; avoid wildcard imports.
- Logger names vary (`LOG`, `log`, `logger`). Match surrounding module.

### Logging

Use `python-json-logger` for structured JSON logging throughout. Follow the established pattern:

```python
import logging

LOG = logging.getLogger(__name__)

LOG.info("Processing message from topic '%s'", topic_name)
LOG.error("Failed to connect to Kafka: %s", error_msg)
LOG.debug("Cluster ID: %s, org_id: %s", cluster_id, org_id)
LOG.warning("Message age exceeded threshold: %d seconds", elapsed)
```

Key patterns:
- Use lazy `%s` arguments for logging instead of formatting strings eagerly.
- Pass context as arguments: `LOG.info("Processing %s from %s", item, source)`.
- Use `LOG.exception("operation failed")` inside an exception handler when traceback is useful.
- Choose level by impact: debug for diagnostics, warning for recoverable abnormal states, error for failed operations.
- CloudWatch logging may add a Watchtower handler; preserve existing conditional setup.
- Never log credentials, tokens, raw authorization headers, customer payloads, account numbers, or PII.

Never use `print()` for application logging. CLI output explicitly intended for users is exception.

### Error Handling

Two patterns used across repos:

**Custom exceptions** (Kafka repos — `insights-ccx-messaging`):
```python
class CCXMessagingError(Exception):
    """Base exception for all messaging errors."""
    pass

class SpecificError(CCXMessagingError):
    """More specific error with context."""
    pass
```

**Standard exceptions** (FastAPI repos):
```python
from fastapi import HTTPException, status

raise HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Unable to initialize SSO session",
)
```

Shared guidance:
- Catch specific exceptions when practical. Broad catches belong only at process, request, or integration boundaries where failure is translated or contained.
- Preserve causes with exception chaining: `raise SpecificError(...) from ex`.
- Avoid logging and re-raising at every layer; log once where enough context exists or where failure is handled.
- Messaging custom exceptions live in `error.py`; FastAPI service-specific exceptions may live near integration code.
- Convert expected API failures to intentional HTTP status codes and safe details. Do not expose upstream response bodies, tokens, or internal tracebacks.
- Validate untrusted Kafka messages, HTTP inputs, URLs, and archive metadata before use.

### Security and Data Handling

- Never commit credentials, tokens, certificates, customer payloads, or environment-specific secrets.
- Read Kafka, S3, SSO, and API credentials from Clowder/configured environment sources.
- Keep TLS verification enabled. Use repository CA-bundle configuration instead of disabling certificate checks.
- Validate incoming messages against existing JSON schemas before processing or publishing.
- Respect archive-size limits and defend extraction code against path traversal and decompression abuse.
- Add finite timeouts to new external HTTP calls and preserve established retry/backoff behavior.
- Return sanitized API errors. Send detailed diagnostics to controlled logs/Sentry without sensitive data.
- Treat dependency, base-image, and authentication changes as security-sensitive; run available scans and tests.

### Project Layout

**Kafka message processing repos** (Pattern A):
```
/ccx_messaging/          - Main source code (all importable components)
  /consumers/            - Kafka message consumers
  /publishers/           - Kafka message publishers
  /engines/              - Processing engines
  /downloaders/          - Archive downloaders (HTTP, S3)
  /watchers/             - Monitoring components
  /utils/                - Utility functions (logging, kafka_config, sentry, etc.)
  command_line.py        - CLI entry point
  schemas.py             - JSON schemas for message validation
  ingress.py             - Message parsing and validation
  error.py               - Custom exception classes
/test/                   - Test files (mirror src structure)
  *_test.py              - Unit tests (suffix: _test.py)
/deploy/                 - Deployment configurations
```

**FastAPI REST API repos** (Pattern B):
```
/ccx_upgrades_data_eng/  - Main source code
  main.py                - FastAPI app, routes, middleware
  config.py              - Settings (pydantic-settings)
  models.py              - Pydantic response/request models
  metrics.py             - Prometheus metrics
  auth.py                - SSO/session management
  inference.py           - Business logic
  utils.py               - Utilities (retry, sentry)
  /tests/                - Test files
    test_main.py         - Endpoint tests
```

Always follow the existing layout of the repo you are working on.

### Testing

**Framework**: pytest with `pytest-cov` for coverage.

**Key patterns**:
- Messaging CLI tests use `pytest.raises(SystemExit)` for exit-code behavior.
- FastAPI endpoint tests use `fastapi.testclient.TestClient` or `httpx` according to local tests.
- Environment-dependent tests isolate state with `patch.dict`; clear cached settings/session factories when needed.
- Mock at lookup site with `unittest.mock.patch`, not necessarily where symbol was originally defined.
- Use `freezegun` for time control where installed; use `pytest-asyncio` for async tests, not as a time-mocking tool.
- Keep tests offline and deterministic. Mock Kafka, S3, SSO, Observatorium, inference, and other external boundaries.

**Kafka repo test pattern**:
```python
import sys
import pytest
import ccx_messaging.command_line as command_line

def test_command_line_args_valid_flag_version():
    """Verify correct parsing of --version flag."""
    sys.argv = ["ccx-messaging", "--version"]
    parser = command_line.parse_args()
    assert not parser.config
    assert parser.version

def test_command_line_args_no_config_provided(capsys):
    """Verify app does not start if no config provided."""
    with pytest.raises(SystemExit) as exception:
        sys.argv = ["ccx-messaging"]
        command_line.ccx_messaging()

    assert exception.type is SystemExit
    assert exception.value.code == 1
```

**FastAPI repo test pattern**:
```python
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

from ccx_upgrades_data_eng.main import app

client = TestClient(app)

@patch.dict(os.environ, needed_env)
@patch("ccx_upgrades_data_eng.main.get_session_manager")
def test_endpoint(get_session_manager_mock):
    """Test endpoint returns expected response."""
    response = client.get("/some/endpoint")
    assert response.status_code == 200
    content = response.json()
    assert content["field"] == expected_value
```

**Test file naming**:
- Kafka repos: `*_test.py` (e.g., `kafka_consumer_test.py`)
- Current FastAPI service: tests live under `ccx_upgrades_data_eng/tests/` and use `test_*.py`

**Test dependencies**:
- Kafka repos: `pytest`, `pytest-cov`, `freezegun`
- FastAPI repos: `pytest`, `pytest-cov`, `pytest-asyncio`, `httpx`

---

## Dependency Management

### Adding/Updating Dependencies

1. **Identify dependency sources**: inspect `pyproject.toml`, `requirements*.txt`, container install commands, and CI. Some repos intentionally maintain more than one list.
2. **Edit canonical metadata**: add or update `[project.dependencies]` or the relevant optional extra.
   ```toml
   dependencies = [
       "existing-package>=1.0",
       "new-package==2.0.0",
   ]
   ```
3. **Keep required mirrors synchronized**: if runtime or CI installs `requirements.txt`, update it consistently. Do not generate a lock file unless repo already uses one.
4. **Install declared extras**:
   ```bash
   python -m pip install -e ".[test]"
   ```
   Add `dev` only when defined.
5. **Run repository-native tests and pre-commit**.

### Known Current Constraints

Constraints change. Confirm them in current files and dependency resolver before editing.

- `insights-ccx-messaging` currently caps boto3 because of aiobotocore/s3fs compatibility.
- Messaging uses `confluent-kafka`, not `kafka-python`.
- `insights-core-messaging` is exactly pinned in current project metadata; preserve exactness unless task explicitly changes it.
- FastAPI service dependencies include several exact pins. Do not convert exact pins to ranges during unrelated work.

---

## Linting Configuration

### Ruff

Ruff policy can be split between `pyproject.toml` and pre-commit arguments. Read both. For example, messaging defines line length and docstring rules in `pyproject.toml`, while current shared pre-commit invokes `ruff-check` with its own selected rules and `--fix`.

Common families include:
- **E/W** — pycodestyle.
- **F** — Pyflakes.
- **UP** — pyupgrade.
- **I** — import sorting.
- **N** — naming.
- **B** — bugbear.
- **C4** — comprehension rules.
- **SIM** — simplification rules.
- **D** — pydocstyle where enabled.

Run `pre-commit run --all-files ruff-check`; then `pre-commit run --all-files ruff-format`. Review auto-fixes before committing.

### Pre-commit Hooks

Current example repos share a generated-style pre-commit baseline, but pins and hook sets can drift. Typical hooks:
- `end-of-file-fixer`, `trailing-whitespace`
- `check-json`, `check-toml`, `check-yaml`
- `debug-statements`, `mixed-line-ending`, `check-ast`, `check-merge-conflict`
- `shellcheck` (with exclusions SC1090, SC2086, SC2034, SC1091)
- `golangci-lint-config-verify`, `golangci-lint-full` (shared processing-tools hooks)
- `abcgo` (threshold 64), `go-version-consistency` (shared processing-tools hooks)
- `ruff-check` (with `--fix`, select UP,F632,E,W,F,I,N,B,C4,SIM), `ruff-format`
- `renovate-config-validator`

Run all: `pre-commit run --all-files`

---

## Maintenance Task Workflows

### Dependency Updates

1. **Identify dependency, target version, and every file that declares it.**
2. **Run baseline checks** using repo-native commands.
3. **Preserve repository pinning policy** unless ticket requests a policy change.
4. **Update canonical metadata and required mirrors** such as `requirements.txt`.
5. **Recreate clean virtual environment or force resolver to evaluate changed constraints.** A previously satisfied environment can hide conflicts.
6. **Run tests, coverage checks, and pre-commit.** Exercise every supported Python version through tox/CI when compatibility changed.
7. **If tests fail**, inspect changelog and migration notes; adapt signatures, imports, behavior, or test doubles as needed.
8. **Document code changes beyond dependency metadata** in PR and Jira resolution.
9. **Commit all synchronized dependency files**, not only `pyproject.toml`.

### Lint Fixes

1. Run `pre-commit run --all-files ruff-check` or repo Make target.
2. Review auto-fixes; repair remaining findings file by file.
3. Run `pre-commit run --all-files ruff-format` or `make pyformat` where available.
4. Re-run complete pre-commit suite.
5. Run tests after lint fixes. Formatting and modernization can alter imports, strings, and runtime behavior.

### Test Fixes

1. Run repo-native tests (`make unit_tests`, `tox`, or `python -m pytest -v`) to identify failures
2. Read the test error output carefully — distinguish between:
   - **Assertion failures**: expected vs actual values don't match — update expected values if the change was intentional, or fix the code
   - **Import errors**: usually from API changes — update imports to match new module structure
   - **Type errors**: identify changed runtime/API contract; fix implementation and annotations together rather than weakening checks
   - **Mock mismatches**: `@patch` targets changed — update mock paths
3. Never delete tests to make the suite pass — fix them or explain why they are obsolete
4. If adding new functionality, write tests covering the happy path and key error cases

### Bug Fixes

1. **Reproduce the bug**: understand the issue from the Jira ticket, then write a failing test
2. **Fix the code**: make the failing test pass with the minimal change needed
3. **Verify**: run the full test suite to ensure no regressions
4. **Document**: PR description should explain what was broken, why, and how the fix works

### New Feature Implementation

1. **Understand the requirements**: read the Jira ticket thoroughly. If requirements are unclear, ask for clarification before starting.
2. **Identify the application pattern**:
   - **Kafka message processing**: Follow the Consumer/Publisher/Engine plugin architecture from `insights-core-messaging`
   - **FastAPI REST API**: Follow the FastAPI route + Pydantic model pattern
3. **Check existing patterns**: look at how similar features are implemented in the same repo. Follow the same patterns for consistency.
4. **Plan the implementation**:
   - Identify which files/packages need changes
   - Consider error cases and edge conditions
   - Consider backward compatibility
5. **Implement incrementally**:
   - Start with types/models/config
   - Implement the core logic
   - Add logging and error handling
   - Wire into existing code (CLI entry, routes, consumers, etc.)
6. **Write tests**: follow the repo's existing test patterns (pytest with `TestClient` for FastAPI, CLI exit testing for Kafka repos)
7. **Run full verification** with repo-native test and pre-commit commands.
8. **Document** behavior, configuration, API/message contract, and deployment impact.

### CI Pipeline Issues

CI pipelines are defined in `.tekton/` (Tekton) and `.github/` (GitHub Actions). When debugging failures:

- **Build failures**: build/install in a clean virtual environment and check resolver output, package discovery, and `setuptools_scm` Git metadata.
- **Test failures**: reproduce with exact CI Python version and command. Check mocked Kafka, S3, SSO, API, and environment assumptions.
- **Lint failures**: run full pre-commit and inspect both `.pre-commit-config.yaml` and `pyproject.toml`.
- **Coverage failures**: match tox/CI flags and threshold rather than running plain pytest only.
- **Python-version failures**: compare `requires-python`, workflow matrix, Docker interpreter, and syntax introduced by Ruff/pyupgrade.
- **Generated workflow failures**: GitHub workflow headers may say they are synced from `RedHatInsights/processing-tools`; fix source workflow or update pinned reusable workflow instead of editing generated downstream files blindly.
- **Tekton failures**: inspect `.tekton/` parameters, Docker build context, output image, and target branch conditions.

---

## Container Image

### Building Locally

```bash
CONTAINER_CMD=$(command -v podman || command -v docker)
$CONTAINER_CMD build . -t <repo-name>:local
```

If the repo has multiple Dockerfiles, use the non-hermetic one (plain `Dockerfile`) since that's closest to what CI builds.

### Dockerfile Patterns

Current repos use `ubi9-minimal`, Python 3.11, an application-local virtual environment, and non-root UID 1001. Preserve repo-specific details.

**Messaging package**:
- Uses named `base` and `final` stages.
- Installs `requirements.txt` and then project package.
- Removes build/runtime packages in final stage.
- Has no universal `CMD`; deployment selects CLI and configuration.

**FastAPI service**:
- Installs project from `pyproject.toml` with `pip install .`.
- Removes pip and unneeded RPMs after installation.
- Exposes port 8000.
- Runs `uvicorn ccx_upgrades_data_eng.main:app` with repo logging configuration.

For every image:
- Keep CA trust settings needed for Red Hat endpoints.
- Do not bake secrets or environment-specific credentials into layers.
- Keep runtime non-root.
- Re-scan image after base-image or dependency changes.

### Base Image Updates

When updating the base image:

1. Open the `Dockerfile`, find `FROM` statement
2. Update image tag
3. Rebuild: `$CONTAINER_CMD build . -t <repo-name>:test`
4. Run repository-appropriate smoke check. Messaging image may require plugin config; FastAPI image requires environment and an HTTP health check. Do not assume every image supports `--help`.
5. Review security scan and installed runtime package changes.
6. Commit the updated `Dockerfile`.

---

## Package Release

`insights-ccx-messaging` publishes `ccx-messaging` to PyPI using `setuptools_scm` and a GitHub Actions trusted-publishing workflow.

- Version comes from Git tags; do not add a hardcoded package version.
- Release tags use `vMAJOR.MINOR.PATCH` and must point to tested `main` commits.
- Verify wheel and source distribution with `python -m build` when release behavior changes.
- Never create or push release tags unless ticket explicitly authorizes release.
- Workflow files marked as synced from `RedHatInsights/processing-tools` must be changed at their source or through documented sync flow.

---

## Jira Integration

### Reading Tickets

Fetch ticket details using the Jira MCP tools or CLI:

```bash
jira issue view CCXDEV-XXXXX --plain
```

### Posting Assessment Comments

**Before starting work**, post an assessment comment:

```
**Assessment**

**Issue**: <brief description of the task>
**Affected files**: <list of files that need changes>
**Plan**: <what will be done>
**Risk**: <Low/Medium — impact assessment>
```

### Posting Resolution Comments

After fixing and creating a PR:

```
**Resolution: <Dependency update / Bug fix / Feature implementation / Lint fix / Test fix / CI fix>**

**Changes**:
- <list of changes made>

**Verification**:
- Tests: passing (`<exact repo test command>`)
- Lint/format: passing (`<exact repo pre-commit or Make command>`)

<If codebase changes were needed beyond a dependency bump:>
**Note**: This update required codebase modifications beyond the dependency bump. Please review carefully.
**Codebase changes**:
- <list each change made to accommodate the update>

**PR**: <PR_URL>
```

### Ticket Transitions

After PR is created and Jira comment posted:
- Transition ticket to "Code Review"

---

## PR Creation

When creating PRs:
- PR title should be clear and descriptive, explaining the "why" rather than only the changed file.
- Include Jira ID when work maps to one ticket: `[CCXDEV-12345] Description of change`.
- Use descriptive commit messages; no strict conventional-commit format is required.
- Follow repository review requirements; current messaging guidance requires two core-team reviews.

### PR Template

Before creating a PR, check if the repo has a `PULL_REQUEST_TEMPLATE.md` in the repo root:

```bash
[ -f PULL_REQUEST_TEMPLATE.md ] && echo "PR template found"
```

If the template exists:
1. **Read the template** to understand its structure and required sections
2. **Fill out every section** of the template with relevant information from your changes
3. **Do not leave placeholder text** — replace all `<!-- comments -->`, `[TODO]`, or example text with actual content
4. **Pass the filled template** as the PR body via `gh pr create --body`

Additional sections beyond the template are allowed, but only after all template sections are filled out first.

If no PR template exists, use the default PR body format with a summary of changes and verification steps.

### Attribution

**Always add a comment after PR creation:**

```bash
gh pr comment <number> --body "Created by Ctibor (autonomous dev bot). Please review carefully before merging."
```

If codebase changes were made beyond a simple dependency bump:

```bash
gh pr comment <number> --body "⚠️ This PR includes codebase changes beyond the dependency update. Please test the application to verify everything works as before."
```

---

## Production Image Update (app-interface)

For deployed services whose release flow requires manual image promotion, update production through an `app-interface` Merge Request after source PR merges. Do not run this workflow for library-only releases or services documented as automatically promoted. Confirm repo `AGENTS.md`, team-info, and deployment docs first.

### Workflow

1. **Get the merged commit SHA**: After the PR is merged, retrieve the full commit SHA from the merge commit. This is used as the image tag.

2. **Wait for the image to be available in Quay**: Before creating the MR, verify that the image is present in the registry. Check availability:
   ```bash
   skopeo inspect docker://quay.io/redhat-services-prod/obsint-processing-tenant/<component>/<component>:latest
   ```
   Check every 15 minutes, with a maximum of 3 retries. If not available after 3 retries, notify the user and stop.

3. **Find the service deployment configuration**:
   - Look in `data/services/insights/` in the `app-interface` repo
   - Find the file that references the service image
   - Locate the `ref:` field with the current image tag

4. **Update the image tag**: Replace the current `ref:` value with the full merged commit SHA.

5. **Create the Merge Request**:
   ```bash
   glab mr create --repo service/app-interface \
     --title "Update <service> image tag to <short-commit-sha>" \
     --description "Update image tag after merging <PR_URL>"
   ```

6. **Add attribution comment**:
   ```bash
   glab mr note <number> --message "Created by Ctibor (autonomous dev bot). Please review carefully before merging."
   ```

7. **Link the MR** in the Jira ticket comment and update the ticket status accordingly.

### Important

- App-interface MRs **always** require human review — never auto-merge
- The image tag is always the full commit SHA from the merged commit
- Always wait for the image to appear in Quay before creating the MR

---

## Slack Notifications

Send Slack notifications using the `SLACK_WEBHOOK_URL` environment variable after completing tasks:

```bash
curl -X POST "${SLACK_WEBHOOK_URL}" \
  -H 'Content-Type: application/json' \
  -d "{\"text\": \"YOUR_MESSAGE_HERE\"}"
```

Include: what was changed, which repo, PR link, and Jira ticket link.

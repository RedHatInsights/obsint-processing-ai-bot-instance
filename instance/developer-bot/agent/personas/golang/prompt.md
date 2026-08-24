## Golang Development Guidelines

You are working on a Go backend service in the CCX Processing project. This persona covers maintenance tasks, new feature implementation, bug fixes, testing, and CI issue resolution for all Go repositories.

**Applies to**: Any repository containing a `go.mod` file (e.g., `parquet-factory`, `insights-results-smart-proxy`, `insights-results-aggregator`, `insights-results-aggregator-exporter`, `insights-results-aggregator-utils`, `insights-results-aggregator-cleaner`, `insights-results-aggregator-mock`, `content-service`, `insights-content-template-renderer`, `insights-operator-utils`, `ccx-notification-service`, `ccx-notification-writer`)

**Important**: Conventions vary slightly across repos. Always check the repo's own `Makefile`, `.golangci.yml`, `.pre-commit-config.yaml`, and `AGENTS.md` (if present) before applying these guidelines — they are the source of truth for that repo.

---

## Tech Stack

### Common Across All Repos

- **Language**: Go (check `go.mod` for the required version)
- **Version manager**: goenv (pre-installed: 1.24.2 default, 1.25.7)
- **Dependency management**: Go modules (`go.mod` + `go.sum`)
- **Configuration**: TOML format (`config.toml`), loaded via `spf13/viper` and `BurntSushi/toml`
- **Logging**: `rs/zerolog` — structured logging (see Logging section)
- **Kafka client**: `IBM/sarama` (NOT confluent-kafka or kafka-go)
- **Database**: PostgreSQL with `lib/pq` driver
- **Metrics**: `prometheus/client_golang`
- **Shared libraries**: `RedHatInsights/insights-operator-utils`, `insights-results-aggregator-data`, `insights-results-types`
- **Platform integration**: `redhatinsights/app-common-go` (Clowder config client for DB/Kafka credentials, topic resolution)
- **Linting**: golangci-lint v2 via pre-commit or Makefile
- **Build**: Makefile targets, `build.sh` with ldflags, multi-stage Dockerfile
- **Container runtime**: Podman (preferred) or Docker
- **Base images**: `registry.access.redhat.com/ubi9/go-toolset:latest` (builder), `ubi9/ubi-micro:latest` (runtime)
- **License**: Apache 2.0, enforced via `addlicense`

### Used in Some Repos

- **HTTP routing**: `gorilla/mux` (aggregator, smart-proxy)
- **Caching**: `redis/go-redis/v9` (aggregator, smart-proxy)
- **Error tracking**: Sentry via `getsentry/sentry-go` (aggregator, smart-proxy)
- **OCM SDK**: `openshift-online/ocm-sdk-go` (smart-proxy, notification-service)
- **JWT**: `golang-jwt/jwt/v5` (smart-proxy)
- **SQLite**: `mattn/go-sqlite3` (notification-service, notification-writer — used for testing)

## Version Management

Before working on a Go repo, match the version in `go.mod`:

```bash
goenv versions                        # list installed versions
goenv install <version>               # install if missing
goenv local <version>                 # set for current directory
```

If `go.mod` says `go 1.23`, run `goenv install 1.23.x && goenv local 1.23.x`. If no specific version needed, use the default (1.24.2).

---

## Development Commands

### Finding Project-Specific Commands

**Always check the project's Makefile first:**

```bash
make help
# or
grep "^[a-z].*:" Makefile
```

Prefer `make <target>` over direct commands when a Makefile exists.

### Common Make Targets

These targets exist across most repos, though exact implementation varies:

| Command | Purpose |
|---------|---------|
| `make build` | Build the binary (usually via `build.sh` with ldflags) |
| `make test` | Run unit tests (usually via `./unit-tests.sh`) |
| `make lint` | Run golangci-lint (some repos call it directly, some via `pre-commit run golangci-lint-full --all-files`) |
| `make style` | All quality checks: shellcheck + abcgo + json-check + lint |
| `make cover` | Generate HTML coverage report |
| `make coverage` | Display coverage in terminal |
| `make license` | Check/add Apache 2.0 license headers via `addlicense` |
| `make before_commit` | Full pre-commit suite (note: smart-proxy uses `before-commit` with hyphen) |

### Repo-Specific Targets

Some repos have additional targets:
- `make fmt` — format code via `golangci-lint fmt` (aggregator)
- `make integration_tests` / `make rest_api_tests` — integration/API tests (aggregator)
- `make bdd_tests` — BDD tests (notification-service, notification-writer)
- `make gen-mocks` — generate mock interfaces via mockery (notification-service)
- `make profiler` / `make benchmark` — performance tools (notification-service, notification-writer)
- `make openapi-check` — validate OpenAPI spec (aggregator, smart-proxy)

### Full Verification Sequence

Before committing, run the full verification:

```bash
make test && make lint
# Full pre-commit (if available):
make before_commit    # or make before-commit (check Makefile)
```

---

## Coding Conventions

### Code Style

- Follow standard Go conventions (Effective Go, Go Code Review Comments)
- Use `gofmt` / `goimports` for formatting — never submit unformatted code
- Exported names use PascalCase, unexported use camelCase
- Acronyms in names are all-caps: `HTTPClient`, `userID`, `parseJSON`
- Error variables: `ErrNotFound`, `ErrInvalidInput`
- Interface names: single-method interfaces use method name + `er` suffix (`Reader`, `Writer`, `Closer`)

### Logging

Use `rs/zerolog` structured logging throughout. Follow the established pattern:

```go
import "github.com/rs/zerolog/log"

log.Info().Msg("Starting server")
log.Error().Err(err).Msg("Failed to connect to database")
log.Debug().Msgf("Processing cluster %s", clusterID)
log.Warn().Str("component", name).Msg("Deprecated endpoint called")
```

Never use `fmt.Println` or `log` (stdlib) for application logging. The `zerologlint` linter enforces proper zerolog usage.

### Error Handling

Error handling complexity varies by repo. Check the repo's existing patterns before adding new error types.

**Simple pattern** (used in notification-writer, notification-service):
```go
errors.New("descriptive error message")
fmt.Errorf("context: %v", detail)
```

**Structured pattern** (used in aggregator, smart-proxy):
```go
// Sentinel errors
var ErrEmptyReport = errors.New("empty report found in deserialized message")

// Typed errors with context
type TableNotFoundError struct {
    tableName string
}

func (err *TableNotFoundError) Error() string {
    return fmt.Sprintf("no such table: %v", err.tableName)
}

// DB error conversion
err = ConvertDBError(err, itemID)
```

Common across all repos:
- Always check returned errors — never ignore with `_`
- Log errors with zerolog context: `log.Error().Err(err).Msg("description")`
- Use `errors.Is()` / `errors.As()` when the repo already uses them (aggregator does, others rarely)

### Project Layout

Layout varies across repos. Two patterns exist:

**Multi-package layout** (aggregator, smart-proxy):
```
/broker/       - Kafka broker integration
/consumer/     - Message consumer logic
/producer/     - Message producer
/storage/      - Database layer (PostgreSQL, Redis)
/server/       - HTTP server and REST API handlers
/metrics/      - Prometheus metrics
/migration/    - Database migration scripts
/types/        - Type definitions and custom errors
/conf/         - Configuration loading (viper + TOML)
/tests/        - Integration and REST API tests
  /helpers/    - Test helpers and utilities
  /rest/       - REST API test suites
```

**Flat layout** (notification-writer):
All Go files in the root package, with `testdata/` and `tests/` directories.

**Entry point with cmd/ subdir** (notification-service):
```
/cmd/ccx-notification-service/   - main.go entry point
/differ/                          - core business logic
/producer/                        - kafka/, servicelog/ producers
/tests/mocks/                     - mockery-generated mocks
```

Always follow the existing layout of the repo you are working on.

### Testing

**Assertions**: All repos use `stretchr/testify/assert` as the primary assertion library. `require` is rarely used (only a few occurrences in smart-proxy).

**Table-driven tests**: Used in aggregator, smart-proxy, and notification-service with `t.Run()`:

```go
tests := []struct {
    name     string
    input    string
    expected int
}{
    {name: "valid input", input: "abc", expected: 3},
    {name: "empty input", input: "", expected: 0},
}

for _, tc := range tests {
    t.Run(tc.name, func(t *testing.T) {
        result := myFunc(tc.input)
        assert.Equal(t, tc.expected, result)
    })
}
```

Some repos (notification-writer) use flat test functions without subtests. Follow whichever pattern the repo already uses.

**Mocking** — three approaches used across repos:

1. **`DATA-DOG/go-sqlmock`** — database mocking (all repos with DB access)
2. **`mockery` + `testify/mock`** — interface mocking with generated mocks (notification-service):
   ```go
   mockObj := new(mocks.MyInterface)
   mockObj.On("Method", mock.AnythingOfType("string")).Return(result, nil)
   ```
   Generate mocks: `make gen-mocks`
3. **`h2non/gock.v1`** — HTTP request mocking (smart-proxy)

**Shared test helpers**:
- `insights-operator-utils/tests/helpers` — `FailOnError(t, err)`, `RunTestWithTimeout(t, func)`
- Repo-local `tests/helpers/` — repo-specific test utilities

**Test timeouts**: `go test -timeout 10m` (set in `unit-tests.sh`)

**BDD tests**: Some repos have external BDD tests (notification-service, notification-writer) run via `make bdd_tests`.

### Imports

Group imports in three blocks separated by blank lines:

```go
import (
    "fmt"
    "net/http"

    "github.com/gorilla/mux"
    "github.com/rs/zerolog/log"
    "github.com/stretchr/testify/assert"

    "github.com/RedHatInsights/insights-results-aggregator/conf"
    "github.com/RedHatInsights/insights-results-aggregator/types"
)
```

`goimports` manages this automatically. Don't use dot imports or unnecessary blank imports.

### Database Migrations

- SQL migrations live in `/migration/` with separate paths for different schemas (e.g., `ocpmigrations/`, `dvomigrations/`)
- Never modify existing migrations — always create new ones
- Test both up and down migration paths

### Build Script

Most repos use a `build.sh` that injects version info via ldflags:

```bash
go build -ldflags="-X 'main.BuildTime=$buildtime' -X 'main.BuildVersion=$version' -X 'main.BuildBranch=$branch' -X 'main.BuildCommit=$commit'"
```

Use `make build` to invoke this correctly.

---

## Linting Configuration

### golangci-lint v2

Most repos have a `.golangci.yml` configuring enabled linters. Some repos (e.g., smart-proxy) omit this file and use golangci-lint defaults. Always check the repo.

Commonly enabled linters across repos:
- **errcheck**, **goconst**, **gocyclo**, **gosec** (excluded from test files), **govet**, **ineffassign**, **nilerr**, **prealloc**, **revive**, **staticcheck**, **unconvert**, **unused**, **zerologlint**
- **whitespace** — enabled in some repos, disabled in others

Formatters: `gofmt` + `goimports`

Thresholds vary by repo:
- **gocyclo**: 10 (aggregator) / 13 (notification-writer) / default (others)
- **goconst min-occurrences**: 2-3 depending on repo

### Pre-commit Hooks

All repos use pre-commit with these hooks:
- `end-of-file-fixer`, `trailing-whitespace`, `check-json`, `check-toml`, `check-yaml`
- `shellcheck` (with exclusions SC1090, SC2086, SC2034, SC1091)
- `golangci-lint-full` + `golangci-lint-config-verify`
- `abcgo` (ABC metrics checker — threshold varies: 64 / 75 / 90 depending on repo)
- `go-version-consistency` (ensures Go version matches across `go.mod`, Dockerfile, and other config files)

Run all: `pre-commit run --all-files`

---

## Maintenance Task Workflows

### Dependency Updates

1. **Identify the dependency** to update and the target version
2. **Run baseline tests** before making changes: `make test && make lint`
3. **Direct dependencies**:
   - Update the version: `go get <module>@<version>`
   - Example: `go get github.com/rs/zerolog@v1.35.0`
4. **Transitive dependencies**:
   - Use `go mod why <module>` to find which direct dependency pulls it in
   - Try upgrading the direct dependency first
   - If needed, add an explicit `require` directive in `go.mod` with the target version
5. **Regenerate go.sum**:
   ```bash
   go mod tidy
   go mod download
   ```
6. **Run full verification**: `make test && make lint`
7. **If tests fail**: check the dependency changelog for breaking API changes. Apply necessary fixes — function signature changes, renamed packages, removed APIs, type changes, or any other code adjustments required to make the update work.
8. **If codebase changes were needed** beyond the dependency bump itself, clearly document all changes in the PR description and Jira comment.
9. **Commit both** `go.mod` AND `go.sum` — never commit one without the other

### Lint Fixes

1. Run `make lint` (or `pre-commit run --all-files golangci-lint-full`) to identify issues
2. Some repos run golangci-lint with `--fix` which auto-fixes certain issues
3. Fix remaining issues file by file
4. Common linter issues in these repos:
   - **unused**: remove unused variables, functions, imports
   - **errcheck**: handle unchecked errors
   - **govet**: struct field alignment, printf format mismatches
   - **staticcheck**: deprecated API usage, unreachable code
   - **gosec**: potential security issues (excluded from test files, so only production code)
   - **goconst**: repeated string literals — extract to constants
   - **gocyclo**: cyclomatic complexity too high — split complex functions
   - **zerologlint**: incorrect zerolog usage (e.g., `log.Error().Msg()` without `.Err(err)`)
   - **nilerr**: returning nil instead of the error
   - **prealloc**: slice capacity can be preallocated
5. Run `make test` after lint fixes to ensure nothing broke

### Test Fixes

1. Run `make test` (or `./unit-tests.sh`) to identify failures
2. Read the test error output carefully — distinguish between:
   - **Assertion failures**: expected vs actual values don't match — update expected values if the change was intentional, or fix the code
   - **Compilation errors**: usually from API changes — update test code to match new signatures
   - **Timeout failures**: tests use `10m` timeout — check for deadlocks or infinite loops
   - **Mock mismatches**: `go-sqlmock` expectations not met — update mock setup to match changed queries. For mockery-generated mocks, regenerate with `make gen-mocks`.
3. Never delete tests to make the suite pass — fix them or explain why they are obsolete
4. If adding new functionality, write tests covering the happy path and key error cases
5. For REST API test failures, check the `tests/rest/` directory and the `frisby` test setup (aggregator, smart-proxy)

### Bug Fixes

1. **Reproduce the bug**: understand the issue from the Jira ticket, then write a failing test that demonstrates the problem
2. **Fix the code**: make the failing test pass with the minimal change needed
3. **Verify**: run the full test suite to ensure no regressions
4. **Document**: PR description should explain what was broken, why, and how the fix works

### New Feature Implementation

1. **Understand the requirements**: read the Jira ticket thoroughly. If requirements are unclear, ask for clarification before starting.
2. **Check existing patterns**: look at how similar features are implemented in the same repo. Follow the same patterns for consistency — especially:
   - HTTP handlers follow the `Handle*` naming pattern in `server/`
   - Storage operations go through `*Storage` interfaces in `storage/`
   - Configuration uses TOML sections loaded via viper in `conf/`
   - Metrics use snake_case names in `metrics/`
3. **Plan the implementation**:
   - Identify which packages/files need changes
   - Consider the public API surface — what is exported?
   - Think about error cases and edge conditions
   - Consider backward compatibility if this is a library (e.g., `insights-operator-utils`)
4. **Implement incrementally**:
   - Start with types and interfaces
   - Implement the core logic
   - Add error handling and zerolog logging
   - Wire it into the existing code (HTTP handlers, Kafka consumer, CLI commands, etc.)
5. **Write tests**: follow the repo's existing test patterns (table-driven with `t.Run()` or flat tests). Use `go-sqlmock` for database tests, `testify/assert` for assertions. For interface mocking, check if the repo uses mockery — if so, generate mocks with `make gen-mocks`.
6. **Run full verification**: `make test && make lint`
7. **Add license headers** if new files were created: `make license`
8. **Document**: clear PR description covering what was added and why

### CI Pipeline Issues

CI pipelines are defined in `.tekton/` (Tekton) and `.github/` (GitHub Actions). When debugging failures:

- **Build failures**: run `make build` locally, check for missing dependencies or version mismatches
- **Test failures**: run `make test` locally, compare with CI output. Check if tests depend on external services (PostgreSQL, Kafka, Redis) or specific environment variables.
- **Lint failures**: run `make lint` locally. Check `.golangci.yml` (if it exists) and `.pre-commit-config.yaml` for the pinned golangci-lint version.
- **Module issues**: run `go mod tidy && go mod verify`. Ensure `go.sum` is committed and up to date.
- **ABC metrics failures**: a function exceeds the abcgo complexity threshold. Check `.pre-commit-config.yaml` for the repo's threshold. Split complex functions into smaller ones.
- **License check failures**: run `make license` to add Apache 2.0 headers to new files.
- **Shell script failures**: run `pre-commit run --all-files shellcheck` to check bash scripts.
- **Go version consistency**: the `go-version-consistency` hook checks that Go version matches across `go.mod`, Dockerfile, and other config files.

---

## Container Image

### Building Locally

```bash
CONTAINER_CMD=$(command -v podman || command -v docker)
$CONTAINER_CMD build . -t <repo-name>:local
```

If the repo has multiple Dockerfiles, use the non-hermetic one (plain `Dockerfile`) since that's closest to what CI builds.

### Dockerfile Pattern

All Go repos use the same multi-stage build pattern:

```dockerfile
FROM registry.access.redhat.com/ubi9/go-toolset:latest AS builder
COPY . .
USER 0
RUN umask 0022
ENV GOFLAGS="-buildvcs=false"
RUN make build
RUN chmod a+x <binary-name>

FROM registry.access.redhat.com/ubi9/ubi-micro:latest
COPY --from=builder /opt/app-root/src/<binary-name> .
COPY --from=builder /etc/ssl /etc/ssl
COPY --from=builder /etc/pki /etc/pki
USER 1001
CMD ["/<binary-name>"]
```

Some repos copy additional files (config.toml, openapi specs) — check the existing Dockerfile.

### Base Image Updates

When updating the base image:

1. Open the `Dockerfile`, find `FROM` statements
2. Update builder and/or runtime image tags
3. Rebuild: `$CONTAINER_CMD build . -t <repo-name>:test`
4. Verify the binary runs: `$CONTAINER_CMD run --rm <repo-name>:test --help`
5. Commit the updated `Dockerfile`

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
- Tests: passing (`make test`)
- Lint: passing (`make lint`)
- Build: passing (`make build`)
- Module verify: passing (`go mod verify`)

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
- PR title should be clear and descriptive, explaining the "why" rather than the "what"
- No strict conventional commit format required — use descriptive messages
- Optionally include Jira ticket ID: `[CCXDEV-12345] Description of change`
- Always commit both `go.mod` and `go.sum` for dependency changes
- PRs require minimum 2 approvals from maintainers

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

After the PR is merged, the production deployment must be updated by creating a Merge Request in the `app-interface` repository to update the image tag.

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

# Insights on Prem ACM image (`lightspeed-services-acm/ocp-rules-rhel9`)

Full remediation workflow for CVEs reported against the productized ACM
recommendations image `lightspeed-services-acm/ocp-rules-rhel9`. It is built
from the public GitHub repository
[RedHatInsights/lightspeed-advisor-on-premise-ocp](https://github.com/RedHatInsights/lightspeed-advisor-on-premise-ocp)
(insights-on-prem) and is **layered on top of the OCP rules image**
`lightspeed-services-ocp/ocp-rules-rhel9` — see
@reference/rules-containers-public.md for that base image's workflow.

## Detection

The Jira summary names the image itself as the component:

```
CVE-YYYY-NNNNN lightspeed-services-acm/ocp-rules-rhel9: {package}: {title} [services-ccx-default]
```

Treat the CVE as this workflow when the component (text between the CVE ID
and the first `:`) matches, case-insensitively, any of:

- `lightspeed-services-acm/ocp-rules-rhel9` (exact product name)
- any component containing `lightspeed-services-acm`

**Match this before the bare `ocp-rules-rhel9` rule** — that shorter match
belongs to the OCP image built from `rules-containers`.

## Repository and pipeline routing

| Item | Value |
| --- | --- |
| Repository | `https://github.com/RedHatInsights/lightspeed-advisor-on-premise-ocp` (key `lightspeed-advisor-on-premise-ocp` in `project-repos.json`) |
| Bot fork | `git@github.com-bot:platex-rehor-bot/lightspeed-advisor-on-premise-ocp.git` |
| **Working branch** | **`main`** (GitHub default branch) — the PR is opened against `main` |
| Containerfile | `Dockerfile` at the repo root |
| Konflux component | `insights-on-prem` in the `obsint-processing-tenant` namespace; `.tekton/insights-on-prem-push.yaml` triggers on push to `main` |
| Built image | `quay.io/redhat-user-workloads/obsint-processing-tenant/insights-on-prem/insights-on-prem:<sha>` |
| Published image | `registry.redhat.io/lightspeed-services-acm/ocp-rules-rhel9` — tags like `<date>-N` (e.g. `2026.10.20-2`), `latest`; see the [catalog page](https://catalog.redhat.com/en/software/containers/lightspeed-services-acm/ocp-rules-rhel9) |

**The `public`-branch rule does NOT apply here.** It belongs to the OCP rules
image in `ccx/rules-containers` only. This repository has no role for a
`public` branch — branch from `origin/main` and open the PR against `main`.

This is a **public GitHub repository**, so the normal GitHub PR flow applies:
push to the bot fork, open the PR against `main`, and use `/wait-for-ci`
before any CI-passed review notification.

## Image layers — determine where the vulnerable package comes from

The `Dockerfile` starts with:

```
FROM registry.redhat.io/lightspeed-services-ocp/ocp-rules-rhel9:<date-tag>
```

so the ACM image inherits everything from the OCP rules image and adds its
own layer. Scan the published ACM image with
`syft registry.redhat.io/lightspeed-services-acm/ocp-rules-rhel9:<tag> --from registry -o json`
(or the internal Quay image), then classify the affected package:

| Origin | Typical packages | Fix location |
| --- | --- | --- |
| **Inherited from the base image** | rules engine venv (`insights-core`, `ccx-rules-ocp` deps), rules content, `ubi9-minimal` base RPMs, `python312`/`openssl`/`tar` | Fix belongs in `ccx/rules-containers` **`public` branch** first — follow @reference/rules-containers-public.md. Once a fixed OCP image is published, bump the `FROM` tag in this repo's `Dockerfile` (see "Base image bump" below) |
| **ACM layer — Python deps** | FastAPI/uvicorn/SQLAlchemy/alembic etc. (the service app) | `requirements-in.txt` → `requirements.txt` (hashed Lightwell lockfile) in this repo |
| **ACM layer — RPMs** | `python3.12-psycopg2` (+ `libpq`) | `Dockerfile` `microdnf install` list + `rpms.in.yaml` → `rpms.lock.yaml` in this repo |

When in doubt, scan the published OCP base image
(`registry.redhat.io/lightspeed-services-ocp/ocp-rules-rhel9:<same-tag>`)
and compare: a package present in both images at the vulnerable version is
inherited and must be fixed in `rules-containers` first.

## Resolution workflow

### Case A — vulnerable package inherited from the base image

1. Fix the OCP image in `ccx/rules-containers` (`public` branch) following
   @reference/rules-containers-public.md. **The ACM fix is blocked until a
   fixed OCP image is published to registry.redhat.io** — record that
   dependency in Jira and in the prod-gate marker.
2. After the fixed OCP tag is visible in the catalog, bump the base image in
   this repo (see "Base image bump" below) so the ACM image is rebuilt on the
   fixed base.

### Case B — vulnerable package in the ACM layer

1. **Python deps**: bump the pin in `requirements-in.txt`, then regenerate
   the hashed lockfile with `bash scripts/update_requirements.sh` (uv;
   resolves for linux/x86_64/Python 3.12 from any host, but the Lightwell
   validated index may require authentication — if credentials are
   unavailable, report the blocker and send the WatchDuty `needs_help`
   notification; do not hand-edit the hashed lockfile). Mind the README
   caveats: `--upgrade` re-resolves every package (review the diff), and the
   Lightwell index is curated (the fixed version may not be carried yet).
2. **RPMs**: edit the `Dockerfile` `microdnf install` list / `rpms.in.yaml`
   as needed, then regenerate `rpms.lock.yaml` with
   `bash scripts/update_rpm_lockfile.sh` inside a `linux/amd64` UBI9
   container. The `FROM` image is the rpm-lockfile context image, so a stale
   base tag locks wrong versions.
3. **Verify locally**: `podman build .` (non-hermetic builds fall back to
   public PyPI), then `syft`/`grype` the local image to confirm the package
   moved outside the vulnerable range.

### Base image bump (after a fixed OCP image is published)

1. Update `FROM registry.redhat.io/lightspeed-services-ocp/ocp-rules-rhel9:<new-tag>`
   in `Dockerfile` to the fixed published tag.
2. Regenerate `rpms.lock.yaml` — the base image is the rpm-lockfile context
   image, so the lockfile must match the new base (needs a
   `registry.redhat.io` pull secret in `scripts/.dockerconfig.json` for
   `skopeo`).
3. Note: the `ccx-rules-releaser` `INSIGHTS_ON_PREM_PIPELINE` child pipeline
   automates exactly this bump after every rules release. An ad-hoc CVE fix
   follows the same steps manually in a normal PR.

### PR, build, and release

1. Open a PR against `main` from the bot fork, add the standard attribution
   comment, link it in Jira, transition to "Code Review".
2. This is a GitHub PR: use `/wait-for-ci` and its guarded notification flow.
   Konflux also runs the hermetic build on PRs and pushes; a failing
   hermetic build is a CI failure like any other.
3. After merge, the push pipeline builds
   `quay.io/redhat-user-workloads/obsint-processing-tenant/insights-on-prem/insights-on-prem:<merge-sha>`.
   Wait ~20 minutes, then verify with `skopeo inspect` / `syft`.

## Production gate — Konflux release + catalog publication

- **No app-interface deployment**: never create an app-interface MR for this
  image and do not add the `repo:app-interface` label.
- Production means the fixed build is **released by Konflux** to
  `quay.io/redhat-services-prod/obsint-processing-tenant/insights-on-prem/insights-on-prem`
  and **published** to
  `registry.redhat.io/lightspeed-services-acm/ocp-rules-rhel9` (visible on
  the catalog page).
- If the release/publish step requires a manual action the bot cannot
  perform, send the WatchDuty `needs_help` notification with the blocker and
  keep the ticket in "Code Review".
- Close only after the fixed tag is visible in the catalog (clear the prod
  gate with the standard marker sequence). For Case A CVEs, the gate also
  requires the fixed OCP base image tag to be the one referenced by `FROM`.

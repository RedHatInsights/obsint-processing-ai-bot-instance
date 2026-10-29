# rules-containers public image (`lightspeed-services-ocp/ocp-rules-rhel9`)

Full remediation workflow for CVEs reported against the productized rules
image `lightspeed-services-ocp/ocp-rules-rhel9`. Team confirmation (Slack):
we manage this image in
[ccx/rules-containers](https://gitlab.cee.redhat.com/ccx/rules-containers),
and **the image comes from the `public` branch, not `master`**.

## Detection

The Jira summary names the image itself as the component:

```
CVE-YYYY-NNNNN lightspeed-services-ocp/ocp-rules-rhel9: {package}: {title} [services-ccx-default]
```

Treat the CVE as this workflow when the component (text between the CVE ID
and the first `:`) matches, case-insensitively, any of:

- `lightspeed-services-ocp/ocp-rules-rhel9` (exact product name)
- any component containing `ocp-rules-rhel9` or `lightspeed-services-ocp`

The component may contain slashes — do not split it on `/`.

## Repository and branch routing

| Item | Value |
| --- | --- |
| Repository | `https://gitlab.cee.redhat.com/ccx/rules-containers` (key `rules-containers` in `project-repos.json`) |
| Bot fork | `https://gitlab.cee.redhat.com/platex-rehor-bot/rules-containers.git` |
| **Working branch** | **`public`** — branch from `origin/public` and open MRs targeting `public` |
| Containerfile | `public.Containerfile` at the repo root of the `public` branch |
| Rules content | `ccx-rules-ocp/` — git submodule; run `git submodule update --init --recursive` after cloning |

**CRITICAL**: `master` builds a different image (`rules-containers-private`,
Konflux component `rules-containers-private`). Changes merged to `master` do
NOT fix CVEs against `lightspeed-services-ocp/ocp-rules-rhel9`. Always work on
`public`.

## Image locations

| Stage | Image | Tags |
| --- | --- | --- |
| Built (dev) | `quay.io/redhat-user-workloads/obsint-processing-tenant/rules-containers/rules-containers-public` | commit SHA + date tag from `konflux.additional-tags` (e.g. `2026.10.28`) |
| Released (internal) | `quay.io/redhat-services-prod/obsint-processing-tenant/rules-containers/rules-containers-public` | same tags after Konflux release |
| Published (customers) | `registry.redhat.io/lightspeed-services-ocp/ocp-rules-rhel9` | `<date>-N` (e.g. `2026.10.28-1`), `latest`; see the [catalog page](https://catalog.redhat.com/en/software/containers/lightspeed-services-ocp/ocp-rules-rhel9) |

## Build pipeline

- Konflux component `rules-containers-public` in the `obsint-processing-tenant`
  namespace; `.tekton/rules-containers-public-push.yaml` triggers on every push
  to `public` (PR pipeline: `rules-containers-public-pull-request.yaml`).
- Hermetic build via Hermeto. Python deps are prefetched from the pinned
  lockfiles; RPMs come from `deps/rpms.lock.yaml`.
- Integration tests (`pipelines/check-rules-are-runnable.yaml`) run the rules
  against a sample archive on every PR/push.
- Local (non-hermetic) build for verification falls back to public PyPI:
  `podman build -f public.Containerfile .`

## Where vulnerable code lives (public branch)

| Vulnerable item | Pinned in | Regenerate with |
| --- | --- | --- |
| Python runtime deps (most) | `deps/requirements-gitlab.in` → `deps/requirements-gitlab.txt` (hashed Lightwell lockfile) | `bash scripts/update_requirements.sh` (needs Lightwell netrc credentials for `packages.redhat.com`) |
| Source/VCS Python packages (e.g. `ccx-ocp-core`) | `deps-source/requirements.txt` | `./scripts/prepare_rules_bump.sh` / manual pin |
| Build-time Python pins (e.g. `uv`) | `deps/requirements-build.in` → `deps/requirements-build.txt` | `bash scripts/update_requirements.sh` |
| RPMs (`python312`, `openssl`, `tar`) and runtime base image layers | `public.Containerfile` `FROM registry.access.redhat.com/ubi9-minimal:<tag>` + `microdnf install` list; `deps/rpms.in.yaml` → `deps/rpms.lock.yaml` | `bash scripts/update_rpm_lockfile.sh` (must run inside a `linux/amd64` UBI9 container; resolves against public UBI repos, no entitlement needed) |
| Rules content | `ccx-rules-ocp` submodule | normally handled by the rules release pipeline, not CVE fixes |

Notes:

- The builder stage base (`registry.access.redhat.com/ubi9/python-312`) does
  not ship in the runtime image; verify with `syft` before treating its CVEs
  as affecting this image.
- `ARG/LABEL TAG_NAME` in `public.Containerfile` is the release date tag
  managed by the release pipeline. Leave it and the submodule untouched for
  dependency/base-image CVE fixes.
- Lockfile regeneration caveats (see the repo README): pip lockfiles resolve
  against the Lightwell validated index (curated; may not carry the fixed
  version yet), and after pip changes the RPM lockfile may need regeneration
  too (e.g. `rustc`/MSRV constraints for build backends like `maturin`).

## Resolution workflow

1. **Assess**: scan the published/internal image with
   `syft <image> --from registry -o json` (use the currently published tag
   from the catalog page, or `:latest`). Map each affected package to its pin
   location in the table above. Compare against the vulnerable range.
2. **Fix on `public`**: create a branch from `origin/public`, bump the pin
   (or base image tag), regenerate the matching lockfile(s). If lockfile
   regeneration cannot run (missing Lightwell netrc / UBI9 container), stop,
   report the exact blocker, and request manual help — do not hand-edit
   hashed lockfiles.
3. **Verify locally**: `podman build -f public.Containerfile .` then
   `syft`/`grype` the local image to confirm the package version moved
   outside the vulnerable range.
4. **MR to `public`**: push to the bot fork
   (`platex-rehor-bot/rules-containers`), open the MR against `public` with
   `glab mr create` (target branch `public`), add the standard attribution
   comment, link it in Jira, transition to "Code Review".
5. **Konflux build**: after merge, the push pipeline builds hermetically.
   Wait ~20 minutes, then verify the new image with
   `skopeo inspect` / `syft` on
   `quay.io/redhat-user-workloads/obsint-processing-tenant/rules-containers/rules-containers-public:<merge-sha>`.
6. **Production = catalog publication, NOT app-interface**:
   - This image has **no app-interface deployment**. Never create an
     app-interface MR for it and do not add the `repo:app-interface` label.
   - Production for this image means the fixed build is **released** to
     `quay.io/redhat-services-prod/obsint-processing-tenant/rules-containers/rules-containers-public`
     and **published** to `registry.redhat.io/lightspeed-services-ocp/ocp-rules-rhel9`
     (visible on the catalog page). Release/publishing normally happens
     through the Konflux release flow driven by
     [ccx-rules-releaser](https://gitlab.cee.redhat.com/ccx/ccx-rules-releaser)
     during a rules release.
   - If a new release/publish needs a manual action the bot cannot perform
     (Konflux release, new rules tag), send the WatchDuty `needs_help`
     notification with the blocker and keep the ticket in "Code Review".
   - Once the fixed tag is visible in the catalog, the downstream
     `insights-on-prem` base-image bump is automated: the releaser's
     `INSIGHTS_ON_PREM_PIPELINE` child pipeline waits for
     `registry.redhat.io/lightspeed-services-ocp/ocp-rules-rhel9:${TAG}` in
     Pyxis and opens a PR in
     [RedHatInsights/lightspeed-advisor-on-premise-ocp](https://github.com/RedHatInsights/lightspeed-advisor-on-premise-ocp).
     No bot action is required there; note it in the Jira comment.
7. **Close** only after the fixed image is published to registry.redhat.io
   (clear the prod gate with the standard marker sequence).

## Notification differences

- MRs here are GitLab MRs like app-interface: `/wait-for-ci` is GitHub-only,
  so do not run it. Send the immediate `production-update`-style WatchDuty
  notification right after MR creation (same format, WatchDuty mention,
  resource ID `ccx/rules-containers!<MR-NUMBER>`).
- State clearly in every notification that the fix targets the `public`
  branch image and that production completion is catalog publication.

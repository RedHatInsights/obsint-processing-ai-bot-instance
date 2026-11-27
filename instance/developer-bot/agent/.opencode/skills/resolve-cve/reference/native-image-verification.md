# Native dependency and base-image verification

Use this reference when a container CVE concerns embedded native dependencies
(especially Rust in Python wheels), scanner coverage is incomplete, or published
SBOM contents disagree with the installed runtime. Complete this investigation
before escalating for supplier evidence. Do not require the original scanner
report to begin: assess the affected package from the authoritative advisory.

The specialist gathers evidence; the coordinator owns task memory, Jira,
notifications and closure. Existing production and human-review gates apply.

## 1. Establish scope and reuse evidence

- Identify the deployed/customer-published digest, platform, source revision,
  advisory ID/aliases, package ecosystem and vulnerable/fixed ranges.
- Read existing task evidence before downloading or scanning. Reuse successful
  results only for the same digest/platform and applicable advisory. Record a
  scan failure as a failure, never package absence.
- Keep restricted-ticket evidence in private task storage. Do not publish it
  in public issues, PR descriptions or generic shared knowledge.

## 2. Obtain the published inventory and exact build inputs

- Inspect the source revision's Containerfile/Dockerfile, all FROM stages,
  COPY --from paths, dependency installation/removal and pipeline prefetch inputs.
- Retrieve the image's registry-published SBOM and available build provenance
  using supported registry/proxy clients. Look for OCI referrers or legacy
  digest-tagged `.sbom` / `.att` artifacts when supported. Record retrieval or
  format failures without making the original scanner report a prerequisite.
- Inspect SBOM provenance/annotations and generation inputs. A merged inventory
  can contain runtime, builder, prefetched and development packages. Even a
  CONTAINS relationship may describe merged build inputs; confirm installation
  against the final filesystem. Do not assume every published SBOM is mixed.
- Resolve historical base and builder digests from published metadata, select
  the in-scope platform and scan those exact images. A floating tag today does
  not verify the historical build. If unresolved, state that coverage gap.
- Include inherited layers and packages added after FROM in the final scan.
  Scanning a base alone does not cover the final application image. CI helper
  images are a separate scope from Dockerfile build stages; do not silently
  claim they were scanned or expand into a whole CI infrastructure audit.
- Follow `redhat-registry-proxy.md` for Red Hat pulls, signature policy and disk
  hygiene. Use configured registry/proxy access; this investigation does not
  require cluster login, kubeconfig inspection, Vault access or workload execution.

## 3. Scan without hiding coverage gaps

- Generate a filesystem-derived Syft SBOM for the final image and exact bases.
  Verify the relevant catalogers ran (for example RPM, Python, ELF and
  cargo-auditable); retain tool versions, package counts, stderr and exit status.
- Update Grype's database once and retain its version/date. Save an **unfiltered**
  JSON report before optionally summarizing fixable findings. `--only-fixed`
  can hide vulnerable packages without available fixes; zero filtered findings
  is not a clean-image verdict. Report raw matches as untriaged findings, not
  confirmed exploitability or counts of distinct CVEs.
- Verify the database covers the target **package plus advisory/aliases**, not
  merely the CVE ID in another ecosystem. With a compatible Grype version:

  ```bash
  grype db status -o json
  grype db search --pkg '<package>' --vuln '<CVE-ID>' --vuln '<ecosystem-advisory-ID>' -o json
  ```

  If this interface is unavailable, inspect supported help/metadata rather than
  guessing commands. Missing database coverage does not prevent assessment from
  an identified package/version and authoritative advisory, but scanner silence
  cannot authorize closure. An explicitly affected version in a supplied SBOM
  with no scanner finding is a useful coverage warning, not proof of safety.

## 4. Resolve native inventory gaps

- Enumerate native binaries in the final layered filesystem, respecting
  whiteouts and symlink/path aliases. Bind OS binaries to RPM owners and recorded
  file digests where available; retain unmatched files for investigation.
  Matching RPM checksums establishes package identity, not absence of CVEs.
- For Rust-backed wheels, bind exact wheel hashes to pinned build inputs and
  compare their native extension hashes with the installed files. Inspect ELF
  `.dep-v0` metadata, symbols and embedded source paths where available. Absence
  of strings or a stripped symbol table does not prove crate absence.
- Inspect corresponding supplier source archives: top-level Cargo.lock,
  workspace manifests, vendor package names/versions, dependency edges, Cargo
  source replacement and relevant build overrides. Account for registry packages
  in the vendor tree and local workspace packages separately. Do not treat
  nested vendored dependencies' test/development lockfiles as the parent build's
  resolved graph. Generic terms such as `webpki` are not package identities.
- Establish how the supplier identifies the source archive as corresponding to
  the exact wheel. Record the evidence and any assumption explicitly. Hashes in
  the same requirements file bind chosen artifacts but do not alone prove which
  source produced a wheel. Prefer available build records/attestations; do not
  invent a universal requirement for a new supplier attestation when existing
  trusted package/source records already establish the relationship.
- If a target is found in a builder tool, trace whether that tool or its code
  reaches the final image. Installation followed by removal in source is not
  enough: verify final filesystem absence and copied artifacts. Keep build-time
  exposure distinct from the runtime verdict.

## 5. Decide and persist the next action

- **AFFECTED:** identify the installed copy/version and its advisory match;
  remediate the owning component and complete the applicable production gate.
- **NOT AFFECTED:** require successful, appropriately scoped inventory and
  sufficient package/source evidence for every in-scope target. Use the parent
  workflow's closure path only when its verification requirements are met.
  Neither empty scanner output nor a human's preferred conclusion substitutes
  for evidence. A qualified engineering recommendation is not automatic closure.
- **INCONCLUSIVE:** name the precise missing relationship or coverage, what
  was already verified, and the smallest next action. Escalate only that gap
  (for example an exact wheel/source binding), not a generic request to scan
  everything again. If the remaining question is whether a source-correspondence
  assumption is acceptable, identify it as an evidence-acceptance decision.
  Record an authorized decision without claiming it created a build attestation.

The coordinator stores a concise summary and `metadata.cve_verification` using
the existing task update API. Preserve unrelated metadata. Include:

- target digest/platform, source revision, advisory/aliases and reviewed ranges;
- base/builder digests and completed/missing scope;
- private evidence paths, scanner/DB versions and target coverage;
- runtime versus build-only findings, source bindings and explicit assumptions;
- verdict, exact blocker, next action and the event that warrants re-investigation.

Set the task's existing `metadata.last_step` / `metadata.next_step` consistently.
On resumption, read this state and the latest Jira feedback before delegating.
Retry failed checks or revisit changed digests, new advisories, database coverage
or supplier evidence; do not redownload identical artifacts or repost an unchanged
blocker every cycle. Follow existing deferred scheduling and notification cooldowns;
do not invent a new scheduler or sleep/poll inside the session. Retain compact
evidence, removing large image layouts per registry-access disk hygiene.

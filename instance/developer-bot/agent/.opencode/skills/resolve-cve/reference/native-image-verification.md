# Native dependency and base-image verification

Use this when a container CVE involves compiled dependencies (such as Rust in
Python wheels), scanner coverage is incomplete, or a published SBOM disagrees
with the runtime. Investigate before requesting supplier evidence; the original
scanner report is not required. Existing ownership and closure rules apply.

## 1. Check the exact images

- Identify the deployed/published digest, platform, source revision and advisory.
  Read saved task evidence before repeating work.
- Inspect the Dockerfile and published SBOM/build metadata to identify the exact
  historical base and builder digests. Scan them and the final image, including
  inherited layers and added packages. Today's floating tags are not evidence
  for an older build; record any unresolved digest.
- Follow `redhat-registry-proxy.md` for access, signature policy and disk cleanup.
  Use registry access; no cluster login or image execution is needed.

## 2. Separate build dependencies from runtime

- Published SBOMs may combine installed, prefetched and build-only packages.
  Check their origin rather than assuming every entry ships in the runtime.
- Trace installation, removal and COPY --from steps. Verify the final filesystem
  and copied artifacts before calling a dependency build-only.

## 3. Check scanner coverage

- Save a successful Syft inventory and an unfiltered Grype report with tool/DB
  versions. Confirm the relevant ecosystem catalogers ran. `--only-fixed` hides
  findings without fixes; a failed scan or zero findings does not prove safety.
- Check that Grype covers the **package and advisory**, including aliases, using
  its supported DB search commands. If coverage is missing, compare identified
  versions directly with the authoritative advisory instead.

## 4. Investigate embedded dependencies

- Map native binaries to RPM owners/checksums where available. For wheels, match
  pinned wheel hashes and installed extension bytes. Inspect Rust `.dep-v0`
  metadata, symbols and source paths; missing strings do not prove absence.
- Check corresponding source archives: root Cargo.lock, workspace packages,
  vendored package names/versions and build overrides. Nested dependency test
  lockfiles are not the parent build graph; generic `webpki` names are not proof
  of the `rustls-webpki` crate.
- Record how the supplier's sources correspond to the exact binaries and any
  remaining assumption. Co-listed hashes alone do not prove this relationship.
  Reuse trusted source/build records before requesting a new attestation.

## 5. Record the verdict and remember the evidence

Apply `/cve-workflow`'s existing verdict and closure gates. Keep build-time
exposure separate from runtime impact. If inconclusive, identify the precise
missing evidence and smallest next action; do not repeat a generic scan request.
A qualified source-based recommendation does not authorize automatic closure.

The coordinator saves a summary and `metadata.cve_verification`, preserving
unrelated metadata: target/base digests and platform, advisory, private evidence
paths, scanner coverage, runtime/build-only findings, assumptions, verdict,
blocker and next action. Update `metadata.last_step` / `metadata.next_step` too.

On resumption, read this state and new Jira feedback. Reuse successful evidence
for the same digest/platform; retry failures or revisit changed images, advisories,
scanner coverage or supplier evidence. Follow existing scheduling/cooldowns,
keep restricted evidence private, and remove large image layouts after scanning.

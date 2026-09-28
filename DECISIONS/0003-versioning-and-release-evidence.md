# 0003: Separate Product, Integration, And Skill Versions

Date: 2026-07-15

## Status

Accepted.

## Context

Scientific Workbench previously used three valid but insufficiently explained
version labels:

- app bundle version `1.0.0`;
- integrated app + skill compatibility line `v2.0`;
- declared scientific skill compatibility axis (currently `2.8` in the release
  pipeline), distinct from mixed historical labels in installed registry stubs.

At M101 closure, the reviewed workspace and release pipeline declare `2.8`,
while the installed skill roots were not mechanically promoted and still carry
mixed historical mother/child labels. Compatibility is therefore bound by the
exact registry-chain hashes and gates, not by treating those labels as proof
that `2.8` is installed.

Historical archives were stored by app version, while a single `manifest.json`
was overwritten by later builds in the same directory. The surviving manifest
for `post-audit-hardening` predates the Git baseline and therefore records
`source_revision: "unknown"`. Rewriting that historical evidence would make the
record look stronger than it was at creation time.

## Decision

The project maintains three independent version axes:

1. **App version** is the numeric macOS bundle and archive version.
2. **Integrated release** identifies the compatibility contract exercised by
   the app + skill gates.
3. **Skill release** is a declared compatibility axis for the scientific skill
   family expected by that integrated release. It is not inferred from one
   registry label; the exact installed content is bound by registry evidence.

New release manifests use schema version 2 and record all three axes. Release
packaging must:

- start from a clean Git worktree;
- record the full source commit and branch;
- create a build-specific manifest beside the archive;
- refuse to overwrite an existing archive or manifest;
- record the Swift/macOS/architecture environment;
- record whether the quality and DOCUS gates ran;
- record the mother registry-stub SHA-256, every resolved
  `canonical_registry` hop with relative path and SHA-256, and the final
  canonical registry path/digest;
- recheck a clean unchanged Git `HEAD` after validation and before manifest
  creation;
- reject registry-chain drift during packaging.

Historical archives and manifests remain unchanged. A historical
`source_revision: "unknown"` remains an honest limitation, not a value to repair
after the fact.

## Consequences

Positive:

- Every schema-2 archive produced and accepted by this pipeline can be traced
  to one clean commit.
- Rebuilding with the same build identifier cannot silently replace evidence.
- App, integration, and skill versions no longer appear contradictory.
- Historical limitations stay visible.

Tradeoffs:

- Release packaging must happen after committing validated changes.
- A new build identifier is required for every retained package.
- Compatibility claims still require the dual app + skill gate; version labels
  alone are not proof.

## Verification

- `script/verify_release_manifest.sh` accepts only the exact allowlisted,
  immutable schema-1 manifest retained at `dist/release/1.0.0/manifest.json`;
  new, fabricated, renamed, or downgraded manifests must satisfy schema 2.
- Schema-2 manifests require complete Git, environment, and gate metadata.
- `script/verify_release_archive.sh` requires one top-level `.app`, verifies the
  archive named by the build manifest, and requires bundle version/build values
  to match the manifest.

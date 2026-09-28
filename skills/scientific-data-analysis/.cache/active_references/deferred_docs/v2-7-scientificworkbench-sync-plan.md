# v2.7 ScientificWorkbench Sync Plan

This plan is the handoff after v2.7 skill hardening. It is intentionally short
so the app chat can use it without loading the full release history.

## Goal

Make ScientificWorkbench consume the installed mother + child skill family
without copying the skills into the app and without assuming one root.

## Inputs For The App

- Mother root: `~/.codex/skills/scientific-data-analysis`
- Child roots:
  - `~/.codex/skills/scientific-data-astro`
  - `~/.codex/skills/scientific-data-documents`
  - `~/.codex/skills/scientific-data-notebooks`
  - `~/.codex/skills/scientific-data-maintainer`
- Registry stubs: each root may expose a compact
  `public_surface_registry.yaml` with `canonical_registry`.
- Contracts: JSON envelopes, run bundles, typed artifacts, app hints, exposure
  modes, and smoke/regression coverage artifacts remain unchanged from v1.9 to
  v2.7.

## Required App Changes

1. Replace single-root assumptions with a `SkillRootCatalog` or equivalent:
   mother, astro, documents, notebooks, maintainer.
2. Load each root's registry by recursively resolving `canonical_registry`.
3. Attach an owning root to every `CapabilityEntry`.
4. Build commands with the owning root as `workingDirectory`.
5. Keep maintainer-only actions out of normal user workflows.
6. Keep `ArtifactDiscovery` and `ToolEnvelopeParser` compatible with v1.8,
   v1.9 and v2.x envelopes.
7. Add drift tests for registry resolution, ownership, exposure, app-readiness,
   artifacts, and fallback behavior.

## Sync Order

1. Verify installed skill family:
   `sync_public_surface_docs.py --check`,
   `audit_v2_7_senior_integration_regression.py`, and
   `portable_smoke_test.py --profile core`.
2. In ScientificWorkbench, add multi-root catalog and recursive registry
   resolver.
3. Update `CapabilityCommandBuilder` to use each capability's owning root.
4. Update tests using installed skill fixtures, not copied skill files.
5. Run Swift tests and app quality gates.
6. Run an end-to-end smoke with a table, a document, a notebook, a FITS file,
   and an optional-backend block.
7. Only then declare the app synchronized with skill v2.7.

## Do Not Do

- Do not rsync the skills into the app bundle.
- Do not expose maintainer routes as normal actions.
- Do not treat smoke/regression coverage as exhaustive coverage.
- Do not silently fall back to an old single registry if recursive resolution
  fails.
- Do not modify user originals during app test runs.

## Expected App Warning Before Work

The current app may still contain a single `DefaultPaths.skillRoot`. That is a
known pre-sync finding, not a skill failure. The app-side sync should close it.

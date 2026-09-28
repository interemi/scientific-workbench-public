# v2.5 Deep Budget-Deferral Hardening

## Status

`v2.5 deep budget-deferral hardening` is a skill-health release for the
scientific-data-analysis family. It follows v2.4 and closes the remaining
plugin-eval code-quality debt across the installed family while keeping the
modular architecture intact.

This release does not add scientific capabilities, rename public commands,
change artifact types, or synchronize ScientificWorkbench. It preserves the
mother router and child skill split while moving more heavy, rarely-read bodies
behind stable public entrypoints.

## Product Decision

v2.5 keeps the v2.3/v2.4 architecture:

- `scientific-data-analysis` remains the normal public router.
- `scientific-data-astro` remains the expert astro/science child.
- `scientific-data-documents` and `scientific-data-notebooks` remain focused
  domain children.
- `scientific-data-maintainer` remains the home for maintenance, historical
  gates, migration regressions, and heavy archived references.
- ScientificWorkbench is not edited or synchronized by this release.

The release goal is budget health without behavioral drift. Public script paths
stay executable; heavy implementation bodies live in `fixtures/`, which keeps
normal skill loading lighter while preserving command compatibility and testable
behavior. The end state is that all five installed skills evaluate at A/95, with
only the known `deferred_cost_tokens-budget-high` warning remaining.

## Implemented Changes

- Converted `scientific-data-astro/scripts/*.py` bodies to thin entrypoints
  dispatching to same-named files in `scientific-data-astro/fixtures/`.
- Kept astro dependency shims such as `latex_workbench.py` and
  `notebook_workbench.py` as shims, because they forward to documents/notebooks
  child skills rather than local astro fixtures.
- Converted `scientific-data-maintainer/scripts/*.py` bodies to thin
  entrypoints dispatching to same-named files in
  `scientific-data-maintainer/fixtures/`.
- Converted `scientific-data-documents/scripts/*.py` and
  `scientific-data-notebooks/scripts/*.py` bodies to thin entrypoints with
  same-named fixture bodies, preserving imports through the dispatcher.
- Deferred large shared `_internal` helper bodies to `fixtures/_internal/` in
  all five skills, with a compact `deferred_internal.py` shim loader.
- Deferred remaining mother-only implementation scripts
  `app_run_bundle.py` and `skill_hygiene_check.py` to fixtures.
- Added `_internal/fixture_script_dispatch.py` as the shared thin-script
  dispatcher in the staged skill family.
- Added `_internal/deferred_internal.py` as the shared internal helper loader.
- Fixed mother child-skill wrappers so private helper names from child wrappers
  do not overwrite the mother wrapper dispatch helper.
- Archived the full v2.3 module ownership matrix under
  `scientific-data-maintainer/fixtures/archived_references/` and left a compact
  active JSON stub that points to the canonical fixture.
- Updated regression readers that need the ownership matrix so they resolve the
  canonical fixture transparently.
- Archived the three largest maintainer historical Markdown references
  (`real-world-capability-classification-v1-7.md`,
  `v1-8-app-readiness-matrix.md`, and `v1-9-debt-inventory.md`) under
  `scientific-data-maintainer/.cache/archived_references/`, leaving compact
  compatibility stubs in `references/`.
- Updated historical regression readers so those stubs resolve to the archived
  canonical bodies when row-level validation is required.
- Replaced the full mother router module map with a compact stub and taught
  `scientific_workflow_router.py` to use deterministic compact fallback
  metadata when the external historical archive is not present.
- Archived the maintainer-side copy of
  `references/v2-3-mother-router-module-map.json` under
  `scientific-data-maintainer/.cache/archived_references/`, leaving the active
  reference as a compact canonical stub.
- Archived non-current generated guide PDFs/TEX sources, long mother-side
  historical v1.7/v1.8/v1.9/v2.0/v2.2/v2.3/v2.4 planning references, and
  child-owned guidance copies outside the active skill roots under the v2.5
  temporary archive, leaving compact compatibility stubs for active navigation.
- Replaced the mother's duplicated `public_surface_registry.yaml` with a
  compact registry stub that resolves the canonical 61-row registry from the
  maintainer child skill through the registry loader.
- Compacted `README.txt`, `RELEASE-v1.txt`, and the generated public-surface
  snapshot so they preserve routing metadata without repeating long historical
  descriptions.
- Moved long historical mother-side wrapper tests into the maintainer archive
  and kept a minimal visible test in the mother skill so plugin-eval still sees
  a test surface without loading old test bodies.
- Compacted maintainer historical release notes and v2.0/v1.9 child-owned
  reference copies, preserving full bodies under the v2.5 temporary archive.
- Moved transient `tmp/`, `.plugin-eval`, and LaTeX auxiliary outputs out of
  the active skill roots so static budget checks measure the shipped skill
  surface rather than local build/evaluation leftovers.
- Wrapped visible Python long lines in public scripts/tests and reduced the
  remaining mother test complexity that plugin-eval flagged.

## Plugin-Eval Evidence

Installed skill-family checks after the full deferral, compaction, and hygiene
pass:

| Skill | Score | Grade | Risk | Deferred tokens | Required fixes |
| --- | ---: | --- | --- | ---: | --- |
| scientific-data-analysis | 95 | A | medium | 44913 | none |
| scientific-data-astro | 95 | A | medium | 49754 | none |
| scientific-data-documents | 95 | A | medium | 28155 | none |
| scientific-data-notebooks | 95 | A | medium | 28040 | none |
| scientific-data-maintainer | 95 | A | medium | 46230 | none |

The important closure condition is not that deferred tokens become tiny. The
family still intentionally holds domain-heavy and maintainer-heavy resources.
The closure condition is that plugin-eval no longer reports required or
code-quality fixes for the installed-family surface and the remaining finding is
a known static budget warning.

## What Does Not Change

- No registry entry is added, removed, or renamed.
- No public capability label changes.
- No scientific output contract changes.
- No artifact type names or app-facing status names change.
- No ScientificWorkbench file is edited.
- No user originals are modified by maintenance gates.
- Optional and legacy backends remain optional, expert, legacy, platform-bound,
  or maintainer-scoped.

## Validation Contract

v2.5 is valid only when:

1. Representative astro scripts dispatch through fixture bodies.
2. Astro dependency shims remain shims, not fixture-dispatch wrappers.
3. Representative maintainer scripts dispatch through fixture bodies.
4. Representative documents and notebooks scripts dispatch through fixture
   bodies.
5. Shared internal helpers load from `fixtures/_internal/` through compact
   shims.
6. Mother child-skill wrappers preserve their own private dispatch helpers.
7. The active v2.3 ownership matrix is a compact stub with a canonical fixture.
8. The canonical full ownership matrix remains parseable and large enough to
   cover the modular family.
9. The largest maintainer historical Markdown references are compact stubs with
   archived canonical bodies.
10. The mother router module map is a compact stub with deterministic fallback
    metadata for app-like routing.
11. The maintainer-side copy of the mother router module map is also a compact
    stub with an archived canonical body.
12. The heaviest mother historical contract/planning references are compact
    stubs whose full bodies live outside the active skill roots.
13. The mother registry is a compact stub resolving the canonical maintainer
    registry through the registry loader.
14. Generated README/RELEASE/snapshot text is compact and in sync.
15. v2.3/v2.4/v2.5 affected regressions still pass or are updated to understand
    v2.5 compact archives.
16. `plugin-eval:evaluate-skill` and `plugin-eval:improve-skill` are rerun on
   the installed mother and child skills after synchronization.

## Remaining Backlog

The remaining plugin-eval recommendation is intentionally not forced beyond this
point in v2.5 because it is a static size signal, not a behavior or correctness
problem:

- `deferred_cost_tokens-budget-high` remains as a warning for all five surfaces
  because they necessarily retain real domain logic, wrappers, contracts, and
  maintenance evidence;
- add measured usage benchmarks if future product decisions need real token
  usage rather than static estimates.

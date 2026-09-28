# v2.7 Senior Integration Hardening

## Purpose

v2.7 closes the actionable follow-up from the senior AI / Agents / Plugins /
Skills evaluation before ScientificWorkbench is synchronized again. The family
already scores `100/A` in `plugin-eval`, but the senior review identified
integration risks that are not solved by the rating alone.

The release goal is not to add capabilities. It is to make the existing
mother + child skill architecture easier and safer for a native app to consume.

## Senior Findings Addressed

| Severity | Finding | v2.7 correction |
|---|---|---|
| P1 | ScientificWorkbench must resolve `canonical_registry` and mother/child roots. | Document recursive registry resolution and validate it with `audit_v2_7_senior_integration_regression.py`. |
| P1 | The app must not assume one `DefaultPaths.skillRoot` for all capabilities. | Define skill-root ownership and require command execution from the owning root. |
| P2 | Coverage is smoke/regression coverage, not exhaustive coverage. | Keep `coverage-summary.json` explicit with `not_exhaustive_project_coverage=true` and document the caveat. |
| P2 | Stubs, symlinks and wrappers need permanent integrity checks. | Add a regression that rejects broken symlinks and unresolved registry stubs. |
| P2 | Exposure/app-readiness can drift between docs and app code. | Treat the app sync plan as a controlled contract update, not a blind rsync. |
| P2 | Historical docs are dense for app consumers. | Add the short `v2-7-scientificworkbench-sync-plan.md` handoff. |

## Multi-Root Contract

This is the v2.7 multi-root contract for app consumers.

ScientificWorkbench must treat the installed skill family as five coordinated
roots:

| Logical owner | Installed root |
|---|---|
| mother | `~/.codex/skills/scientific-data-analysis` |
| astro | `~/.codex/skills/scientific-data-astro` |
| documents | `~/.codex/skills/scientific-data-documents` |
| notebooks | `~/.codex/skills/scientific-data-notebooks` |
| maintainer | `~/.codex/skills/scientific-data-maintainer` |

The app may keep the mother as the visible default, but command construction
must execute a capability from the root that owns the capability. Maintainer
routes remain hidden from normal users.

## Canonical Registry Contract

Each `public_surface_registry.yaml` may be compact. A consumer must:

1. Open the root's `public_surface_registry.yaml`.
2. If it contains `canonical_registry`, resolve that path relative to the stub.
3. Repeat until the loaded file contains `entries:`.
4. Treat that file as the authoritative registry for that root.
5. Cache the resolved path and a fingerprint, but do not rewrite the skill.

This keeps plugin-eval cost low without hiding the public surface from app
consumers.

## Coverage Caveat

`coverage-summary.json` is a smoke/regression coverage artifact. It proves that
each skill has a traceable, current probe. It does not claim exhaustive unit
test coverage over every capability, optional backend, GUI route, or legacy
workflow.

App docs and release notes must say "smoke/regression coverage" rather than
"complete coverage".

## Integrity Requirements

The v2.7 regression validates:

- five skill roots exist;
- each root has `SKILL.md`, `public_surface_registry.yaml`, and
  `coverage-summary.json`;
- recursive `canonical_registry` resolution reaches a 61-entry registry;
- no broken symlink exists in `references/`;
- the mother exposes the v2.7 sync plan;
- ScientificWorkbench currently has the expected integration work pending.

## Not In Scope

- No Swift changes in ScientificWorkbench.
- No app-side parser rewrite.
- No rsync into the app.
- No new capability.
- No change to scientific behavior.

## Closure Criteria

v2.7 is ready to hand to the app only when:

- `audit_v2_7_senior_integration_regression.py` passes in editable;
- `sync_public_surface_docs.py --check` passes where applicable;
- `portable_smoke_test.py --profile core` still passes;
- `evaluate-skill` still reports `100/A` for mother and children, or any
  deviation is documented before sync;
- `guia_scientific_data_analysis_v2_7.tex/pdf` exists in `references/` and on
  the Desktop.

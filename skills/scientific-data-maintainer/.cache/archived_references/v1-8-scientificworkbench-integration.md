# v1.8 ScientificWorkbench Integration Contract

Status: Fase 8 integration reference for the editable v1.8 workstream.

This document explains how `scientific-data-analysis` v1.8 should be consumed
by ScientificWorkbench later. It is intentionally a skill-side backend
contract, not an app-side implementation plan. ScientificWorkbench was read for
compatibility context only; v1.8 does not edit or synchronize the app.

Short form: this is the skill-side backend contract for v1.8.

## Product Boundary

v1.8 means:

- the skill is becoming an app-ready backend;
- commands should be safer to invoke from a GUI or local runner;
- outputs should be parseable enough for an app to understand status,
  warnings, artifacts, provenance, and next actions;
- optional, legacy, and domain-specific routes must say when they do not apply;
- app-like regressions prove the backend behavior on temporary copies.

v1.8 does not mean:

- ScientificWorkbench is already synchronized with every new backend contract;
- the app has reached v2.0;
- every capability is normal-user app surface;
- every old CLI route has a perfect `--run-dir` implementation;
- domain-specific astronomy tools are suddenly general-purpose tools.

The large app synchronization is a future v2.0 milestone. v1.8 prepares the
backend so that v1.9 can consolidate contracts and v2.0 can integrate them
without brittle parsing.

## Read-Only App Context Observed

From read-only inspection of ScientificWorkbench:

- `CapabilityCommandBuilder` builds commands through
  `scripts/datanalysis_env.py run-tool`.
- default app runs use a run output directory with `summary.json`,
  `manifest.json`, and an `artifacts/` folder.
- `ToolEnvelopeParser` currently extracts top-level `tool` and `status` from a
  JSON object in stdout.
- `ArtifactDiscovery` recursively lists regular files from a run directory.
- the architecture states: AI plans and explains; local capabilities execute.

Therefore v1.8 keeps top-level `tool` and `status` compatible, while adding the
new app-ready fields documented in `references/v1-8-app-ready-contract.md`.

## Backend Contracts To Use Later

ScientificWorkbench should eventually prefer these skill-side contracts:

| Contract | Reference | Purpose |
|---|---|---|
| App-ready JSON envelope | `references/v1-8-app-ready-contract.md` | Parse status, warnings, errors, artifacts, provenance, next actions, and UI hints. |
| Run bundle | `references/v1-8-run-bundle-contract.md` | Discover a stable run folder without fragile file guessing. |
| App-readiness matrix | `references/v1-8-app-readiness-matrix.md` | Decide normal, expert, optional, maintainer, or not-exposed capability surface. |
| Dry-run router | `references/v1-8-workflow-router.md` | Plan/reject routes deterministically before execution. |
| This integration note | `references/v1-8-scientificworkbench-integration.md` | Keep the skill/app boundary explicit until v2.0. |

## Recommended Invocation Shape

Preferred future app-side shape:

```bash
python scripts/scientific_workflow_router.py plan <input> \
  --task "<user task>" \
  --summary-json <run>/router_summary.json \
  --manifest-json <run>/router_manifest.json
```

Then, after the user or app chooses a route:

```bash
python scripts/app_run_bundle.py \
  --run-dir <run> \
  --tool <capability_id> \
  -- \
  python scripts/<capability>.py <args> --summary-json <run>/summary.json
```

For routes that already support direct app bundles:

```bash
python scripts/profile_table.py input.csv --run-dir <run>
```

The app may continue using `datanalysis_env.py run-tool` as its compatibility
launcher. v1.8 only asks that the child tool or wrapper leave a parseable
summary and stable artifacts.

## Exposure Policy

The app should not expose all public capability labels equally.

| Exposure | Use |
|---|---|
| Normal | General or genuinely transferable routes: table profiling, document intake, containers, notebooks, time series, physical QA, noise budget. |
| Expert | FITS, astrometry, sky crossmatch, RGB FITS export, photometric solution, RV, spectroscopy, deck geometry, advanced document surgery. |
| Optional backend panel | STILTS/TOPCAT, APT, DuckDB, iWork/Keynote, TEAREDUCE when missing or platform-bound. |
| Legacy expert | IRAF, fxcor, iSTARMOD, narrow coursework report routes. |
| Maintainer only | release gates, sync checks, smoke tests, registry audits. |
| Not exposed in normal mode | `li6708_equivalent_width_workbench.py measure` and fixed coursework/literature checks unless the user explicitly enters expert spectroscopy/coursework context. |

This matches the v1.8 app-readiness matrix. It also preserves the v1.7 rule:
do not force analogies just because a pattern is interesting.

## Status Semantics For The App

`PASS` means the result is usable.

`WARNING` means the result is useful but requires review before trust.

`BLOCKED_CONTROLADO` means the route did not run because a backend, input,
platform, or safety precondition was absent, and the user was told what to do
next.

`FAIL` means clean failure without misleading products.

`ROTO` is an audit classification for broken behavior such as raw traceback,
false success, original mutation, or deceptive artifacts. A public tool should
avoid emitting `ROTO`; regressions use it to classify failures.

## What The App Should Trust

The app can trust:

- `summary.json` as the primary parse target when present;
- top-level `tool` and `status` for backwards compatibility;
- `contract_version: "1.8"` when present;
- `app_status` as the normalized status;
- `typed_artifacts` for artifact cards and previews;
- `original_modified` for safety display;
- `warnings`, `errors`, and `next_actions` for user-facing recovery.

The app should not trust:

- file extension alone for FITS, notebooks, ZIPs, or Office/iWork formats;
- optional backend availability without a preflight;
- domain-specific tools as general routes without router evidence;
- a raw stdout blob as the only source of truth when `summary.json` exists.

## v1.8 Regression Evidence

The editable skill has dedicated app-like regressions:

- `scripts/audit_v1_8_phase5_router_regression.py`
- `scripts/audit_v1_8_phase6_app_like_general_regression.py`
- `scripts/audit_v1_8_phase7_app_like_science_astro_regression.py`
- `scripts/audit_v1_8_phase4_run_bundles_regression.py`
- `scripts/audit_v1_8_app_ready_contract_regression.py`
- `scripts/audit_v1_8_app_readiness_matrix_regression.py`

These are backend gates. They do not prove that ScientificWorkbench has already
adopted every v1.8 field.

## Work Left For v1.9

v1.9 should consolidate:

- field names and app status normalization;
- `--run-dir` support or wrapper coverage for priority routes;
- P2 artifact typing debt;
- app-readiness matrix stability;
- optional backend preflight presentation;
- consistent next actions across PASS, WARNING, BLOCKED_CONTROLADO, and FAIL.

## Work Left For v2.0

v2.0 is the likely large app sync:

- update ScientificWorkbench parsers for full v1.8 envelopes;
- consume `typed_artifacts`, `app_hints`, and `next_actions`;
- route normal/expert/optional/legacy modes through the matrix;
- use the dry-run router as deterministic local planner fallback;
- align app run folders with the run-bundle contract;
- keep original inputs read-only and provenance visible in the UI.

Until that happens, v1.8 should be described as backend-ready, not as fully
app-synchronized.

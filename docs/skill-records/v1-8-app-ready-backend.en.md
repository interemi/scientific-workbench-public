# v1.8 App-Ready Backend Charter

> English publication edition of a preserved private record at `d6583f1`.
> Original source: `skills/scientific-data-maintainer/.cache/archived_references/v1-8-app-ready-backend.md`.
> Original SHA-256: `1509971e48fb3e7b51c3fdb3cfab55a21610a5bf4abdef14e65be9863f9d39d4`.
> Historical states and results are unchanged; this edition does not rerun them.
> Machine-specific paths use `$PRIVATE_WORKSPACE` (the original editable
> workspace) and `$HOME` aliases. Where shown, set `RUNS_DIR` to a fresh output
> root before reproducing a historical command; preserve earlier evidence.
> Original documents remain unchanged privately.

Status: Phase 0 charter for the editable v1.8 workstream.

v1.8 is the "App-ready backend / Workflow Contract Release" for
`scientific-data-analysis`. The product goal is to make the skill easier and
safer for `Scientific Workbench` to invoke later, without developing or
synchronizing the app during this release.

## Product Objective

v1.8 should turn the v1.7 stable skill into a more predictable local backend:

- stable command and output expectations for app-like calls;
- parseable JSON envelopes and summary files;
- typed artifact and run-folder conventions;
- explicit status semantics for `PASS`, `WARNING`, `BLOCKED_CONTROLADO`,
  `FAIL`, and `ROTO`;
- conservative workflow recommendations that explain why a route applies or
  does not apply;
- compatibility evidence that the app can consume without guessing.

The skill remains the deterministic execution layer. AI, Codex, or the app may
plan and explain, but local capabilities should execute the scientific,
document, notebook, table, container, and reporting work.

## Non-Goals

v1.8 is not:

- a Scientific Workbench feature sprint;
- a GUI release;
- a rewrite of all existing capabilities;
- a promise to make every domain-specific, legacy, or optional route visible in
  normal app mode;
- a migration from the skill into the app;
- a broad new capability expansion unless a narrow app-readiness need makes it
  unavoidable.

Scientific Workbench may be read for compatibility context, but its source should
not be edited in v1.8 unless a later prompt explicitly asks for app-side work.

## Relationship To v1.7, v1.9, And v2.0

v1.7 stable answered what the skill is allowed to be in real-world use:
general, cross-domain adaptable, domain-specific, legacy-specific, or
maintainer-only. It gave the 59 public capabilities examples, limits, and
honest not-applicable criteria.

v1.8 builds on that by asking a different question: can an app invoke this
capability safely and understand the result?

v1.9 should be a consolidation release. It should freeze names, schemas, status
semantics, and artifact conventions; reduce P2 debt; and harden app-like
regressions without a large product-shape change.

v2.0 is the planned synchronization point with Scientific Workbench. At that
stage, the app can consume the mature backend contracts rather than relying on
ad hoc wrappers or brittle parsing.

## Boundary With Scientific Workbench

Observed app-side contract from read-only inspection:

- `CapabilityCommandBuilder` invokes skill tools through
  `scripts/datanalysis_env.py run-tool`.
- Guided runs expect run directories with `summary.json`, `manifest.json`, and
  an `artifacts/` folder.
- `ToolEnvelopeParser` currently extracts only top-level `tool` and `status`
  from a JSON object in stdout.
- `ArtifactDiscovery` discovers files recursively from the run directory.
- App architecture states that AI plans and local capabilities execute.

Implication for v1.8: improve the skill backend so those expectations become
less fragile, while leaving app implementation details untouched.

## Editable And Installed Baseline

Editable source of truth:

`$PRIVATE_WORKSPACE/skill_work/scientific-data-analysis`

Installed skill:

`$HOME/.codex/skills/scientific-data-analysis`

Scientific Workbench:

`$PRIVATE_WORKSPACE/ScientificWorkbench`

Phase 0 found the editable tree coherent as v1.7 stable with 59 public registry
entries and no public-surface drift.

Phase 0 also found a baseline warning in the installed tree: the installed
registry currently exposes 61 labels while installed generated docs and the v1.7
release gate still expect 59. The installed-only registry entries are:

- `legacy_spectroscopy_report_builder.py populate`
- `latex_workbench.py compile`

Do not delete or overwrite those entries in Phase 0. Before the final v1.8 sync,
they must be triaged explicitly: either carry the capability changes into the
editable tree with tests/docs, or document that they are intentionally removed by
the v1.8 sync.

## v1.8 Workstream Rules

- Work in the editable skill tree.
- Do not synchronize the installed skill until the final v1.8 install phase.
- Do not edit Scientific Workbench during skill-side phases.
- Preserve v1.6 and v1.7 regressions as baseline confidence gates.
- Prefer narrow wrappers, docs, and regressions over broad rewrites.
- Treat optional and legacy routes as controlled blocks when their backend is
  absent.
- Keep original user inputs read-only; work on copies when executing,
  transforming, or testing.
- If app-ready behavior would require a large redesign, document it as P2
  backlog for v1.9 or v2.0.

## v1.8 Phase Outputs

The v1.8 series should produce:

- an app-ready JSON contract;
- a 59-capability app-readiness matrix for the editable public surface
  (`references/v1-8-app-readiness-matrix.md`);
- an app-ready run-bundle contract for deterministic execution folders
  (`references/v1-8-run-bundle-contract.md`);
- app-like regressions for general routes;
- app-like regressions for science, astronomy, optional, and legacy routes;
- a run-bundle contract;
- a deterministic dry-run router or a documented decision not to ship one;
- a v1.8 user/developer guide in PDF and TeX;
- a release candidate gate that proves v1.8 is ready before install sync.

## Closure Criteria

v1.8 can be declared installed only when:

- the editable release candidate has no `FAIL` or `ROTO`;
- accepted `WARNING` and `BLOCKED_CONTROLADO` cases are documented;
- app-ready contracts and run-bundle contracts have regressions;
- the app-readiness matrix covers the complete editable public surface;
- public docs and generated snapshots have no drift;
- v1.6 and v1.7 affected regressions still pass;
- post-sync installed validation passes;
- Scientific Workbench remains unmodified by the skill-side v1.8 work.

## Phase 0 Decision

Proceed with v1.8 in the editable tree, with baseline status `WARNING` because
the installed tree has public-surface drift relative to the editable source of
truth. This warning does not require immediate rollback in Phase 0, but it must be
resolved before final v1.8 installation.

## Phase 8 Documentation Decision

Phase 8 adds the documentation and user/developer guide for the app-ready backend
release:

- `references/v1-8-scientificworkbench-integration.md`
- `references/guia_scientific_data_analysis_v1_8.tex`
- `references/guia_scientific_data_analysis_v1_8.pdf`
- `scripts/audit_v1_8_phase8_docs_regression.py`

The wording is deliberately conservative: v1.8 makes the skill backend
app-ready; it does not claim that Scientific Workbench is already synchronized to
v2.0. The final app sync remains a later milestone.

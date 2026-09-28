# v2.0 Integrated Release Charter

> English publication edition of a preserved private record at `d6583f1`.
> Original source: `skills/scientific-data-maintainer/.cache/archived_references/v2-0-integrated-release-charter.md`.
> Original SHA-256: `f2bd0cacb6ad7a783bf383246af3e5da9c8d9de1924eee53d2623a0c7ca2a26e`.
> Historical states and results are unchanged; this edition does not rerun them.
> Machine-specific paths use `$PRIVATE_WORKSPACE` (the original editable
> workspace) and `$HOME` aliases. Where shown, set `RUNS_DIR` to a fresh output
> root before reproducing a historical command; preserve earlier evidence.
> Original documents remain unchanged privately.

Status: Phase 0 charter for the v2.0 workstream.

This document defines v2.0 as the first integrated release between the
`scientific-data-analysis` skill and the native macOS app
Scientific Workbench. It is intentionally written before implementation work so
later phases can distinguish backend work, app work, and true dual-release
validation.

## Product Objective

v2.0 turns the v1.9 skill into a formally consumed backend for
Scientific Workbench. The user-facing target is:

- open Scientific Workbench;
- attach files or folders;
- ask in natural language;
- review a proposed workflow;
- execute local `scientific-data-analysis` capabilities safely;
- inspect artifacts, logs, previews, and job state;
- retry, cancel, or resume where supported;
- keep originals untouched;
- export or continue work with clear provenance.

The skill remains the deterministic execution engine. Scientific Workbench owns
the UI-driven workflow layer, provider selection, job state, previews,
interactive selectors, confirmations, and product-level recovery.

## Baseline Confirmed For Phase 0

- Installed skill path:
  `$HOME/.codex/skills/scientific-data-analysis`
- Editable skill path:
  `$PRIVATE_WORKSPACE/skill_work/scientific-data-analysis`
- App path:
  `$PRIVATE_WORKSPACE/ScientificWorkbench`
- Installed skill version expected by this phase: `v1.9 stable`.
- v1.9 completed:
  - artifact type freeze;
  - app-facing error hardening;
  - app hints and next actions;
  - exposure-mode boundaries;
  - v2.0 deferral guardrails;
  - app-like regression expansion;
  - no Scientific Workbench synchronization.

## Non-Goals

v2.0 must not:

- hide FAIL or ROTO states behind product wording;
- modify original user inputs;
- make optional backends core dependencies;
- expose legacy/domain-specific tools as normal actions without an expert or
  optional boundary;
- use cloud AI as the source of truth for scientific execution;
- leak provider keys, tokens, sensitive paths, stdout, stderr, transcripts, or
  artifacts;
- sync the installed skill or app before release-candidate gates pass.

## Deferred P1 Rows That Enter v2.0

The v1.9 inventory and deferral guardrail preserve exactly eight P1 rows for
v2.0:

| Row | Target | v2.0 owner |
|---:|---|---|
| 8 | `fits_rgb_batch.py` | Progress UI, interactive job control, previews, and job history for RGB/FITS batches. |
| 10 | `stilts_workbench.py` | Optional STILTS/TOPCAT panel and native-alternative routing. |
| 13 | `radial_velocity_workbench.py inspect` | Interactive column/unit selector and guided RV inspection. |
| 26 | `photometric_solution.py` | Interactive calibration-column selector and prefit review. |
| 28 | `apt_workbench.py` | Optional APT panel, backend state, logs, and alternatives. |
| 34 | `office_roundtrip.py docx-style-inventory` | Visual style selector and match preview. |
| 35 | `office_roundtrip.py docx-styled-replace` | Visual diff/confirmation before edited-copy replacement. |
| 37 | `keynote_export.py` | GUI confirmation and controlled Keynote automation. |

These rows are not backend-only fixes. They require Scientific Workbench-side UX
or orchestration to be genuinely closed.

## Additional v2.0 Scope

v2.0 also owns the broader product items explicitly deferred from v1.9:

- major synchronization with Scientific Workbench;
- UI-driven workflows;
- app planner plus skill as a formal execution engine;
- job history, previews, and status consumed directly by the app;
- joint skill plus app documentation;
- app-side adoption of envelopes, run bundles, typed artifacts, app hints,
  next actions, and clean error kinds;
- dual release gates over both the editable skill and Scientific Workbench;
- post-sync validation of the installed skill and the app using that installed
  skill.

## Backend/App Boundary

The skill owns:

- public capability registry;
- deterministic scripts;
- summary JSON;
- manifest JSON;
- typed artifacts;
- run-bundle contracts;
- app-facing warnings/errors;
- next actions;
- provenance and original-modified policy.

Scientific Workbench owns:

- SwiftUI interaction;
- local/cloud provider selection;
- plan review and dry-run UI;
- workflow state;
- progress/cancel/retry/resume controls;
- artifact discovery and previews;
- optional-backend panels;
- visual selectors and confirmations;
- support bundles;
- release packaging and app quality gates.

Shared contracts must be validated from both sides.

## Phase Order

1. Phase 0: charter and dual baseline.
2. Phase 1: integrated skill plus app contract.
3. Phase 2: app-side parser and artifact discovery.
4. Phase 3: science, astronomy, and optional-backend deferred rows.
5. Phase 4: documents, iWork, and GUI deferred rows.
6. Phase 5: formal planner and workflow model.
7. Phase 6: UI-driven workflows and exposure modes.
8. Phase 7: job history, previews, states, and support.
9. Phase 8: end-to-end dual regressions.
10. Phase 9: joint documentation and v2.0 guide.
11. Phase 10: dual release candidate.
12. Phase 11: final install/sync and post-sync validation.
13. Controlled rollback only if sync or post-sync validation fails.

Phase 4 status on 2026-06-14: P1 rows 34, 35, and 37 are closed in the
editable skill and Scientific Workbench trees with copy-only workflows, explicit
confirmation, typed document artifacts, visual QA, and dual regressions. The
installed skill remains unchanged.

Phase 7 status on 2026-06-15: Scientific Workbench persists app-facing envelope
metadata in job history, re-indexes interrupted run bundles, preserves captured
sidecars and useful artifacts for cancelled/failed jobs, previews bounded
image/PDF/table/Markdown/notebook/JSON/log artifacts, exports redacted per-job
support bundles, and distinguishes individual retry from resumable workflow
execution. The installed skill remains unchanged.

Phase 8 status on 2026-06-15: the dual end-to-end gate passed in the editable
tree with 10/10 required families covered, zero FAIL/ROTO, unchanged originals,
151 Swift tests, Scientific Workbench quality gate, packaged real-run smoke, and
decision `LISTO_PARA_FASE_9`. The DOCUS benchmark remained optional and the
Accessibility-driven UI smoke was skipped in favor of deterministic headless
and packaged paths. The installed skill remains unchanged.

Phase 9 status on 2026-06-16: joint skill plus app documentation is expected to
explain product boundaries, local-first execution, optional cloud providers,
Codex bridge use, workflow testing, sync policy, and limitations before any
release-candidate or installed-skill synchronization.

## Closure Criteria

v2.0 can be declared only when:

- the eight deferred P1 rows are closed, blocked honestly by environment, or
  explicitly validated through app-side UX;
- Scientific Workbench parses and displays skill envelopes, run bundles, typed
  artifacts, app hints, next actions, and clean errors;
- guided app workflows do not modify original inputs;
- optional, expert, legacy, and maintainer-only exposure boundaries are visible
  in the app;
- `swift test` and the selected app quality gates pass;
- skill `py_compile`, public-surface check, v2.0 regressions, affected v1.9
  regressions, and portable smoke pass;
- joint documentation exists;
- the installed skill and app are validated together after sync;
- no FAIL or ROTO is hidden or accepted without a documented block.

## Phase 0 Read-Only App Policy

Phase 0 reads Scientific Workbench for compatibility only. It must not edit the
app. The phase regression can compare a stored SHA-256 manifest of the app files
read during Phase 0 against current hashes to confirm the read-only boundary.

## Risks

- Scope creep: moving v2.0 into a full app redesign instead of integration.
- Contract drift: app parser and skill envelopes evolve separately.
- Optional-backend confusion: STILTS/TOPCAT/APT/Keynote are presented as core.
- Safety regression: original user data is modified or secrets are logged.
- Test bloat: realistic gates become too slow for regular release work.

## Phase 0 Decision

Proceed to Phase 1 only if the baseline regression passes and confirms:

- installed skill is v1.9 stable;
- the eight v2.0 deferral rows are present and still P1;
- Scientific Workbench exists with the expected roadmap, architecture, runner,
  parser, artifact discovery, and tests;
- Phase 0 did not modify Scientific Workbench;
- the v2.0 charter exists and contains the required closure criteria.

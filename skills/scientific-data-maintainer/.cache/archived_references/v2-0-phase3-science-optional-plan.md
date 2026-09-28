# v2.0 Phase 3 Science, Astro, and Optional Prep Plan

Phase 3 prepares the deferred scientific, astronomy, and optional-backend P1
work for v2.0. This reference is intentionally preparatory: it does not close
the individual P1 rows. The concrete implementations are reserved for the
individual prompts P1-8, P1-10, P1-13, P1-26, and P1-28.

## Scope

Phase 3 turns the v1.9 deferrals into a controlled work queue for
ScientificWorkbench integration. It defines exposure mode, safety boundary,
input/output expectations, backend policy, and the exact prompt order for the
five scientific/optional targets.

## Non Goals

- No UI-driven workflow is implemented in this preparatory step.
- No command builder is added in this preparatory step.
- No scientific backend contract is changed in this preparatory step.
- No optional backend is made mandatory.
- No original user data may be modified.
- No installed skill synchronization occurs.
- No ScientificWorkbench source file is edited by this preparatory step.

## Target Queue

| Deferred row | Prompt | Target | Exposure for app | Input family | Expected app-facing result | Backend policy | Safety boundary |
|---:|---|---|---|---|---|---|---|
| 8 | P1-8 | `fits_rgb_batch.py` | expert_science | grouped FITS images copied to a run folder | run bundle with manifest, summary, typed artifacts, previews, progress/job state when implemented | native datanalysis backend; no GUI dependency | No original FITS modified; progress UI and job control are app-side v2.0 work |
| 10 | P1-10 | `stilts_workbench.py` | optional_panel | CSV/FITS/VOTable/catalog tables copied to a run folder | PASS when STILTS is present; BLOCKED_CONTROLADO with native alternative when absent | STILTS/TOPCAT remain optional | Relegate from normal mode unless explicit STILTS/TOPCAT route is requested |
| 13 | P1-13 | `radial_velocity_workbench.py inspect` | expert_science | RV tables/manifests copied to a run folder | guided inspect result with clear units/column assumptions and typed artifacts | backend stays scientific/domain-specific | Interactive column/unit selector belongs to the app prompt, not to this prep step |
| 26 | P1-26 | `photometric_solution.py` | expert_science | standard-star calibration table copied to a run folder | fit summary, plots/tables, app hints, and prefit review when implemented | preserve first-order photometric fit contract | Interactive calibration-column selector belongs to the app prompt |
| 28 | P1-28 | `apt_workbench.py` | optional_panel | copied image/source-list/preferences bundle | PASS when APT backend is present; BLOCKED_CONTROLADO with visual/native alternative when absent | APT remains optional | No original image or preference file modified; panel/log handling is app-side v2.0 work |

## Exposure Rules

- `expert_science` targets may appear in scientific/astro expert workflows, not
  in normal general-purpose intake.
- `optional_panel` targets may appear only when the user explicitly asks for the
  optional backend or when a copied project already declares that backend.
- The router should reject or relegate these targets for generic office,
  personal, or business inputs.
- Domain-specific outputs must not be marketed as general real-world workflows.

## Native Alternatives

- `stilts_workbench.py`: when STILTS/TOPCAT is absent, the app should surface a
  clean BLOCKED_CONTROLADO and, where relevant, suggest native table inspection
  or `catalog_workbench.py crossmatch-sky` instead of pretending STILTS ran.
- `apt_workbench.py`: when APT is absent, the app should surface a clean
  BLOCKED_CONTROLADO and, where relevant, suggest native FITS inspection,
  image QA, or aperture-photometry preparation rather than invoking APT.

## Prompt Order

1. P1-8: `fits_rgb_batch.py`
2. P1-10: `stilts_workbench.py`
3. P1-13: `radial_velocity_workbench.py inspect`
4. P1-26: `photometric_solution.py`
5. P1-28: `apt_workbench.py`

This order starts with the heaviest app job/run-state case, then closes optional
backend panels, then the two guided scientific selectors. Each prompt must
produce its own app-side tests and skill-side regression where it changes code.

## Individual Closure Tracking

- P1-13 `radial_velocity_workbench.py inspect`: closed in the editable skill
  and ScientificWorkbench by
  `references/v2-0-p1-13-radial-velocity-selector.md` and
  `scripts/audit_v2_0_p1_13_radial_velocity_selector_regression.py`.
  The CLI contract remains unchanged; the column/unit selector and normalized
  `.vels` staging are app-side.
- P1-26 `photometric_solution.py`: closed in the editable skill and
  ScientificWorkbench by
  `references/v2-0-p1-26-photometric-calibration-selector.md` and
  `scripts/audit_v2_0_p1_26_photometric_calibration_regression.py`.
  The first-order fit remains unchanged; table preview, column/passband
  selection, range validation, and canonical copied-input staging are app-side.
- P1-28 `apt_workbench.py`: closed in the editable skill and
  ScientificWorkbench by
  `references/v2-0-p1-28-apt-optional-panel.md` and
  `scripts/audit_v2_0_p1_28_apt_optional_panel_regression.py`.
  APT remains optional; the app reports command/preferences/batch readiness,
  preserves preflight Jobs and artifacts, and offers native FITS/noise routes.

## Preparatory Acceptance Criteria

- The five targets are present and mapped to deferred rows 8, 10, 13, 26, and
  28 from `references/v1-9-v2-0-deferrals.md`.
- Phase 3 states explicitly that individual P1 closure is reserved for the
  target prompts.
- Exposure is limited to `expert_science` and `optional_panel`; there is no
  normal-general promise.
- Optional backends are allowed to block cleanly.
- Native alternatives for STILTS and APT are documented.
- No installed synchronization is performed.
- ScientificWorkbench remains unchanged by this preparatory step.

## Future Prompt Deliverables

Each individual P1 prompt should report:

- app mode: normal, expert, optional, or not exposed;
- copied input path and original-modification check;
- command builder or guided workflow changes, if any;
- UI/panel/preflight changes, if any;
- skill-side regression;
- app-side test;
- typed artifacts and run-bundle behavior;
- warnings, blocked states, and limits.

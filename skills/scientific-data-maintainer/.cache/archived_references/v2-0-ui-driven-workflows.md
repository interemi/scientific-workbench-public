# v2.0 UI-Driven Workflows

Status: Phase 6 implementation contract for ScientificWorkbench and the
editable `scientific-data-analysis` skill.

## Goal

ScientificWorkbench opens on a useful work surface and lets a person choose,
configure, run, inspect, and cancel workflows without first writing a CLI
command. The CLI remains available as an advanced override, not as the normal
interaction model.

The skill remains the execution engine. ScientificWorkbench supplies guided
controls, stages safe inputs where required, writes every output into a fresh
run directory, parses the envelope, and discovers typed artifacts.

## Exposure Policy

| Surface | Count | Meaning | Direct-run policy |
|---|---:|---|---|
| Normal | 25 | General and adaptable daily workflows | Guided controls; no domain confirmation |
| Expert | 13 | Scientific or domain-specific workflows | Visible only in Expert; explicit review required |
| Optional | 8 | External backend or platform feature | Visible only in Optional; preflight and controlled blocking |
| Legacy | 9 | Narrow coursework or legacy environment | Visible only in Legacy; explicit review required |
| Maintenance | 6 | Release, validation, and maintainer gates | Hidden from every user catalog mode; Maintenance only |

The counts cover all 61 public registry rows. The 55 user-facing rows belong to
exactly one of Normal, Expert, Optional, or Legacy. Maintainer-only rows never
enter those four lists.

## UI Contract

- `CapabilityCatalogView` provides a compact Normal / Expert / Optional /
  Legacy segmented control.
- Search applies only inside the selected exposure mode.
- Selecting a capability from Settings or an optional-backend alternative also
  selects its correct exposure mode.
- Expert and Legacy execution controls stay disabled until the user confirms
  that domain and safety requirements were reviewed.
- Optional astronomy routes expose Java, STILTS, TOPCAT, APT preferences,
  readiness, logs, native alternatives, and controlled blocking in the
  capability workspace. The same diagnostics remain available in Settings.
- Maintainer-only capabilities are reachable only through Maintenance.
- Agent, Jobs, Results, Settings, and the useful Home dashboard keep their
  existing roles. No marketing or landing-page screen was introduced.

## Guided Workflows Added Or Hardened

Dedicated forms:

- `photometry_noise_budget`: source, sky, dark, read noise, aperture, frames,
  units, and gain.
- `timeseries_forecasting_workbench`: source table, title, date/value columns,
  frequency, horizon, language, and runtime.
- `deliverable_factory.scaffold`: kind, format, title, and language.
- `bootstrap_analysis_notebook`: domain, language, runtime, title, and optional
  data source.
- `companion_route_check`: natural-language task plus selected filename and
  format context.

Default guided command construction:

- `scientific_writeup_review`
- `semantic_diff`, with an explicit baseline-and-candidate requirement
- `physical_qa`
- `presentation_workbench.inspect`
- `presentation_workbench.existing-deck-style-audit`
- `latex_workbench.scaffold`
- `latex_workbench.review`
- `latex_workbench.compile`
- `notebook_branch_compare`
- the five form-backed routes above where a safe default command also exists
  (`deliverable_factory.scaffold`, `bootstrap_analysis_notebook`, and
  `timeseries_forecasting_workbench`)

All 25 Normal capabilities now have either a dedicated form or a safe guided
command. Advanced arguments remain an override, not a requirement, in Normal.

Previously implemented guided surfaces remain in place for radial velocity,
photometric calibration, DOCX style inventory/replacement, Keynote preflight,
STILTS/TOPCAT/APT readiness, FITS/table/container inspection, notebook copy,
document intake, and cross-domain bundles.

## Honest Limits

Some Expert, Optional, and Legacy capabilities still require advanced
arguments because a generic form would hide domain assumptions or backend
requirements. They remain correctly classified and are not exposed in Normal.
The UI says that the guided form is not yet safe instead of pretending the
route is generally app-ready.

Legacy and domain-specific tools are not generalized by analogy. Missing
optional backends remain `BLOCKED_CONTROLADO`, not failures and not silent
successes.

## Verification

- Swift build and test-target compilation.
- Exposure policy tests for 25 Normal, 13 Expert, 8 Optional, 9 Legacy, and 6
  Maintenance rows.
- Command-builder tests for new guided routes and the two-input semantic diff
  guard.
- `scripts/audit_v2_0_phase6_ui_workflows_regression.py`.
- Headless ScientificWorkbench transcript using the deterministic local
  planner; no maintainer capability may appear in the generated user plan.
- Input fingerprint comparison before and after the headless run.

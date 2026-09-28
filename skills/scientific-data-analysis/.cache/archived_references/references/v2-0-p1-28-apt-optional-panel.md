# v2.0 P1-28: APT Optional Panel

`apt_workbench.py` remains an optional astronomy backend. ScientificWorkbench
exposes APT command, saved preferences, batch readiness, logs, outputs, and
native alternatives without making Java or APT core dependencies.

## Real Machine State

The P1-28 audit on June 13, 2026 found:

- Java 17: available;
- APT command: unavailable;
- saved `APT.pref`: unavailable;
- APT batch readiness: `BLOCKED_CONTROLADO`.

This is a valid optional-backend state. Core ScientificWorkbench and
scientific-data-analysis workflows remain usable.

## App Panel

The optional astronomy panel reports:

- APT command readiness;
- saved preference readiness;
- combined batch readiness;
- a human-readable blocking message;
- specific next actions;
- the latest APT Job status and artifact count.

Users can select explicit `APT.csh`/`APT.bat` and `APT.pref` files. These paths
are local settings. `Run APT Preflight` creates a normal ScientificWorkbench
Job, so command, stdout, stderr, parsed status, and `summary.json` remain
inspectable in Jobs and Results.

## Reproducible Batch Route

The supported backend sequence is:

1. `apt_workbench.py prepare-source-list`
2. `apt_workbench.py run-batch`
3. `apt_workbench.py parse-results`

The source table, image, and saved preferences must be copied into a controlled
run or test directory before execution. A real batch run can emit:

- `summary_json`;
- `manifest_json`;
- APT output table;
- parsed `table_csv`;
- command log;
- stdout `log_txt`;
- stderr `log_txt`.

APT preferences are scientific provenance because they control aperture,
background, and coordinate interpretation.

## Controlled Absence

When APT or `APT.pref` is absent:

- backend state: `BLOCKED_CONTROLADO`;
- `errors.kind`: `missing_optional_backend`;
- `original_modified`: `false`;
- no output table that looks scientifically valid is created;
- `next_actions` instruct the user to configure APT and save preferences or
  choose a native route.

ScientificWorkbench maps a blocked envelope to a blocked Job even when the CLI
returns exit code 2.

## Native Alternatives

The panel offers:

- `inspect_fits.py` for native FITS/header/WCS/visual inspection;
- `photometry_noise_budget.py` for a native measurement and SNR preparation
  route.

For fully code-native aperture photometry, the skill documentation continues
to recommend `aperture_photometry.py`/photutils when APT compatibility is not
required. That helper is not promoted as a new public capability by this
change.

## Exposure And Safety

- Exposure: `optional_panel`.
- APT is not core.
- The app does not install or automate the APT GUI.
- Originals are never modified.
- Saved preferences are never inferred silently.
- APT results remain domain-specific astronomy photometry outputs.

## Regression

`scripts/audit_v2_0_p1_28_apt_optional_panel_regression.py` validates:

- real Java/APT/preference state;
- synthetic copied source table, image, and preferences;
- source-list preparation;
- fake controlled APT batch execution;
- logs, manifest, output table, and parsed CSV;
- blocked missing-backend behavior with specific next actions;
- app panel, command builder, blocked Job mapping, native alternatives, and
  Swift tests.

## Validation Result

Validation completed on June 13, 2026:

- P1-28 regression: `PASS`;
- phase 2 parser/artifact regression: `PASS`;
- phase 3 science/optional regression: `PASS`;
- v1.9 error contract regression: `PASS`;
- v1.9 artifact type regression: `PASS`;
- public surface synchronization check: `PASS`, with no drift;
- ScientificWorkbench Swift suite: `125/125 PASS`.

No installed skill synchronization was performed.

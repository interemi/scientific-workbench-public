# v1.8 Workflow Router Dry-Run

Status: Fase 5 design note for the editable v1.8 workstream.

`scripts/scientific_workflow_router.py` is a deterministic planning backend for
ScientificWorkbench and for CLI users who want a conservative first diagnosis.
It does not execute downstream capabilities, does not mutate inputs, and does
not replace expert tools. Its job is to describe the input, recommend likely
routes, reject unsafe or mismatched routes with reasons, and return an app-ready
JSON envelope.

## Modes

| Mode | Purpose |
|---|---|
| `inspect` | Inventory the input path and recommend candidate capabilities. |
| `plan` | Return a dry-run plan with commands that a person/app may execute later on copies. |
| `explain` | Explain why a requested capability applies, does not apply, or is unknown for the input. |

## Contract

The router emits the v1.8 app-ready fields needed by ScientificWorkbench:

- `contract_version: "1.8"`
- `status` plus normalized `app_status`
- `input_kind`
- `recommended_capabilities`
- `rejected_capabilities`
- `plan_steps`
- `required_backends`
- `safety_notes`
- `next_actions`
- `original_modified: false`

The router also preserves the standard skill envelope: `tool`, `notes`,
`artifacts`, `results`, `qa`, `warnings`, `errors`, `provenance`,
`typed_artifacts`, and `app_hints`.

## Conservative Input Kinds

Initial routing supports common app-facing families:

- `table_csv`, `table_like`, `table_folder`
- `mixed_folder`
- `notebook_ipynb`, `notebook_folder`
- `fits_file`, `fits_folder`, `fits_like_unverified`
- `archive_container`, `archive_folder`, `archive_like_unverified`
- `document_file`, `document_folder`
- `missing_path`, `empty_directory`
- `unknown_file`, `generic_directory`, `unsupported_path`

If the router does not know, it says so. Unknown inputs are `WARNING`, not a
false pass. Missing paths and empty folders are `BLOCKED_CONTROLADO` with a
next action.

For table-like inputs the router stays conservative, but it can promote a
specialized route when the app/user task says so:

- time-series or forecasting language promotes
  `timeseries_forecasting_workbench.py` before ordinary table profiling;
- sensor, measurement, range, NaN/Inf, uncertainty, or QA language promotes
  `physical_qa.py` before ordinary table profiling.
- document/admin/intake/handoff language promotes
  `document_intake_workbench.py` before the broader cross-domain route for
  mixed folders.

If those task signals are absent, ordinary `profile_table.py` remains the first
recommendation.

## Safety Boundary

- The router is read-only except for optional `--summary-json` and
  `--manifest-json` outputs.
- It never deserializes notebooks as executable code.
- It checks only lightweight file signatures, suffixes, and directory contents.
- It does not call Astropy, DuckDB, Jupyter, Keynote, Quick Look, STILTS, APT,
  IRAF, or TEAREDUCE.
- It does not edit ScientificWorkbench or synchronize the installed skill.

## Regression

The focused gate is:

```bash
python3 scripts/audit_v1_8_phase5_router_regression.py
```

It creates six temporary fixtures: CSV, mixed folder, legacy notebook, fake
FITS, missing path, and empty folder. For each case it validates JSON
parseability, v1.8 fields, app status, manifest/summary outputs, and unchanged
input hashes.

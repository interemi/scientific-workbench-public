# v1.8 Run Bundle Contract

Status: Fase 4 contract for the editable v1.8 workstream.

This reference defines the local run-folder shape that
`ScientificWorkbench` can discover without relying on brittle recursive
heuristics. It complements `references/v1-8-app-ready-contract.md`: the JSON
envelope explains what happened, while the run bundle gives every execution a
stable filesystem home.

## Product Goal

Every app-like run should be able to leave one directory that is safe to show,
inspect, archive, or hand off:

```text
run/
  manifest.json
  summary.json
  stdout.txt
  stderr.txt
  command.txt
  artifacts/
  previews/
  reports/
  tables/
  logs/
  next_steps.md
```

The folder is a contract for app discovery, not a mandate to rewrite every
legacy script in v1.8. Existing script-specific outputs remain valid. New or
migrated app-ready routes should add this structure when `--run-dir` is used or
when the command is executed through `scripts/app_run_bundle.py`.

## Required Files

| Path | Required | Meaning |
|---|---:|---|
| `summary.json` | yes | Final v1.8 app-ready envelope. It should include `contract_version`, `app_status`, typed artifacts, warnings/errors, provenance, and `next_actions`. |
| `manifest.json` | yes | Run-level manifest with command, environment, captured logs, outputs, and the child tool manifest when available. |
| `stdout.txt` | yes | Captured stdout from the child command. Direct `--run-dir` integrations may leave a placeholder; `app_run_bundle.py` captures real stdout. |
| `stderr.txt` | yes | Captured stderr from the child command. Direct `--run-dir` integrations may leave a placeholder; `app_run_bundle.py` captures real stderr. |
| `command.txt` | yes | Shell-quoted command and working directory, with home paths redacted through the standard public-path helpers. |
| `next_steps.md` | yes | Human-readable next actions derived from the envelope status, warnings, errors, and `next_actions`. |

## Required Directories

| Path | Meaning |
|---|---|
| `artifacts/` | Generic products that do not fit a narrower typed directory yet. |
| `previews/` | Static visual previews such as PNG quicklooks. |
| `reports/` | Human-readable reports, usually Markdown. |
| `tables/` | CSV/TSV/tabular products. |
| `logs/` | Extra logs from child tools or optional backends. Top-level stdout/stderr remain canonical. |

The directories must exist even if empty. That keeps app-side discovery simple:
the app can render a stable run shell first, then list typed artifacts.

## Relationship To The v1.8 JSON Envelope

`summary.json` is the canonical envelope for app parsing. It should keep the
v1.6/v1.7 legacy fields while adding v1.8 app fields:

- `contract_version: "1.8"`
- `app_status`
- `typed_artifacts`
- `original_modified`
- `warnings`
- `errors`
- `next_actions`
- `app_hints`

Run-bundle files should also appear as typed artifacts when possible:

| Run-bundle file | Artifact type |
|---|---|
| `summary.json` | `summary_json` |
| `manifest.json` | `manifest_json` |
| `stdout.txt` | `log_txt` |
| `stderr.txt` | `log_txt` |
| `command.txt` | `log_txt` |
| `next_steps.md` | `report_md` |
| `run/` | `handoff_bundle` |

## Recommended Invocation Patterns

Preferred app-style wrapper:

```bash
python scripts/app_run_bundle.py \
  --run-dir tmp/run \
  --tool profile_table \
  -- \
  python scripts/profile_table.py input.csv --run-dir tmp/run
```

Direct app-ready route where implemented:

```bash
python scripts/profile_table.py input.csv --run-dir tmp/run
```

The wrapper is the canonical way to capture `stdout.txt` and `stderr.txt`.
Direct `--run-dir` support is a convenience for scripts and regressions; it
creates the bundle structure and standard paths, but it cannot capture its own
stdout/stderr without a parent process.

## Migrated v1.8 Fase 4 Targets

Fase 4 migrates the following priority routes because the change is narrow and
compatible with existing flags:

- `profile_table.py`
- `cross_domain_data_workbench.py`
- `document_intake_workbench.py`
- `inspect_data_container.py`

Each keeps its existing `--summary-json`, `--manifest-json`, and `--output-dir`
behavior. `--run-dir` only supplies defaults when those paths are omitted.

## Existing Output Producers

Many scripts already produce parts of the bundle contract:

- `summary.json`: most public tools with `--summary-json`.
- `manifest.json`: tools with `--manifest-json` and `write_manifest`.
- backend logs: `apt_workbench.py`, notebook runners, TEAREDUCE routes, and
  pipeline workbenches that capture child stdout/stderr.
- output directories: document intake, cross-domain workbench, forecasting,
  notebook execution, FITS/RGB routes, presentations, and report builders.

Fase 4 does not move all of those tools. It establishes the contract and proves
the helper path on high-value general routes.

## P2 Migration Backlog

The following migrations are useful but intentionally deferred unless a later
phase asks for them:

- notebook execution families: move executed copies and workspace logs into the
  run bundle while preserving current output layout;
- presentation/iWork/Quick Look tools: place previews under `previews/` and
  reports under `reports/`;
- FITS/RGB and astronomy pipelines: add run-bundle support without disrupting
  existing science manifests;
- optional backends such as STILTS/APT/TEAREDUCE: normalize backend logs into
  `logs/` while keeping controlled-block behavior;
- legacy coursework routes: expose run bundles only in expert mode, not normal
  app mode.

## Validation Requirements

A v1.8 run-bundle regression must verify:

- all required files exist;
- all required directories exist;
- `summary.json` and `manifest.json` parse as JSON;
- `summary.json` has a valid v1.8 app envelope;
- typed artifact records include valid artifact types;
- original inputs are not modified;
- `next_steps.md` is non-empty and readable by a person;
- broken/blocked runs fail cleanly without raw traceback leakage.

## Integration Note

ScientificWorkbench already expects run folders and discovers artifacts
recursively. v1.8 makes that expectation explicit on the skill side, but it does
not imply that the app has adopted the full contract yet. The app-side adoption
of `typed_artifacts`, `app_hints`, and mode-specific exposure belongs to the
future v2.0 synchronization path.

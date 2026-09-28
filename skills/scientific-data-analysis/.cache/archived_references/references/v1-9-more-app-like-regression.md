# v1.9 More App-Like Regressions

Status: priority pass for imperfect app-like inputs.

This reference extends the v1.9 app-like regression layer with intentionally
imperfect inputs. It does not edit ScientificWorkbench, does not require
optional backends, and does not replace the broader Deuda R regression.

## Goal

Validate that app-facing routes stay useful when inputs are realistic but not
clean:

- duplicate columns, infinities, and empty columns;
- mixed project folders with profile warnings;
- row-count changes in compared tables;
- notebooks with `input()` or answer-cell risks;
- branch folders with missing outputs;
- time series with duplicate/unparseable dates;
- ZIP archives with unsafe member names.

Each case must keep output parseable, preserve originals, emit typed artifacts,
and surface warnings or clean failures instead of raw tracebacks.

## Targets

| Target | Imperfect input | Expected app-facing behavior |
|---|---|---|
| `profile_table.py` | duplicate header, `inf`, all-null column | `WARNING`, summary artifact, no mutation |
| `cross_domain_data_workbench.py` | mixed folder with table warning | `WARNING` or `PASS` with typed bundle artifacts |
| `semantic_diff.py` | baseline/candidate CSV row-count change | `WARNING`, report artifact |
| `coursework_notebook_fidelity_check.py` | notebook with `input()` and answer-cell risk | `WARNING`, report artifact |
| `notebook_branch_compare.py` | branch missing product output | `WARNING`, comparison artifacts |
| `timeseries_forecasting_workbench.py` | duplicate and unparseable dates | `WARNING`, notebook/handoff artifacts |
| `inspect_data_container.py` | ZIP with path traversal member | `WARNING`, safe inspection artifact |

## Backlog

| Item | Reason |
|---|---|
| optional backend positive paths | Keep out of priority coverage; they require local optional installs. |
| GUI/platform previews | Belongs to targeted platform passes or v2.0. |
| full ScientificWorkbench job flow | Reserved for v2.0 sync. |
| helper migration | Owned by Deuda F/G1, not by this priority pass. |

## Regression

`scripts/audit_v1_9_more_app_like_regression.py` writes temporary fixtures and
outputs under `tmp/v1_9_priority_more_app_like/`.

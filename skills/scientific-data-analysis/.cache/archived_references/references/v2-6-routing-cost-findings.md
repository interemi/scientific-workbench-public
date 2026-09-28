# v2.6 Routing Cost Findings

This file records the first v2.6 observed-usage pass. The current figures are
local proxy measurements from the deterministic harness, not Codex weekly usage
or billing tokens. They are useful for comparing relative routing weight inside
the same harness, but they are not a promise of real account-level savings.

- The mother skill remains the normal broad entrypoint.
- Child direct routes are expected to be cheaper for expert, already-scoped
  work because they avoid loading broad routing context.
- No public routing contract change is justified from one proxy run alone.

## Harness Result

Source: `tmp/v2_6_phase2_observed_usage_harness/observed_usage.jsonl`

| Scenario | Route | Status | Local proxy tokens | Notes |
|---|---|---:|---:|---|
| `table_professional_csv` | child direct | PASS | 1975 | Direct table profiling through `scientific-data-notebooks`. |
| `mixed_folder_router` | mother | PASS | 20484 | Broad inspection plan through the mother router. |
| `legacy_notebook_inspect` | child direct | BLOCKED_CONTROLADO | 811 | System Python lacks `nbformat`; failure is clean and parseable. |
| `document_admin_intake` | child direct | PASS | 3605 | Document bundle processed on synthetic copies. |
| `fits_simple_inspect` | child direct | PASS | 1313 | Minimal FITS inspection with simple fallback. |
| `optional_stilts_block` | optional backend | BLOCKED_CONTROLADO | 1457 | Missing STILTS command blocks cleanly. |
| `maintainer_surface_check` | maintainer | PASS | 162 | v2.5 budget-deferral regression stays cheap and parseable. |
| `router_vs_direct_table` | mother | PASS | 20565 | Mother planning on the same CSV is much heavier than direct profiling. |

## Interpretation

The strongest signal is the CSV comparison:

- direct child profiling: 1975 local proxy tokens;
- mother router planning: 20565 local proxy tokens.

That does not prove real Codex weekly-token savings, but it supports the v2.5
architecture decision: keep the mother skill as the safe broad entrypoint, and
use child skills directly when intent is already scoped.

## Preliminary Decision

Use child skills directly only when the user intent is already narrow:

- FITS/WCS/photometry/spectroscopy: `scientific-data-astro`
- documents/PDF/Office/LaTeX/reporting: `scientific-data-documents`
- tables/notebooks/containers/time series: `scientific-data-notebooks`
- release gates/smoke/plugin-eval: `scientific-data-maintainer`

The mother skill should stay the safe default for ambiguous or mixed work.

## v2.6 Action

No trigger rewrite or public contract change is applied in v2.6 from this single
pass. The evidence is recorded and guarded by regressions so later releases can
compare repeat runs before changing routing text.

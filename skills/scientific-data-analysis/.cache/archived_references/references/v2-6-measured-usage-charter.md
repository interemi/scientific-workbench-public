# v2.6 Measured Usage Charter

v2.6 is the measured-usage release for the `scientific-data-analysis` family.
It follows v2.5, which removed required plugin-eval fixes and left only the
accepted static `deferred_cost_tokens-budget-high` recommendation.

## Product Goal

Measure representative real workflows before making another architecture move.
The goal is not to promise lower weekly usage by intuition, but to collect
repeatable evidence about where Codex-facing skill usage is likely to be
expensive and where routing to child skills is cheaper.

## Non Goals

- Do not redesign the v2.5 mother/child architecture without measured evidence.
- Do not edit or synchronize ScientificWorkbench.
- Do not change artifact types, JSON envelopes, run bundles, or public
  capability contracts.
- Do not treat static plugin-eval deferred-token warnings as failures when all
  required fixes are closed.
- Do not use private user data for benchmarks.

## Scope

- Define a small benchmark matrix that covers the mother skill and the four
  child skills.
- Build deterministic synthetic fixtures for tables, mixed folders, notebooks,
  documents, FITS, optional-backend blocking, maintainer gates, and router vs
  direct-child routes.
- Record local observed execution metrics and classify them honestly as local
  proxy measurements when plugin-eval cannot provide real token accounting.
- Keep app-ready behavior sane: parseable summaries, typed artifacts, clean
  warnings/errors, and `original_modified=false`.

## Closure Criteria

v2.6 is complete only when:

1. The charter, observed-usage contract, benchmark matrix, routing findings,
   optimization log, and guide v2.6 exist.
2. The benchmark matrix covers at least 8 representative scenarios and all five
   installed skills.
3. The harness produces `observed_usage.jsonl`, `result.json`, and `summary.md`
   from deterministic fixtures.
4. The app-ready sanity regression passes.
5. v2.3, v2.4, and v2.5 affected regressions still pass.
6. `portable_smoke_test.py --profile core` passes after final sync when the
   environment is available.
7. `plugin-eval:evaluate-skill` is rerun on all five installed skills.
8. `guia_scientific_data_analysis_v2_6.tex` and PDF exist and are copied to
   the Desktop.

## Risk Register

- `deferred_cost_tokens-budget-high` can remain as a static warning even when
  observed workflows are acceptable.
- Local proxy metrics are not billing metrics. They are useful for comparing
  deterministic routes, not for promising exact weekly usage savings.
- Optional backend absence is a valid `BLOCKED_CONTROLADO`, not a failure.
- More aggressive compaction belongs to a later release only if v2.6 evidence
  shows a clear payoff.

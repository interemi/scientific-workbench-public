# v2.6 Cost Optimization Log

v2.6 optimizes only where measured evidence supports a change. The first
optimization pass is deliberately conservative.

## Applied

- Added a deterministic benchmark matrix and local observed-usage harness.
- Added regression gates so future optimizations must preserve coverage,
  app-ready behavior, and non-destructive execution.
- Corrected the maintainer scenario to use a maintainer-owned regression instead
  of running the mother `sync_public_surface_docs.py --check` from the child
  skill tree.
- Captured stdout JSON from regressions as `summary_json` when a scenario does
  not natively accept `--summary-json`.
- Recorded local proxy evidence that direct child routes are lighter than mother
  routing when the user intent is already scoped.
- Kept the v2.5 mother/child architecture unchanged.

## Not Applied

- No further file moves from active skill roots before measured usage proves
  they reduce real workflow cost.
- No trigger-rule rewrite from a single local proxy run.
- No ScientificWorkbench changes.
- No public artifact, envelope, registry, or run-bundle contract changes.
- No claim that v2.6 reduces weekly usage-limit consumption until plugin-eval or
  live Codex observed usage produces comparable real measurements.

## Next Decision Point

After several real representative runs, compare:

1. mother route vs child direct route for already-scoped tasks;
2. optional backend preflight cost vs native alternatives;
3. maintenance gates loaded through mother wrappers vs direct maintainer skill.

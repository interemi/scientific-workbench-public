# v2.6 Observed Usage Contract

The v2.6 harness records deterministic workflow observations in JSON Lines.
When plugin-eval cannot provide real token usage for a local scenario, the
record must say so and use clearly named local proxy fields.

## Required Fields

- `scenario_id`: stable id from `v2-6-benchmark-matrix.json`.
- `family`: broad scenario family such as `table`, `document`, `fits`, or
  `maintainer`.
- `skill`: expected skill surface.
- `route`: `mother`, `child_direct`, `maintainer`, or `optional_backend`.
- `command`: argv used for the local run.
- `status`: `PASS`, `WARNING`, `BLOCKED_CONTROLADO`, or `FAIL`.
- `returncode`: process exit code or null for skipped cases.
- `duration_ms`: wall-clock runtime for the command.
- `stdout_bytes` and `stderr_bytes`: raw local process output sizes.
- `summary_json`: produced summary path when the command supports it.
- `artifacts`: paths created by the scenario.
- `original_modified`: must be `false` for generated fixtures.
- `token_measurement_kind`: `plugin_eval_observed`, `local_proxy`, or
  `not_available`.
- `token_proxy_estimate`: optional integer estimate derived from local prompt,
  output, and fixture sizes; not a billing metric.
- `notes`: short caveat for interpretation.

## Interpretation Rules

- `plugin_eval_observed` is the only category that may be treated as real token
  accounting.
- `local_proxy` is useful for comparing routes inside this repo, but must not be
  described as real Codex billing usage.
- `BLOCKED_CONTROLADO` is acceptable for optional backend absence when the
  message is parseable and human-readable.
- A traceback, original mutation, missing summary where promised, or misleading
  success is `FAIL`.

## Output Files

The harness writes:

- `observed_usage.jsonl`
- `result.json`
- `summary.md`
- per-scenario `summary_json` files when supported by the capability

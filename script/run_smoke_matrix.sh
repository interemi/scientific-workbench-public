#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-smoke.XXXXXX")"
KEEP_SMOKE_MATRIX="${KEEP_SMOKE_MATRIX:-0}"

cleanup() {
  if [[ "$KEEP_SMOKE_MATRIX" != "1" ]]; then
    rm -rf "$TMP_ROOT"
  else
    echo "kept smoke matrix files at $TMP_ROOT"
  fi
}
trap cleanup EXIT

cd "$ROOT_DIR"
"$ROOT_DIR/script/swift_build.sh" >/dev/null
APP_BINARY="$("$ROOT_DIR/script/swift_build.sh" --show-bin-path)/ScientificWorkbench"

write_fixture_file() {
  local path="$1"
  local body="$2"
  mkdir -p "$(dirname "$path")"
  printf "%s" "$body" >"$path"
}

validate_transcript() {
  local transcript="$1"
  local case_name="$2"
  shift 2
  /usr/bin/python3 - "$transcript" "$case_name" "$@" <<'PY'
import json
import sys

transcript_path = sys.argv[1]
case_name = sys.argv[2]
expected = sys.argv[3:]

with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    raise SystemExit(f"{case_name}: missing structured agent_plan")
if plan.get("source") not in {"local", "skillRouter"}:
    raise SystemExit(f"{case_name}: expected local or skillRouter planner, got {plan.get('source')!r}")

steps = plan.get("steps")
if not isinstance(steps, list) or not steps:
    raise SystemExit(f"{case_name}: missing plan steps")
ids = [step.get("capability_id") for step in steps]
missing = [capability for capability in expected if capability not in ids]
if missing:
    raise SystemExit(f"{case_name}: missing expected capabilities {missing}; got {ids}")

estimate = plan.get("estimate", {})
if estimate.get("enabled_step_count") != len([step for step in steps if step.get("is_enabled", True)]):
    raise SystemExit(f"{case_name}: estimate enabled_step_count does not match enabled steps")

if payload.get("jobs") not in ([], None):
    raise SystemExit(f"{case_name}: smoke matrix should plan only, not execute jobs")

print(f"ok {case_name}: {' '.join(ids)}")
PY
}

run_case() {
  local case_name="$1"
  local prompt="$2"
  local input_path="$3"
  shift 3
  local output_root="$TMP_ROOT/output/$case_name"
  local transcript="$output_root/transcript.json"
  mkdir -p "$output_root"

  "$APP_BINARY" \
    --agent-input "$input_path" \
    --agent-mode workflow \
    --agent-local-planner \
    --agent-output-root "$output_root" \
    --agent-prompt "$prompt" \
    --agent-transcript-json "$transcript" \
    --agent-isolated-session \
    --agent-exit-after-run

  validate_transcript "$transcript" "$case_name" "$@"
}

run_no_input_case() {
  local case_name="$1"
  local prompt="$2"
  shift 2
  local output_root="$TMP_ROOT/output/$case_name"
  local transcript="$output_root/transcript.json"
  mkdir -p "$output_root"

  "$APP_BINARY" \
    --agent-mode workflow \
    --agent-local-planner \
    --agent-output-root "$output_root" \
    --agent-prompt "$prompt" \
    --agent-transcript-json "$transcript" \
    --agent-isolated-session \
    --agent-exit-after-run

  validate_transcript "$transcript" "$case_name" "$@"
}

CSV_ROOT="$TMP_ROOT/fixtures/csv-only"
FITS_ROOT="$TMP_ROOT/fixtures/fits-only"
DOCS_ROOT="$TMP_ROOT/fixtures/documents-only"
NOTEBOOK_FILE="$TMP_ROOT/fixtures/notebook-only/analysis.ipynb"
MIXED_ROOT="$TMP_ROOT/fixtures/mixed"

write_fixture_file "$CSV_ROOT/table.csv" "x,y
1,2
"
write_fixture_file "$FITS_ROOT/source.fits" "SIMPLE  =                    T
"
write_fixture_file "$DOCS_ROOT/brief.pdf" "%PDF-1.4
"
write_fixture_file "$DOCS_ROOT/notes.md" "# Notes
"
write_fixture_file "$NOTEBOOK_FILE" '{"cells":[{"cell_type":"markdown","metadata":{},"source":["# Notebook smoke\n"]},{"cell_type":"code","execution_count":null,"metadata":{},"outputs":[],"source":["x = 1\n"]}],"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"}},"nbformat":4,"nbformat_minor":5}
'
write_fixture_file "$MIXED_ROOT/spectra/target_a.fits" "SIMPLE  =                    T
"
write_fixture_file "$MIXED_ROOT/tables/measurements.csv" "time,flux
1,2
"
write_fixture_file "$MIXED_ROOT/docs/readme.pdf" "%PDF-1.4
"

run_no_input_case \
  "readiness" \
  "Check Scientific Workbench readiness without inputs." \
  "datanalysis_env.status" \
  "datanalysis_healthcheck" \
  "env_doctor"

run_case \
  "csv-only" \
  "Analyze this table folder safely." \
  "$CSV_ROOT" \
  "profile_table"

run_case \
  "fits-only" \
  "Analyze this FITS folder safely." \
  "$FITS_ROOT" \
  "inspect_fits"

run_case \
  "documents-only" \
  "Analyze these documents safely." \
  "$DOCS_ROOT" \
  "document_intake_workbench"

run_case \
  "notebook-only" \
  "Inspect this notebook safely." \
  "$NOTEBOOK_FILE" \
  "notebook_workbench.execute-copy"

run_case \
  "mixed" \
  "Analyze this mixed laboratory folder safely." \
  "$MIXED_ROOT" \
  "document_intake_workbench" \
  "cross_domain_data_workbench"

echo "Scientific Workbench smoke matrix passed."

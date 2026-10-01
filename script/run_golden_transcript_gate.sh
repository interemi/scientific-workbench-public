#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientific-workbench-golden.XXXXXX")"
GOLDEN_DIR="$ROOT_DIR/Tests/Fixtures/GoldenTranscripts"
UPDATE_GOLDEN_TRANSCRIPTS="${UPDATE_GOLDEN_TRANSCRIPTS:-0}"
KEEP_GOLDEN_TRANSCRIPTS="${KEEP_GOLDEN_TRANSCRIPTS:-0}"

cleanup() {
  if [[ "$KEEP_GOLDEN_TRANSCRIPTS" != "1" ]]; then
    rm -rf "$TMP_ROOT"
  else
    echo "kept golden transcript files at $TMP_ROOT"
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

sanitize_transcript() {
  local transcript="$1"
  local sanitized="$2"
  /usr/bin/python3 - "$transcript" "$sanitized" "$TMP_ROOT" <<'PY'
import json
import os
import sys

transcript_path, sanitized_path, tmp_root = sys.argv[1:4]
replacements = [
    (os.path.realpath(os.path.normpath(tmp_root)), "<TMP_ROOT>"),
    (os.path.normpath(tmp_root), "<TMP_ROOT>"),
    (os.path.realpath(tmp_root), "<TMP_ROOT>"),
    (tmp_root, "<TMP_ROOT>"),
]
replacements.sort(key=lambda item: len(item[0]), reverse=True)

with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

def normalize(value):
    if isinstance(value, str):
        normalized = value
        for original, replacement in replacements:
            normalized = normalized.replace(original, replacement)
        return normalized
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value

payload = normalize(payload)
payload["generated_at"] = "<timestamp>"
# Setup checklist/recovery reflects local machine readiness (for example
# Ollama/Codex availability). The dedicated first-run smoke validates those
# fields; golden transcripts stay focused on deterministic planning behavior.
payload.pop("setup_checklist", None)
payload.pop("setup_recovery", None)

plan = payload.get("agent_plan")
if isinstance(plan, dict):
    plan["id"] = "<uuid>"
    plan["created_at"] = "<timestamp>"
    for step in plan.get("steps", []):
        if isinstance(step, dict):
            step["id"] = "<uuid>"

for message in payload.get("messages", []):
    if isinstance(message, dict):
        message["created_at"] = "<timestamp>"

for job in payload.get("jobs", []):
    if isinstance(job, dict):
        job["id"] = "<uuid>"
        for key in ("created_at", "started_at", "finished_at"):
            if isinstance(job.get(key), str):
                job[key] = "<timestamp>"

with open(sanitized_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

compare_transcript() {
  local actual="$1"
  local expected="$2"
  local case_name="$3"

  if [[ ! -f "$expected" ]]; then
    echo "$case_name: missing golden transcript at $expected"
    echo "Run UPDATE_GOLDEN_TRANSCRIPTS=1 $ROOT_DIR/script/run_golden_transcript_gate.sh after reviewing the generated behavior."
    return 1
  fi

  /usr/bin/python3 - "$actual" "$expected" "$case_name" <<'PY'
import difflib
import sys

actual_path, expected_path, case_name = sys.argv[1:4]
actual = open(actual_path, "r", encoding="utf-8").read().splitlines(keepends=True)
expected = open(expected_path, "r", encoding="utf-8").read().splitlines(keepends=True)

if actual != expected:
    diff = "".join(difflib.unified_diff(
        expected,
        actual,
        fromfile=f"expected/{case_name}.json",
        tofile=f"actual/{case_name}.json",
        n=3,
    ))
    raise SystemExit(f"{case_name}: golden transcript changed\n{diff}")
PY
}

run_case() {
  local case_name="$1"
  local prompt="$2"
  shift 2

  local output_root="$TMP_ROOT/output/$case_name"
  local transcript="$output_root/transcript.json"
  local sanitized="$output_root/sanitized_transcript.json"
  local expected="$GOLDEN_DIR/$case_name.json"
  mkdir -p "$output_root"

  local command=(
    "$APP_BINARY"
    --agent-mode workflow
    --agent-ai-provider ollama
    --agent-local-planner
    --agent-output-root "$output_root"
    --agent-prompt "$prompt"
    --agent-transcript-json "$transcript"
    --agent-isolated-session
    --agent-exit-after-run
  )

  for input_path in "$@"; do
    command+=(--agent-input "$input_path")
  done

  "${command[@]}"
  sanitize_transcript "$transcript" "$sanitized"

  if [[ "$UPDATE_GOLDEN_TRANSCRIPTS" == "1" ]]; then
    mkdir -p "$GOLDEN_DIR"
    cp "$sanitized" "$expected"
    echo "updated $expected"
  else
    compare_transcript "$sanitized" "$expected" "$case_name"
    echo "ok $case_name"
  fi
}

CSV_FILE="$TMP_ROOT/fixtures/csv/table.csv"
DOC_FILE="$TMP_ROOT/fixtures/documents/notes.md"
MIXED_CSV="$TMP_ROOT/fixtures/mixed/measurements.csv"
MIXED_DOC="$TMP_ROOT/fixtures/mixed/notes.md"
DOCUS_ROOT="$TMP_ROOT/fixtures/DOCUS"

write_fixture_file "$CSV_FILE" "time,flux,error
1,2.4,0.1
2,2.9,0.1
3,3.3,0.2
"
write_fixture_file "$DOC_FILE" "# Practice Notes

This synthetic document describes a short local scientific workflow.
It is intentionally tiny and does not reference DOCUS or UCM.
"
write_fixture_file "$MIXED_CSV" "wavelength,flux
6707.1,0.82
6707.8,0.64
6708.4,0.91
"
write_fixture_file "$MIXED_DOC" "# Mixed Bundle

Synthetic notes paired with a small CSV table for cross-domain routing.
"
write_fixture_file "$DOCUS_ROOT/P1_parte1.pdf" "%PDF-1.4
"
write_fixture_file "$DOCUS_ROOT/P1_parte2.pdf" "%PDF-1.4
"
write_fixture_file "$DOCUS_ROOT/FWHM_vsini_datafit.csv" "fwhm,vsini
1.0,2.0
"
write_fixture_file "$DOCUS_ROOT/fits_p1/nrej1101_foces02_n2.fits" "SIMPLE  =                    T
"
write_fixture_file "$DOCUS_ROOT/fits_p1/npwand_n3.fits" "SIMPLE  =                    T
"
write_fixture_file "$DOCUS_ROOT/iSTARMOD/README.md" "# Synthetic iSTARMOD tree
"

run_case \
  "readiness" \
  "Check Scientific Workbench readiness without inputs."

run_case \
  "csv-profile" \
  "Analyze this CSV table file safely and summarize the useful columns." \
  "$CSV_FILE"

run_case \
  "document-intake" \
  "Analyze this document safely without editing the original." \
  "$DOC_FILE"

run_case \
  "mixed-csv-document" \
  "Analyze this mixed CSV and document bundle safely, then produce a first-pass inventory." \
  "$MIXED_CSV" \
  "$MIXED_DOC"

run_case \
  "legacy-docus-report-plan" \
  "Necesito que analices en profundidad la carpeta DOCUS, hagas la practica UCM y produzcas un PDF final sin tocar originales." \
  "$DOCUS_ROOT"

if [[ "$UPDATE_GOLDEN_TRANSCRIPTS" == "1" ]]; then
  echo "Scientific Workbench golden transcripts updated."
else
  echo "Scientific Workbench golden transcript gate passed."
fi

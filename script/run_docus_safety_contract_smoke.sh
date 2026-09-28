#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientific-workbench-docus-safety.XXXXXX")"
SOURCE="$TMP_ROOT/DOCUS"
OUTPUT="$TMP_ROOT/benchmark"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "DOCUS safety contract smoke failed: $*" >&2
  exit 1
}

mkdir -p "$SOURCE/fits_p1" "$SOURCE/iSTARMOD"
touch \
  "$SOURCE/FWHM_vsini_datafit.csv" \
  "$SOURCE/P1_parte1.pdf" \
  "$SOURCE/P1_parte2.pdf" \
  "$SOURCE/reference.html" \
  "$SOURCE/fits_p1/one.fits" \
  "$SOURCE/fits_p1/two.fits"
ln -s "P1_parte1.pdf" "$SOURCE/internal-link"
ln -s "/usr/bin/python3" "$SOURCE/external-link"

set +e
DOCUS_SOURCE="$SOURCE" \
DOCUS_BENCHMARK_OUTPUT_ROOT="$OUTPUT" \
DOCUS_BENCHMARK_MODE=plan \
DOCUS_BENCHMARK_APP_BINARY=/usr/bin/false \
  "$ROOT_DIR/script/run_docus_benchmark.sh" \
  >"$TMP_ROOT/failed-app.stdout" \
  2>"$TMP_ROOT/failed-app.stderr"
failed_app_status=$?
set -e

[[ "$failed_app_status" -ne 0 ]] || fail "the failing app override unexpectedly passed"
[[ -f "$OUTPUT/original_fingerprint_before.json" ]] || fail "missing pre-run fingerprint"
[[ -f "$OUTPUT/original_fingerprint_after.json" ]] || fail "EXIT guard did not create the post-run fingerprint"
cmp -s "$OUTPUT/original_fingerprint_before.json" "$OUTPUT/original_fingerprint_after.json" \
  || fail "unchanged fixture fingerprints differ"
[[ -f "$OUTPUT/original_metadata_before.mtree" ]] || fail "missing mtree metadata baseline"
[[ -f "$OUTPUT/original_metadata_diff.txt" ]] || fail "missing mtree verification output"
[[ ! -s "$OUTPUT/original_metadata_diff.txt" ]] || fail "unchanged fixture metadata differs"
[[ -L "$SOURCE/internal-link" ]] || fail "internal source symlink changed"
[[ -L "$SOURCE/external-link" ]] || fail "external source symlink changed"
[[ -L "$OUTPUT/work/DOCUS/internal-link" ]] || fail "internal safe-copy symlink was not preserved"
[[ ! -L "$OUTPUT/work/DOCUS/external-link" ]] || fail "external safe-copy symlink was not neutralized"

/usr/bin/python3 - "$OUTPUT/safe_copy_symlinks.json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    records = json.load(handle)
by_path = {record["path"]: record for record in records}
if by_path.get("internal-link", {}).get("action") != "preserved":
    raise SystemExit("internal symlink action was not recorded as preserved")
if by_path.get("external-link", {}).get("action") != "removed_from_safe_copy":
    raise SystemExit("external symlink action was not recorded as removed")
PY

/usr/bin/python3 - "$ROOT_DIR/script/run_docus_benchmark.sh" "$SOURCE" "$OUTPUT" <<'PY'
import ast
import copy
import json
from pathlib import Path
import shlex
import sys

script, source, output = sys.argv[1:]
section = Path(script).read_text().split("validate_transcript_and_write_report() {", 1)[1]
validator = section.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
tree = ast.parse(validator)
expected = next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "expected_steps"
                        for target in node.targets))
safe_copy = Path(output) / "work/DOCUS"
run_root = Path(output) / "validation-runs"
run_root.mkdir()
documents = [safe_copy / name for name in ("P1_parte1.pdf", "P1_parte2.pdf", "reference.html")]
steps = [{"capability_id": capability, "raw_arguments": ""} for capability in expected]
steps[expected.index("document_intake_workbench")]["raw_arguments"] = shlex.join(map(str, documents))
jobs = []
for index, capability in enumerate(expected):
    run_dir = run_root / str(index)
    run_dir.mkdir()
    jobs.append({"capability_id": capability, "status": "succeeded", "exit_code": 0,
                 "run_directory": str(run_dir), "artifacts": []})
    if capability == "document_intake_workbench":
        (run_dir / "summary.json").write_text(json.dumps({
            "discovery": {"input_count": 3, "found_count": 3, "missing_inputs": [], "limit_reached": False},
            "files": [{"name": document.name} for document in documents],
        }))
jobs[-1]["artifacts"] = [{"path": str(run_root / "synthetic.pdf")}]
payload = {"agent_plan": {"source": "local", "steps": steps}, "jobs": jobs}
transcript = Path(output) / "validation-transcript.json"
sys.argv = [script, str(transcript), source, str(safe_copy), str(run_root),
            str(Path(output) / "validation-report.md"), "full", str(run_root),
            str(Path(output) / "safe_copy_symlinks.json")]

def validate(candidate, rejection_expected):
    transcript.write_text(json.dumps(candidate))
    try:
        exec(compile(validator, script, "exec"), {})
    except SystemExit as exc:
        if not rejection_expected or "requires every planned job exactly once" not in str(exc):
            raise
    else:
        if rejection_expected:
            raise SystemExit("DOCUS full validator accepted incomplete or failed execution")

validate(payload, False)
for mutation in ("missing", "duplicate", "failed", "nonzero_exit"):
    candidate = copy.deepcopy(payload)
    if mutation == "missing":
        candidate["jobs"].pop(0)
    elif mutation == "duplicate":
        candidate["jobs"].append(copy.deepcopy(candidate["jobs"][0]))
    elif mutation == "failed":
        candidate["jobs"][0]["status"] = "failed"
    else:
        candidate["jobs"][0]["exit_code"] = 1
    validate(candidate, True)
PY

chmod 600 "$SOURCE/P1_parte1.pdf"
set +e
LC_ALL=C /usr/sbin/mtree -P \
  -p "$SOURCE" \
  -f "$OUTPUT/original_metadata_before.mtree" \
  >"$TMP_ROOT/metadata-mutation.diff" 2>&1
metadata_mutation_status=$?
set -e
[[ "$metadata_mutation_status" -ne 0 ]] || fail "mtree guard missed a permission mutation"

overlap="$SOURCE/benchmark-output-must-not-exist"
set +e
DOCUS_SOURCE="$SOURCE" \
DOCUS_BENCHMARK_OUTPUT_ROOT="$overlap" \
DOCUS_BENCHMARK_MODE=plan \
DOCUS_BENCHMARK_APP_BINARY=/usr/bin/false \
  "$ROOT_DIR/script/run_docus_benchmark.sh" \
  >"$TMP_ROOT/overlap.stdout" \
  2>"$TMP_ROOT/overlap.stderr"
overlap_status=$?
set -e

[[ "$overlap_status" -ne 0 ]] || fail "overlapping output root unexpectedly passed"
[[ ! -e "$overlap" ]] || fail "overlap guard wrote inside the source"
grep -q "overlaps the original source" "$TMP_ROOT/overlap.stderr" \
  || fail "overlap rejection did not explain the boundary"

echo "Scientific Workbench DOCUS safety contract smoke passed."

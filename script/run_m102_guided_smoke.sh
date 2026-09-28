#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientific-workbench-m102-guided.XXXXXX")"
MOTHER_ROOT="$ROOT_DIR/skills/scientific-data-analysis"
ASTRO_ROOT="$ROOT_DIR/skills/scientific-data-astro"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fingerprint() {
  /usr/bin/shasum -a 256 "$@" | /usr/bin/sort
}

run_tool() {
  local skill_root="$1"
  shift
  (
    cd "$skill_root"
    /usr/bin/python3 scripts/datanalysis_env.py run-tool "$@"
  )
}

mkdir -p "$TMP_ROOT/fixtures/catalogs" "$TMP_ROOT/output/crossmatch"
LEFT="$TMP_ROOT/fixtures/catalogs/left.csv"
RIGHT="$TMP_ROOT/fixtures/catalogs/right.csv"
cat >"$LEFT" <<'EOF'
source_id,ra_deg,dec_deg
L1,120.000000,-30.000000
L2,121.000000,-31.000000
EOF
cat >"$RIGHT" <<'EOF'
source_id,ra_deg,dec_deg
R1,120.000100,-30.000100
R2,122.000000,-32.000000
EOF

CATALOG_BEFORE="$(fingerprint "$LEFT" "$RIGHT")"
CROSSMATCH_OUTPUT="$TMP_ROOT/output/crossmatch/catalog_crossmatch.ecsv"
CROSSMATCH_SUMMARY="$TMP_ROOT/output/crossmatch/summary.json"
CROSSMATCH_MANIFEST="$TMP_ROOT/output/crossmatch/manifest.json"
run_tool "$MOTHER_ROOT" catalog_workbench crossmatch-sky \
  "$LEFT" "$RIGHT" "$CROSSMATCH_OUTPUT" \
  --left-ra ra_deg --left-dec dec_deg \
  --right-ra ra_deg --right-dec dec_deg \
  --radius-arcsec 1.0 \
  --summary-json "$CROSSMATCH_SUMMARY" \
  --manifest-json "$CROSSMATCH_MANIFEST" >/dev/null
CATALOG_AFTER="$(fingerprint "$LEFT" "$RIGHT")"
[[ "$CATALOG_BEFORE" == "$CATALOG_AFTER" ]] || {
  echo "M102 guided smoke failed: catalog inputs changed" >&2
  exit 1
}

/usr/bin/python3 - "$CROSSMATCH_SUMMARY" "$CROSSMATCH_MANIFEST" "$CROSSMATCH_OUTPUT" <<'PY'
import json
import pathlib
import sys

summary_path, manifest_path, output_path = map(pathlib.Path, sys.argv[1:4])
for path in (summary_path, manifest_path, output_path):
    if not path.is_file():
        raise SystemExit(f"M102 guided smoke failed: missing crossmatch output {path}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
if summary.get("tool") != "catalog_workbench.crossmatch-sky":
    raise SystemExit("M102 guided smoke failed: wrong crossmatch tool envelope")
if str(summary.get("status", "")).lower() not in {"ok", "warning", "pass"}:
    raise SystemExit(f"M102 guided smoke failed: crossmatch status {summary.get('status')!r}")
results = summary.get("results") or {}
if results.get("matched_rows") != 1:
    raise SystemExit(f"M102 guided smoke failed: expected one catalog match, got {results.get('matched_rows')!r}")
PY

mkdir -p "$TMP_ROOT/fixtures/legacy" "$TMP_ROOT/output/legacy"
SOURCE_PROJECT="$TMP_ROOT/fixtures/legacy/legacy_report"
SCAFFOLD_SUMMARY="$TMP_ROOT/fixtures/legacy/scaffold-summary.json"
SCAFFOLD_MANIFEST="$TMP_ROOT/fixtures/legacy/scaffold-manifest.json"
run_tool "$ASTRO_ROOT" legacy_spectroscopy_report_builder scaffold \
  "$SOURCE_PROJECT" \
  --title "Synthetic M102 report" \
  --author "Scientific Workbench" \
  --summary-json "$SCAFFOLD_SUMMARY" \
  --manifest-json "$SCAFFOLD_MANIFEST" >/dev/null

ENVCHECK="$TMP_ROOT/fixtures/legacy/envcheck.json"
cat >"$ENVCHECK" <<'EOF'
{
  "tool": "legacy_spectroscopy_envcheck",
  "status": "warning",
  "app_status": "warning",
  "results": {
    "detected_practice_assets": {
      "fits_count": 0,
      "calibration_csv": null,
      "istarmod_root": null
    }
  }
}
EOF

SOURCE_PROJECT_FILES=()
while IFS= read -r path; do
  SOURCE_PROJECT_FILES+=("$path")
done < <(find "$SOURCE_PROJECT" -type f -print | /usr/bin/sort)
LEGACY_BEFORE="$(fingerprint "$ENVCHECK" "${SOURCE_PROJECT_FILES[@]}")"
STAGED_PROJECT="$TMP_ROOT/output/legacy/legacy_report"
cp -R "$SOURCE_PROJECT" "$STAGED_PROJECT"
LEGACY_SUMMARY="$TMP_ROOT/output/legacy/summary.json"
LEGACY_MANIFEST="$TMP_ROOT/output/legacy/manifest.json"
run_tool "$ASTRO_ROOT" legacy_spectroscopy_report_builder populate \
  "$STAGED_PROJECT" \
  --envcheck "$ENVCHECK" \
  --summary-json "$LEGACY_SUMMARY" \
  --manifest-json "$LEGACY_MANIFEST" >/dev/null
LEGACY_AFTER="$(fingerprint "$ENVCHECK" "${SOURCE_PROJECT_FILES[@]}")"
[[ "$LEGACY_BEFORE" == "$LEGACY_AFTER" ]] || {
  echo "M102 guided smoke failed: legacy report inputs changed" >&2
  exit 1
}

/usr/bin/python3 - "$LEGACY_SUMMARY" "$LEGACY_MANIFEST" "$STAGED_PROJECT" <<'PY'
import json
import pathlib
import sys

summary_path, manifest_path, project_path = map(pathlib.Path, sys.argv[1:4])
for path in (summary_path, manifest_path, project_path / "main.tex"):
    if not path.exists():
        raise SystemExit(f"M102 guided smoke failed: missing legacy report output {path}")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
if summary.get("tool") != "legacy_spectroscopy_report_builder.populate":
    raise SystemExit("M102 guided smoke failed: wrong legacy report tool envelope")
if str(summary.get("status", "")).lower() not in {"ok", "warning", "pass"}:
    raise SystemExit(f"M102 guided smoke failed: legacy report status {summary.get('status')!r}")
section = project_path / "sections" / "01_objetivo_materiales.tex"
section_text = section.read_text(encoding="utf-8") if section.is_file() else ""
if "Material detectado" not in section_text or "0 FITS" not in section_text:
    raise SystemExit("M102 guided smoke failed: legacy material section was not rendered")
PY

echo "Scientific Workbench M102 guided workflow smoke passed: crossmatch and isolated legacy report inputs unchanged."

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/deploy/smoke-test-output}"
PROFILE="${PROFILE:-core}"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  SELECTED_PYTHON="$PYTHON_BIN"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  SELECTED_PYTHON="$ROOT_DIR/.venv/bin/python"
else
  SELECTED_PYTHON="python3"
fi

cd "$ROOT_DIR"
"$SELECTED_PYTHON" scripts/portable_smoke_test.py \
  --output-dir "$OUTPUT_DIR" \
  --examples-dir "$ROOT_DIR/examples" \
  --profile "$PROFILE" \
  --summary-json "$OUTPUT_DIR/summary.json" \
  --manifest-json "$OUTPUT_DIR/manifest.json"
echo "Smoke test complete. See: $OUTPUT_DIR"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/deploy/teareduce-smoke-output}"
SEARCH_ROOT="${SEARCH_ROOT:-}"

cd "$ROOT_DIR"

CMD=(python3 scripts/datanalysis_env.py run-tool teareduce_smoke_test
  --output-dir "$OUTPUT_DIR"
  --summary-json "$OUTPUT_DIR/summary.json"
  --manifest-json "$OUTPUT_DIR/manifest.json")

if [[ -n "$SEARCH_ROOT" ]]; then
  CMD+=(--search-root "$SEARCH_ROOT")
fi

"${CMD[@]}"
echo "TEAREDUCE smoke test complete. See: $OUTPUT_DIR"

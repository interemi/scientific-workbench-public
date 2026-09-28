#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-conda}"

cd "$ROOT_DIR"
if ! command -v "$CONDA_BIN" >/dev/null 2>&1; then
  echo "Could not find conda. Set CONDA_BIN or install Conda/Mamba first." >&2
  exit 1
fi

if "$CONDA_BIN" env list | grep -qE '^datanalysis[[:space:]]'; then
  "$CONDA_BIN" env update -f environment.yml --prune
else
  "$CONDA_BIN" env create -f environment.yml
fi
"$CONDA_BIN" run -n datanalysis python scripts/env_doctor.py --summary-json "$ROOT_DIR/deploy/env_doctor.conda.json"
echo "Conda installation complete. Activate with: conda activate datanalysis"

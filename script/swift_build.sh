#!/usr/bin/env bash
set -euo pipefail

options=()
if [[ -n "${SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM:-}" ]]; then
  options+=(--build-system "$SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM")
fi
if [[ -n "${SCIENTIFIC_WORKBENCH_SWIFT_SCRATCH_PATH:-}" ]]; then
  options+=(--scratch-path "$SCIENTIFIC_WORKBENCH_SWIFT_SCRATCH_PATH")
fi

exec swift build "${options[@]}" "$@"

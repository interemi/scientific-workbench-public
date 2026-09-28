#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

cleanup_app() {
  /usr/bin/osascript -e 'tell application "Scientific Workbench" to quit' >/dev/null 2>&1 || true
  pkill -x "Scientific Workbench" >/dev/null 2>&1 || true
  for _ in {1..40}; do
    if ! pgrep -x "Scientific Workbench" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  pkill -9 -x "Scientific Workbench" >/dev/null 2>&1 || true
}

run_step() {
  local name="$1"
  shift
  local started_at
  started_at="$(date +%s)"
  printf "\n==> %s\n" "$name"
  cleanup_app
  "$@"
  cleanup_app
  local finished_at
  finished_at="$(date +%s)"
  printf "<== %s passed in %ss\n" "$name" "$((finished_at - started_at))"
}

trap cleanup_app EXIT

run_step "Repository hygiene checks" "$ROOT_DIR/script/check_repo_hygiene.sh"
run_step "Swift unit/integration tests" "$ROOT_DIR/script/run_swift_tests.sh"
run_step "Process-group cancellation smoke" "$ROOT_DIR/script/run_process_group_smoke.sh"
run_step "Headless planner smoke matrix" "$ROOT_DIR/script/run_smoke_matrix.sh"
run_step "Golden transcript regression gate" "$ROOT_DIR/script/run_golden_transcript_gate.sh"
run_step "Headless capability E2E matrix" "$ROOT_DIR/script/run_e2e_capability_matrix.sh"
run_step "M102 reviewed guided workflow smoke" "$ROOT_DIR/script/run_m102_guided_smoke.sh"
run_step "Mixed research benchmark" "$ROOT_DIR/script/run_mixed_research_benchmark.sh"
run_step "Secret redaction gate" "$ROOT_DIR/script/run_secret_redaction_gate.sh"
run_step "Settings surface checks" "$ROOT_DIR/script/check_settings_surface.sh"
run_step "Release readiness static checks" "$ROOT_DIR/script/check_release_readiness.sh"
run_step "Fresh first-run packaged smoke" "$ROOT_DIR/script/run_first_run_smoke.sh"

DOCUS_BENCHMARK_RAN=0
if [[ "${RUN_DOCUS_BENCHMARK:-0}" == "1" ]]; then
  DOCUS_BENCHMARK_RAN=1
  run_step "DOCUS benchmark (${DOCUS_BENCHMARK_MODE:-plan})" "$ROOT_DIR/script/run_docus_benchmark.sh"
else
  printf "\n==> DOCUS benchmark skipped; set RUN_DOCUS_BENCHMARK=1 to run the safe copied-input benchmark\n"
fi

run_step "Packaged app bundle verification" "$ROOT_DIR/script/build_and_run.sh" --verify
run_step "Finder/Dock packaged smoke" "$ROOT_DIR/script/run_finder_dock_smoke.sh"
run_step "Packaged real-run smoke" "$ROOT_DIR/script/run_packaged_real_run_smoke.sh"

if [[ "${SKIP_UI_SMOKE:-0}" == "1" ]]; then
  printf "\n==> Packaged UI smoke skipped because SKIP_UI_SMOKE=1\n"
else
  run_step "Packaged UI smoke" "$ROOT_DIR/script/run_ui_smoke.sh"
fi

if [[ "$DOCUS_BENCHMARK_RAN" == "1" ]]; then
  printf "\nScientific Workbench quality gate passed with DOCUS benchmark (%s).\n" "${DOCUS_BENCHMARK_MODE:-plan}"
else
  printf "\nScientific Workbench quality gate passed without DOCUS benchmark; run with RUN_DOCUS_BENCHMARK=1 for major-milestone validation.\n"
fi

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  echo "release readiness failed: $*" >&2
  exit 1
}

[[ -x "$ROOT_DIR/script/package_release.sh" ]] || fail "package_release.sh is not executable"
[[ -x "$ROOT_DIR/script/verify_release_manifest.sh" ]] || fail "verify_release_manifest.sh is not executable"
[[ -x "$ROOT_DIR/script/verify_release_archive.sh" ]] || fail "verify_release_archive.sh is not executable"
[[ -x "$ROOT_DIR/script/run_release_manifest_contract_smoke.sh" ]] || fail "run_release_manifest_contract_smoke.sh is not executable"
[[ -x "$ROOT_DIR/script/run_release_package_guard_smoke.sh" ]] || fail "release package guard smoke is not executable"
[[ -x "$ROOT_DIR/script/resolve_skill_registry_evidence.py" ]] || fail "registry evidence resolver is not executable"
[[ -x "$ROOT_DIR/script/run_skill_registry_evidence_smoke.sh" ]] || fail "registry evidence smoke is not executable"
[[ -x "$ROOT_DIR/script/run_first_run_smoke.sh" ]] || fail "run_first_run_smoke.sh is not executable"
[[ -x "$ROOT_DIR/script/run_docus_safety_contract_smoke.sh" ]] || fail "DOCUS safety contract smoke is not executable"
[[ -x "$ROOT_DIR/script/run_finder_dock_smoke.sh" ]] || fail "run_finder_dock_smoke.sh is not executable"
[[ -x "$ROOT_DIR/script/check_settings_surface.sh" ]] || fail "check_settings_surface.sh is not executable"
[[ -x "$ROOT_DIR/script/run_swift_tests.sh" ]] || fail "run_swift_tests.sh is not executable"
[[ -x "$ROOT_DIR/script/run_packaged_real_run_smoke.sh" ]] || fail "run_packaged_real_run_smoke.sh is not executable"
[[ -x "$ROOT_DIR/script/run_m102_guided_smoke.sh" ]] || fail "M102 guided workflow smoke is not executable"
[[ -x "$ROOT_DIR/script/check_repo_hygiene.sh" ]] || fail "check_repo_hygiene.sh is not executable"
[[ -x "$ROOT_DIR/script/check_git_publication_readiness.sh" ]] || fail "check_git_publication_readiness.sh is not executable"
[[ -f "$ROOT_DIR/script/audit_public_documentation.py" ]] || fail "missing public documentation audit"
[[ -f "$ROOT_DIR/script/extract_pdf_text.swift" ]] || fail "missing PDF text extractor"
[[ -f "$ROOT_DIR/script/check_workflow_requirements.py" ]] || fail "missing workflow requirements check"
[[ -f "$ROOT_DIR/docs/WORKFLOW_REQUIREMENTS.md" ]] || fail "missing workflow requirements document"
[[ -f "$ROOT_DIR/docs/TROUBLESHOOTING.md" ]] || fail "missing troubleshooting document"
[[ -f "$ROOT_DIR/docs/SOURCE_DISTRIBUTION_BOUNDARY.md" ]] || fail "missing source distribution boundary"
[[ -f "$ROOT_DIR/docs/PUBLIC_SOURCE_HANDOFF.md" ]] || fail "missing public source handoff"
[[ -f "$ROOT_DIR/docs/LICENSE_DECISION.md" ]] || fail "missing license decision record"
[[ -f "$ROOT_DIR/docs/OWNERSHIP_CONFIRMATION.md" ]] || fail "missing ownership confirmation record"
[[ -f "$ROOT_DIR/docs/DOCUMENTATION_PUBLICATION_PLAN.md" ]] || fail "missing documentation publication plan"
[[ -f "$ROOT_DIR/distribution/public-source-exclusions.txt" ]] || fail "missing public source exclusion policy"
[[ -f "$ROOT_DIR/script/export_public_source.py" ]] || fail "missing public source exporter"
[[ -f "$ROOT_DIR/RELEASE_CHECKLIST.md" ]] || fail "missing RELEASE_CHECKLIST.md"
[[ -f "$ROOT_DIR/RELEASE_NOTES.md" ]] || fail "missing RELEASE_NOTES.md"
[[ -f "$ROOT_DIR/POST_100_BACKLOG.md" ]] || fail "missing POST_100_BACKLOG.md"
[[ -f "$ROOT_DIR/DECISIONS/0003-versioning-and-release-evidence.md" ]] || fail "missing release evidence ADR"
[[ -f "$ROOT_DIR/Guides/Scientific_Workbench_User_Guide.md" ]] || fail "missing user guide"

grep -q -- "--build" "$ROOT_DIR/script/build_and_run.sh" || fail "build_and_run.sh lacks build-only mode"
grep -q "notarytool" "$ROOT_DIR/script/package_release.sh" || fail "package script lacks notarytool path"
grep -q "verify_release_manifest.sh" "$ROOT_DIR/script/package_release.sh" || fail "package script does not verify release manifest"
grep -q "verify_release_archive.sh" "$ROOT_DIR/script/package_release.sh" || fail "package script does not verify release archive"
grep -q "MANIFEST_SCHEMA_VERSION=2" "$ROOT_DIR/script/package_release.sh" || fail "package script lacks schema-2 release evidence"
grep -q '_manifest.json' "$ROOT_DIR/script/package_release.sh" || fail "package script must preserve one manifest per build"
grep -q 'status --porcelain' "$ROOT_DIR/script/package_release.sh" || fail "package script must require a clean Git worktree"
grep -q 'assert_source_unchanged' "$ROOT_DIR/script/package_release.sh" || fail "package script must re-check source integrity after validation"
grep -q 'REGISTRY_EVIDENCE_BEFORE' "$ROOT_DIR/script/package_release.sh" || fail "package script must detect registry changes during packaging"
grep -q 'skill_registry_stub_sha256' "$ROOT_DIR/script/package_release.sh" || fail "package script must record mother registry evidence"
grep -q 'skill_registry_relative_path' "$ROOT_DIR/script/package_release.sh" || fail "package script must record the canonical registry path"
grep -q "Tests/ScientificWorkbenchTests" "$ROOT_DIR/script/run_swift_tests.sh" || fail "Swift test runner must scan the full test target"
grep -q "Developer ID" "$ROOT_DIR/RELEASE_CHECKLIST.md" || fail "release checklist lacks Developer ID guidance"
grep -q "notarytool" "$ROOT_DIR/RELEASE_CHECKLIST.md" || fail "release checklist lacks notarytool guidance"
grep -qi "quality gate" "$ROOT_DIR/RELEASE_NOTES.md" || fail "release notes lack quality-gate note"
grep -q "SkillRootCatalog" "$ROOT_DIR/Sources/ScientificWorkbench/Services/SkillRootCatalog.swift" || fail "missing multi-root skill catalog"
grep -q "resolvedSkillRoot" "$ROOT_DIR/Sources/ScientificWorkbench/Services/CapabilityCommandBuilder.swift" || fail "command builder must use capability owning roots"
grep -q 'TextField("Mother skill root"' "$ROOT_DIR/Sources/ScientificWorkbench/Views/SettingsView.swift" || fail "settings must label the configured root as the mother skill root"
grep -qi "smoke/regression coverage" "$ROOT_DIR/ARCHITECTURE.md" || fail "architecture must describe coverage as smoke/regression, not exhaustive"

if grep -R "DefaultPaths\\.skillRoot" "$ROOT_DIR/Sources" "$ROOT_DIR/Tests" >/dev/null; then
  fail "stale DefaultPaths.skillRoot single-root reference found"
fi

"$ROOT_DIR/script/check_repo_hygiene.sh" >/dev/null || fail "repository hygiene check failed"
"$ROOT_DIR/script/check_git_publication_readiness.sh" >/dev/null || fail "Git publication readiness check failed"
python3 "$ROOT_DIR/script/audit_public_documentation.py" >/dev/null || fail "public documentation inventory failed"
python3 "$ROOT_DIR/script/check_workflow_requirements.py" >/dev/null || fail "workflow requirements drifted from the canonical registry"
"$ROOT_DIR/script/run_skill_registry_evidence_smoke.sh" >/dev/null || fail "skill registry evidence smoke failed"
"$ROOT_DIR/script/run_release_manifest_contract_smoke.sh" >/dev/null || fail "release manifest contract smoke failed"
"$ROOT_DIR/script/run_release_package_guard_smoke.sh" >/dev/null || fail "release package guard smoke failed"
"$ROOT_DIR/script/run_docus_safety_contract_smoke.sh" >/dev/null || fail "DOCUS safety contract smoke failed"

if grep -R "altool" RELEASE_CHECKLIST.md RELEASE_NOTES.md script/package_release.sh >/dev/null; then
  fail "legacy altool workflow should not be used"
fi

echo "Scientific Workbench release readiness checks passed."

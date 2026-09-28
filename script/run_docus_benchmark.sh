#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCUS_SOURCE="${DOCUS_SOURCE:-$HOME/Desktop/DOCUS}"
DOCUS_BENCHMARK_MODE="${DOCUS_BENCHMARK_MODE:-plan}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
# IRAF/CL tools used by the DOCUS full benchmark are path-sensitive and can
# break on whitespace. Keep the default benchmark root ASCII-safe/no-space.
OUTPUT_ROOT="${DOCUS_BENCHMARK_OUTPUT_ROOT:-$HOME/Documents/ScientificWorkbenchRuns/DOCUSBenchmarks/$TIMESTAMP}"
WORK_ROOT="$OUTPUT_ROOT/work"
DOCUS_COPY="$WORK_ROOT/DOCUS"
RUN_OUTPUT="$OUTPUT_ROOT/run_output"
TRANSCRIPT="$RUN_OUTPUT/transcript.json"
LEGACY_WORKSPACE_ROOT="$HOME/Documents/ScientificWorkbenchRuns/LegacyWorkspaces"
FINGERPRINT_BEFORE="$OUTPUT_ROOT/original_fingerprint_before.json"
FINGERPRINT_AFTER="$OUTPUT_ROOT/original_fingerprint_after.json"
MTREE_BEFORE="$OUTPUT_ROOT/original_metadata_before.mtree"
MTREE_DIFF="$OUTPUT_ROOT/original_metadata_diff.txt"
SANITIZED_SYMLINKS="$OUTPUT_ROOT/safe_copy_symlinks.json"
REPORT="$OUTPUT_ROOT/benchmark_report.md"
PROMPT="${DOCUS_BENCHMARK_PROMPT:-Necesito que analices en profundidad la carpeta DOCUS, hagas la practica UCM y produzcas un PDF final sin tocar originales.}"

case "$DOCUS_BENCHMARK_MODE" in
  plan|progress|full) ;;
  *)
    echo "DOCUS_BENCHMARK_MODE must be 'plan', 'progress', or 'full'." >&2
    exit 2
    ;;
esac

if [[ "$DOCUS_BENCHMARK_MODE" != "plan" ]]; then
  /usr/bin/python3 - "$OUTPUT_ROOT" <<'PY'
import sys

path = sys.argv[1]
if any(character.isspace() or ord(character) > 127 for character in path):
    raise SystemExit(
        "DOCUS full/progress benchmark output root must be ASCII and contain no whitespace "
        f"because legacy IRAF/CL tools cannot safely run from this path: {path}"
    )
PY
fi

/usr/bin/python3 - "$DOCUS_SOURCE" "$OUTPUT_ROOT" "$WORK_ROOT" "$DOCUS_COPY" "$RUN_OUTPUT" "$LEGACY_WORKSPACE_ROOT" <<'PY'
import os
import sys

source, output_root, work_root, copy_root, run_output, legacy_root = sys.argv[1:7]
if not os.path.isdir(source):
    raise SystemExit(f"DOCUS source is not a directory: {source}")
if os.path.lexists(output_root):
    raise SystemExit(
        "DOCUS benchmark output root must be a new path; refusing to reuse or follow it: "
        f"{output_root}"
    )

source_real = os.path.realpath(os.path.abspath(source))
for label, path in {
    "output root": output_root,
    "work root": work_root,
    "safe copy": copy_root,
    "run output": run_output,
    "legacy workspace root": legacy_root,
}.items():
    candidate_real = os.path.realpath(os.path.abspath(path))
    try:
        common = os.path.commonpath([source_real, candidate_real])
    except ValueError:
        continue
    if common in {source_real, candidate_real}:
        raise SystemExit(
            f"DOCUS benchmark {label} overlaps the original source; refusing before any write: "
            f"source={source_real} candidate={candidate_real}"
        )
PY

cd "$ROOT_DIR"
if [[ -n "${DOCUS_BENCHMARK_APP_BINARY:-}" ]]; then
  APP_BINARY="$DOCUS_BENCHMARK_APP_BINARY"
  [[ -x "$APP_BINARY" ]] || {
    echo "DOCUS_BENCHMARK_APP_BINARY is not executable: $APP_BINARY" >&2
    exit 2
  }
else
  swift build >/dev/null
  APP_BINARY="$(swift build --show-bin-path)/ScientificWorkbench"
fi

mkdir -p "$OUTPUT_ROOT" "$WORK_ROOT" "$RUN_OUTPUT"

fingerprint_tree() {
  local output_file="$1"
  local input_path="$2"
  /usr/bin/python3 - "$output_file" "$input_path" <<'PY'
import hashlib
import json
import os
import stat
import sys

output_file, input_path = sys.argv[1:3]
input_path = os.path.abspath(input_path)
records = []

def digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def xattr_digests(path):
    try:
        names = sorted(os.listxattr(path, follow_symlinks=False))
    except (AttributeError, OSError, TypeError):
        return {}
    digests = {}
    for name in names:
        try:
            value = os.getxattr(path, name, follow_symlinks=False)
        except (OSError, TypeError):
            continue
        digests[name] = hashlib.sha256(value).hexdigest()
    return digests

def add_record(path):
    relative_path = os.path.relpath(os.path.abspath(path), input_path)
    stat_result = os.lstat(path)
    record = {
        "path": relative_path,
        "mode": stat.S_IMODE(stat_result.st_mode),
        "uid": stat_result.st_uid,
        "gid": stat_result.st_gid,
        "nlink": stat_result.st_nlink,
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "ctime_ns": stat_result.st_ctime_ns,
        "birthtime_ns": int(getattr(stat_result, "st_birthtime", 0) * 1_000_000_000),
        "flags": getattr(stat_result, "st_flags", 0),
        "xattrs": xattr_digests(path),
    }
    if os.path.islink(path):
        resolved_target = os.path.realpath(path)
        try:
            target_scope = "internal" if os.path.commonpath([input_path, resolved_target]) == input_path else "external"
        except ValueError:
            target_scope = "external"
        record.update(
            kind="symlink",
            target=os.readlink(path),
            resolved_target=resolved_target,
            target_scope=target_scope,
        )
    elif os.path.isdir(path):
        record.update(kind="directory")
    elif os.path.isfile(path):
        record.update(kind="file", sha256=digest_file(path))
    else:
        record.update(kind="other")
    records.append(record)

if not os.path.isdir(input_path):
    raise SystemExit(f"DOCUS source is not a directory: {input_path}")

add_record(input_path)
for directory, dirnames, filenames in os.walk(input_path, followlinks=False):
    dirnames[:] = sorted(dirnames)
    for dirname in dirnames:
        add_record(os.path.join(directory, dirname))
    for filename in sorted(filenames):
        add_record(os.path.join(directory, filename))

records.sort(key=lambda item: (item["path"], item["kind"]))
with open(output_file, "w", encoding="utf-8") as handle:
    json.dump(records, handle, indent=2, sort_keys=True)
PY
}

validate_required_docus_shape() {
  /usr/bin/python3 - "$DOCUS_SOURCE" <<'PY'
import os
import sys

root = sys.argv[1]
required = [
    "fits_p1",
    "iSTARMOD",
    "FWHM_vsini_datafit.csv",
    "P1_parte1.pdf",
    "P1_parte2.pdf",
]
missing = [item for item in required if not os.path.exists(os.path.join(root, item))]
if missing:
    raise SystemExit(f"DOCUS benchmark missing required items in {root}: {missing}")

fits_root = os.path.join(root, "fits_p1")
fits_files = [name for name in os.listdir(fits_root) if name.lower().endswith((".fit", ".fits", ".fts"))]
if len(fits_files) < 2:
    raise SystemExit(f"DOCUS benchmark expected multiple FITS files under {fits_root}, found {len(fits_files)}")
PY
}

validate_original_unchanged() {
  /usr/bin/python3 - "$FINGERPRINT_BEFORE" "$FINGERPRINT_AFTER" <<'PY'
import json
import sys

before_path, after_path = sys.argv[1:3]
with open(before_path, "r", encoding="utf-8") as handle:
    before = json.load(handle)
with open(after_path, "r", encoding="utf-8") as handle:
    after = json.load(handle)

if before != after:
    before_map = {(item.get("path"), item.get("kind")): item for item in before}
    after_map = {(item.get("path"), item.get("kind")): item for item in after}
    removed = sorted(set(before_map) - set(after_map))
    added = sorted(set(after_map) - set(before_map))
    changed = sorted(
        key for key in set(before_map).intersection(after_map)
        if before_map[key] != after_map[key]
    )
    raise SystemExit(
        "DOCUS original changed during benchmark; "
        f"added={added[:8]} removed={removed[:8]} changed={changed[:8]}"
    )
PY
}

capture_original_metadata() {
  LC_ALL=C /usr/sbin/mtree -c -n -P \
    -p "$DOCUS_SOURCE" \
    -k 'uid,gid,mode,flags,nlink,size,link,time,btime,ctime,xattrsdigest,acldigest,nxattr,dataless' \
    >"$MTREE_BEFORE"
}

validate_original_metadata() {
  : >"$MTREE_DIFF"
  if ! LC_ALL=C /usr/sbin/mtree -P \
    -p "$DOCUS_SOURCE" \
    -f "$MTREE_BEFORE" \
    >"$MTREE_DIFF" 2>&1; then
    echo "DOCUS original metadata/ACL/xattr guard failed:" >&2
    sed -n '1,80p' "$MTREE_DIFF" >&2
    return 1
  fi
}

sanitize_safe_copy_symlinks() {
  /usr/bin/python3 - "$DOCUS_COPY" "$DOCUS_SOURCE" "$SANITIZED_SYMLINKS" <<'PY'
import json
import os
import sys

copy_root, source_root, manifest_path = sys.argv[1:4]
copy_real = os.path.realpath(copy_root)
source_real = os.path.realpath(source_root)
records = []

def within(path, root):
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False

for directory, dirnames, filenames in os.walk(copy_root, topdown=True, followlinks=False):
    for name in sorted(set(dirnames + filenames)):
        path = os.path.join(directory, name)
        if not os.path.islink(path):
            continue
        relative_path = os.path.relpath(path, copy_root)
        target = os.readlink(path)
        resolved_target = os.path.realpath(path)
        is_internal = within(resolved_target, copy_real)
        points_to_original = within(resolved_target, source_real)
        action = "preserved"
        if not is_internal:
            os.unlink(path)
            action = "removed_from_safe_copy"
            if name in dirnames:
                dirnames.remove(name)
        records.append({
            "path": relative_path,
            "target": target,
            "resolved_target": resolved_target,
            "scope": "internal" if is_internal else ("original_source" if points_to_original else "external"),
            "action": action,
        })

remaining_external = []
for directory, dirnames, filenames in os.walk(copy_root, topdown=True, followlinks=False):
    for name in sorted(set(dirnames + filenames)):
        path = os.path.join(directory, name)
        if os.path.islink(path) and not within(os.path.realpath(path), copy_real):
            remaining_external.append(os.path.relpath(path, copy_root))
if remaining_external:
    raise SystemExit(f"Safe DOCUS copy still contains external symlinks: {remaining_external}")

with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(records, handle, indent=2, ensure_ascii=False, sort_keys=True)
    handle.write("\n")
PY
}

ORIGINAL_GUARD_ARMED=0

verify_original_guard() {
  local status=0
  if ! fingerprint_tree "$FINGERPRINT_AFTER" "$DOCUS_SOURCE"; then
    status=1
  elif ! validate_original_unchanged; then
    status=1
  fi
  if ! validate_original_metadata; then
    status=1
  fi
  return "$status"
}

verify_original_on_exit() {
  local command_status=$?
  trap - EXIT
  if [[ "$ORIGINAL_GUARD_ARMED" -eq 1 ]]; then
    if ! verify_original_guard; then
      echo "DOCUS original guard failed while handling an earlier benchmark exit." >&2
      exit 97
    fi
  fi
  exit "$command_status"
}

trap verify_original_on_exit EXIT

validate_transcript_and_write_report() {
  /usr/bin/python3 - "$TRANSCRIPT" "$DOCUS_SOURCE" "$DOCUS_COPY" "$RUN_OUTPUT" "$REPORT" "$DOCUS_BENCHMARK_MODE" "$LEGACY_WORKSPACE_ROOT" "$SANITIZED_SYMLINKS" <<'PY'
import json
import os
import shlex
import sys
from collections import Counter

transcript_path, source_root, copy_root, run_output, report_path, mode, legacy_workspace_root, symlink_manifest_path = sys.argv[1:9]
expected_steps = [
    "datanalysis_env.status",
    "legacy_spectroscopy_envcheck",
    "document_intake_workbench",
    "echelle_multispec_inventory",
    "profile_table",
    "istarmod_workbench.inspect-tree",
    "istarmod_workbench.prepare-copy",
    "fxcor_iraf_workbench.prepare-session",
    "fxcor_iraf_workbench.run-auto",
    "legacy_rv_coursework_workbench.analyze",
    "legacy_external_reference_check",
    "li6708_equivalent_width_workbench.measure",
    "legacy_spectroscopy_report_builder.scaffold",
    "legacy_spectroscopy_report_builder.populate",
    "latex_workbench.review",
    "latex_workbench.compile",
]

with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)
with open(symlink_manifest_path, "r", encoding="utf-8") as handle:
    safe_copy_symlinks = json.load(handle)
if not isinstance(safe_copy_symlinks, list):
    raise SystemExit("DOCUS safe-copy symlink manifest must be a list")
removed_external_symlinks = [
    item for item in safe_copy_symlinks
    if isinstance(item, dict) and item.get("action") == "removed_from_safe_copy"
]

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    raise SystemExit("DOCUS benchmark transcript is missing agent_plan")
if plan.get("source") not in {"local", "skillRouter"}:
    raise SystemExit(f"DOCUS benchmark expected local or skillRouter planner, got {plan.get('source')!r}")

steps = plan.get("steps")
if not isinstance(steps, list):
    raise SystemExit("DOCUS benchmark transcript is missing plan steps")
step_ids = [step.get("capability_id") for step in steps]
if step_ids != expected_steps:
    raise SystemExit(f"DOCUS benchmark plan order changed.\nexpected={expected_steps}\nactual={step_ids}")

source_real = os.path.realpath(source_root)
copy_real = os.path.realpath(copy_root)
run_real = os.path.realpath(run_output)
legacy_workspace_real = os.path.realpath(legacy_workspace_root)
legacy_workspace_capabilities = frozenset({
    "legacy_spectroscopy_envcheck",
    "fxcor_iraf_workbench.prepare-session",
    "fxcor_iraf_workbench.run-auto",
    "legacy_rv_coursework_workbench.analyze",
    "legacy_external_reference_check",
    "legacy_spectroscopy_report_builder.scaffold",
    "legacy_spectroscopy_report_builder.populate",
    "latex_workbench.review",
    "latex_workbench.compile",
})
transcript_text = json.dumps(payload, ensure_ascii=False)
if source_real in transcript_text or source_root in transcript_text:
    raise SystemExit("DOCUS benchmark leaked the original DOCUS path into the transcript")
if copy_real not in transcript_text and copy_root not in transcript_text:
    raise SystemExit("DOCUS benchmark transcript does not reference the safe DOCUS copy")

for raw in [step.get("raw_arguments", "") for step in steps]:
    if source_real in raw or source_root in raw:
        raise SystemExit(f"DOCUS benchmark raw arguments reference the original DOCUS path: {raw}")

expected_document_paths = [
    os.path.join(copy_root, "P1_parte1.pdf"),
    os.path.join(copy_root, "P1_parte2.pdf"),
]
expected_document_paths.extend(sorted(
    os.path.join(copy_root, name)
    for name in os.listdir(copy_root)
    if name.lower().endswith(".html") and os.path.isfile(os.path.join(copy_root, name))
))
intake_step = next(
    (step for step in steps if step.get("capability_id") == "document_intake_workbench"),
    None,
)
if not intake_step:
    raise SystemExit("DOCUS benchmark plan is missing document_intake_workbench")
try:
    intake_tokens = shlex.split(intake_step.get("raw_arguments", ""), posix=True)
except ValueError as exc:
    raise SystemExit(f"DOCUS document-intake arguments are not parseable: {exc}") from exc
missing_planned_documents = [path for path in expected_document_paths if path not in intake_tokens]
if missing_planned_documents:
    raise SystemExit(
        "DOCUS document-intake plan omitted expected copied inputs: "
        f"{missing_planned_documents}"
    )

jobs = payload.get("jobs") or []
if mode == "plan" and jobs:
    raise SystemExit("DOCUS plan benchmark should not execute jobs")

bad_run_dirs = []
pdfs = []
job_lines = []
failed_jobs = []
completed_jobs = []
step_order = {capability: index for index, capability in enumerate(step_ids)}
ordered_jobs = sorted(
    jobs,
    key=lambda job: step_order.get(job.get("capability_id"), len(step_order))
)
summary_notes_by_job = {}
document_intake_verified = None
for job in ordered_jobs:
    capability = job.get("capability_id", "unknown")
    run_directory = job.get("run_directory")
    if isinstance(run_directory, str):
        real_run = os.path.realpath(run_directory)
        is_benchmark_run = real_run == run_real or real_run.startswith(run_real + os.sep)
        is_approved_legacy_run = (
            capability in legacy_workspace_capabilities
            and real_run.startswith(legacy_workspace_real + os.sep)
        )
        if not (is_benchmark_run or is_approved_legacy_run):
            bad_run_dirs.append(run_directory)
        summary_path = os.path.join(run_directory, "summary.json")
        if os.path.isfile(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as handle:
                    summary_payload = json.load(handle)
                notes = summary_payload.get("notes") or summary_payload.get("warnings") or []
                if isinstance(notes, str):
                    notes = [notes]
                if isinstance(notes, list):
                    summary_notes_by_job[job.get("capability_id")] = [str(note) for note in notes]
                if capability == "document_intake_workbench":
                    discovery = summary_payload.get("discovery")
                    files = summary_payload.get("files")
                    if not isinstance(discovery, dict):
                        discovery = ((summary_payload.get("results") or {}).get("intake") or {}).get("discovery")
                    if not isinstance(files, list):
                        files = ((summary_payload.get("results") or {}).get("intake") or {}).get("files")
                    if not isinstance(discovery, dict) or not isinstance(files, list):
                        raise SystemExit("DOCUS document-intake summary lacks discovery/files evidence")
                    missing_inputs = discovery.get("missing_inputs") or []
                    input_count = discovery.get("input_count")
                    found_count = discovery.get("found_count")
                    limit_reached = discovery.get("limit_reached")
                    expected_names = [os.path.basename(path) for path in expected_document_paths]
                    actual_names = [item.get("name") for item in files if isinstance(item, dict)]
                    if (
                        missing_inputs
                        or limit_reached
                        or input_count != len(expected_document_paths)
                        or found_count != input_count
                        or Counter(actual_names) != Counter(expected_names)
                    ):
                        raise SystemExit(
                            "DOCUS document intake was incomplete; "
                            f"expected={expected_names!r} actual={actual_names!r} "
                            f"input_count={input_count!r} found_count={found_count!r} "
                            f"missing_inputs={missing_inputs!r} limit_reached={limit_reached!r}"
                        )
                    document_intake_verified = f"{found_count}/{input_count} expected copied inputs"
            except Exception as exc:
                summary_notes_by_job[job.get("capability_id")] = [f"Could not read summary notes: {exc}"]
    status = job.get("status", "unknown")
    exit_code = job.get("exit_code", "-")
    parsed_status = job.get("parsed_status")
    message = job.get("message")
    recovery = job.get("recovery_advice")
    details = []
    if parsed_status:
        details.append(f"parsed `{parsed_status}`")
    if message:
        details.append(str(message).replace("\n", " ")[:240])
    if recovery:
        details.append(f"recovery: {str(recovery).replace(chr(10), ' ')[:240]}")
    suffix = f" - {'; '.join(details)}" if details else ""
    job_lines.append(f"- `{capability}`: {status}, exit {exit_code}{suffix}")
    if status == "succeeded":
        completed_jobs.append(capability)
    else:
        failed_jobs.append(job)
    for artifact in job.get("artifacts") or []:
        path = artifact.get("path")
        if isinstance(path, str) and path.lower().endswith(".pdf"):
            pdfs.append(path)

if bad_run_dirs:
    raise SystemExit(f"DOCUS benchmark wrote jobs outside the benchmark output root: {bad_run_dirs[:5]}")

if mode in {"progress", "full"} and not jobs:
    raise SystemExit(f"DOCUS {mode} benchmark did not execute any jobs")

if mode == "full" and (
    failed_jobs
    or Counter(completed_jobs) != Counter(expected_steps)
    or any(job.get("exit_code") != 0 for job in jobs)
):
    job_statuses = ", ".join(f"{job.get('capability_id')}={job.get('status')}" for job in jobs)
    raise SystemExit(
        "DOCUS full benchmark requires every planned job exactly once, succeeded with exit 0. "
        f"Job statuses: {job_statuses}"
    )

if mode == "full" and not pdfs:
    job_statuses = ", ".join(f"{job.get('capability_id')}={job.get('status')}" for job in jobs)
    raise SystemExit(f"DOCUS full benchmark did not index a final PDF. Job statuses: {job_statuses}")

if mode == "full" and document_intake_verified is None:
    raise SystemExit("DOCUS full benchmark lacks complete document-intake evidence")

first_blocker = failed_jobs[0] if failed_jobs else None
first_blocker_capability = first_blocker.get("capability_id") if first_blocker else None
next_step = None
if first_blocker_capability in step_ids:
    blocked_index = step_ids.index(first_blocker_capability)
    if blocked_index + 1 < len(step_ids):
        next_step = step_ids[blocked_index + 1]

report = [
    "# DOCUS Benchmark Report",
    "",
    f"- Mode: `{mode}`",
    f"- Original DOCUS: `{source_root}`",
    f"- Safe copy: `{copy_root}`",
    f"- Run output: `{run_output}`",
    f"- Approved legacy workspace root: `{legacy_workspace_root}`",
    f"- Safe-copy external symlinks neutralized: `{len(removed_external_symlinks)}`",
    f"- Transcript: `{transcript_path}`",
    f"- Plan source: `{plan.get('source')}`",
    f"- Planned enabled steps: `{len([step for step in steps if step.get('is_enabled', True)])}`",
    f"- Executed jobs: `{len(jobs)}`",
    f"- Successful jobs: `{len(completed_jobs)}`",
    f"- Document intake: `{document_intake_verified or 'not executed in this mode'}`",
    f"- First blocker: `{first_blocker_capability or 'none'}`",
    f"- Next planned step after blocker: `{next_step or 'none'}`",
    "",
    "## Plan",
    "",
]
report.extend(f"{index}. `{capability}`" for index, capability in enumerate(step_ids, start=1))
report.extend(["", "## Jobs", ""])
report.extend(job_lines or ["- Plan-only benchmark; no jobs executed."])
if first_blocker:
    blocker_notes = summary_notes_by_job.get(first_blocker.get("capability_id"), [])
    report.extend([
        "",
        "## First Blocker",
        "",
        f"- Capability: `{first_blocker.get('capability_id')}`",
        f"- Status: `{first_blocker.get('status')}`",
        f"- Exit code: `{first_blocker.get('exit_code')}`",
        f"- Parsed status: `{first_blocker.get('parsed_status') or '-'}`",
        f"- Message: {str(first_blocker.get('message') or '-').replace(chr(10), ' ')[:500]}",
        f"- Recovery advice: {str(first_blocker.get('recovery_advice') or '-').replace(chr(10), ' ')[:500]}",
    ])
    if blocker_notes:
        report.extend(["", "### Structured Notes", ""])
        report.extend(f"- {note}" for note in blocker_notes[:20])
report.extend(["", "## PDF Artifacts", ""])
report.extend([f"- `{path}`" for path in pdfs] or ["- No PDF artifacts indexed in this mode."])
report.extend([
    "",
    "## Safety Checks",
    "",
    "- Original DOCUS path was fingerprinted before and after the benchmark.",
    "- The app received only the safe DOCUS copy as input.",
    "- External symlinks were removed only from the safe copy and recorded before execution.",
    "- Plan raw arguments were checked for accidental references to the original DOCUS path.",
    "- Planned and executed document intake were checked against every copied PDF/HTML target.",
    "- Jobs outside run output were accepted only for the exact path-sensitive capability allowlist under the canonical legacy workspace root.",
])

with open(report_path, "w", encoding="utf-8") as handle:
    handle.write("\n".join(report) + "\n")

progress = f", first blocker {first_blocker_capability}" if first_blocker_capability else ""
print(f"ok DOCUS {mode} benchmark: {len(step_ids)} planned steps, {len(jobs)} jobs, {len(pdfs)} PDF artifacts{progress}")
PY
}

validate_required_docus_shape
fingerprint_tree "$FINGERPRINT_BEFORE" "$DOCUS_SOURCE"
capture_original_metadata
ORIGINAL_GUARD_ARMED=1

/usr/bin/ditto "$DOCUS_SOURCE" "$DOCUS_COPY"
sanitize_safe_copy_symlinks

command=(
  "$APP_BINARY"
  --agent-input "$DOCUS_COPY"
  --agent-mode workflow
  --agent-ai-provider ollama
  --agent-local-planner
  --agent-output-root "$RUN_OUTPUT"
  --agent-prompt "$PROMPT"
  --agent-transcript-json "$TRANSCRIPT"
  --agent-isolated-session
  --agent-exit-after-run
)

if [[ "$DOCUS_BENCHMARK_MODE" == "progress" || "$DOCUS_BENCHMARK_MODE" == "full" ]]; then
  command+=(--agent-auto-run --agent-enable-restricted-steps)
fi

"${command[@]}"
if ! verify_original_guard; then
  ORIGINAL_GUARD_ARMED=0
  echo "DOCUS original changed or could not be fully verified after benchmark execution." >&2
  exit 97
fi
ORIGINAL_GUARD_ARMED=0
validate_transcript_and_write_report

echo "Scientific Workbench DOCUS benchmark passed."
echo "Benchmark report: $REPORT"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${1:-}"

fail() {
  echo "release manifest verify failed: $*" >&2
  exit 1
}

if [[ -z "$MANIFEST" ]]; then
  MANIFEST="$(/usr/bin/python3 - "$ROOT_DIR/dist/release" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
candidates = list(root.glob("**/manifest.json")) + list(root.glob("**/*_manifest.json"))
if candidates:
    print(max(candidates, key=lambda path: path.stat().st_mtime))
PY
)"
fi

[[ -n "$MANIFEST" ]] || fail "no manifest path supplied and no release manifest found"
[[ -f "$MANIFEST" ]] || fail "missing manifest at $MANIFEST"

/usr/bin/python3 - "$MANIFEST" <<'PY'
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

manifest_path = Path(sys.argv[1]).resolve()
manifest_bytes = manifest_path.read_bytes()
manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
payload = json.loads(manifest_bytes.decode("utf-8"))

def fail(message: str) -> None:
    raise SystemExit(message)

required = [
    "app_name",
    "bundle_identifier",
    "version",
    "build",
    "minimum_macos",
    "archive_file",
    "archive_relative_path",
    "archive_size_bytes",
    "sha256",
    "signed",
    "notarized",
    "quality_gate_ran",
    "source_revision",
    "created_at",
]
missing = [key for key in required if key not in payload]
if missing:
    fail(f"missing keys: {', '.join(missing)}")

if payload["app_name"] != "Scientific Workbench":
    fail(f"unexpected app_name: {payload['app_name']!r}")
if payload["bundle_identifier"] != "com.emilio.scientific-workbench":
    fail(f"unexpected bundle_identifier: {payload['bundle_identifier']!r}")
if not re.fullmatch(r"[0-9]+(\.[0-9]+){0,2}", str(payload["version"])):
    fail(f"version must be numeric: {payload['version']!r}")
if not re.fullmatch(r"[0-9A-Za-z.-]+", str(payload["build"])):
    fail(f"invalid build: {payload['build']!r}")
if payload["minimum_macos"] != "14.0":
    fail(f"unexpected minimum_macos: {payload['minimum_macos']!r}")

archive_file = str(payload["archive_file"])
if "/" in archive_file or archive_file != os.path.basename(archive_file):
    fail(f"archive_file must be a basename: {archive_file!r}")
archive_path = manifest_path.parent / archive_file
if not archive_path.is_file():
    fail(f"missing archive file: {archive_path}")

expected_relative = f"{payload['version']}/{archive_file}"
if payload["archive_relative_path"] != expected_relative:
    fail(
        "archive_relative_path mismatch: "
        f"{payload['archive_relative_path']!r} != {expected_relative!r}"
    )

size = archive_path.stat().st_size
if size <= 0:
    fail("archive is empty")
if int(payload["archive_size_bytes"]) != size:
    fail(f"archive_size_bytes mismatch: {payload['archive_size_bytes']!r} != {size}")

digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
if payload["sha256"] != digest:
    fail("sha256 mismatch")

for key in ["signed", "notarized", "quality_gate_ran"]:
    if not isinstance(payload[key], bool):
        fail(f"{key} must be boolean")
if payload["notarized"] and not payload["signed"]:
    fail("notarized release evidence must also be signed")

try:
    dt.datetime.strptime(payload["created_at"], "%Y-%m-%dT%H:%M:%SZ")
except ValueError as exc:
    fail(f"created_at must be UTC ISO-8601 seconds: {exc}")

declared_schema_version = payload.get("manifest_schema_version")
legacy_schema_v1_location = (
    manifest_path.name == "manifest.json"
    and manifest_path.parent.name == str(payload["version"])
)
known_legacy_manifests = {
    "37cd62074728789655567466a1803c697e40cb4b89034b977c646fab715ebf2c": {
        "version": "1.0.0",
        "build": "post-audit-hardening",
        "archive_file": "Scientific_Workbench_1.0.0_post-audit-hardening_macOS.zip",
        "archive_size_bytes": 2441833,
        "sha256": "7559ad3bfc1054f4aeb63ed25ff8fdfa1ff52b150e32f63353b0a8fa73674033",
        "quality_gate_ran": True,
        "source_revision": "unknown",
        "created_at": "2026-06-06T14:12:44Z",
    }
}
if declared_schema_version is None:
    if not legacy_schema_v1_location:
        fail("non-legacy release manifests must declare manifest_schema_version")
    expected_legacy = known_legacy_manifests.get(manifest_digest)
    if expected_legacy is None:
        fail("unrecognized legacy schema-1 evidence; new manifests require schema 2")
    mismatches = [
        key
        for key, expected_value in expected_legacy.items()
        if payload.get(key) != expected_value
    ]
    if mismatches:
        fail(
            "recognized legacy manifest identity mismatch: "
            + ", ".join(mismatches)
        )
    schema_version = 1
else:
    if isinstance(declared_schema_version, bool) or not isinstance(declared_schema_version, int):
        fail("manifest_schema_version must be an integer")
    schema_version = declared_schema_version
    if schema_version == 1:
        fail("schema v1 is reserved for recognized immutable historical evidence")

if schema_version not in (1, 2):
    fail(f"unsupported manifest_schema_version: {schema_version!r}")

schema_v2_only_keys = [
    "integrated_release",
    "skill_release",
    "source_revision_short",
    "source_dirty",
    "git_branch",
    "environment",
    "validation",
    "skill_registry_sha256",
    "skill_registry_stub_sha256",
    "skill_registry_relative_path",
    "skill_registry_chain",
]
if schema_version == 1:
    if not legacy_schema_v1_location:
        fail("schema v1 manifests are only supported as <version>/manifest.json")
    unexpected_v2 = [key for key in schema_v2_only_keys if key in payload]
    if unexpected_v2:
        fail(
            "schema v1 manifest contains schema v2 fields: "
            + ", ".join(unexpected_v2)
        )

if schema_version == 2:
    required_v2 = schema_v2_only_keys
    missing_v2 = [key for key in required_v2 if key not in payload]
    if missing_v2:
        fail(f"missing schema v2 keys: {', '.join(missing_v2)}")

    expected_manifest_name = (
        f"Scientific_Workbench_{payload['version']}_{payload['build']}_manifest.json"
    )
    if manifest_path.name != expected_manifest_name:
        fail(
            "schema v2 manifest filename mismatch: "
            f"{manifest_path.name!r} != {expected_manifest_name!r}"
        )
    expected_archive_name = (
        f"Scientific_Workbench_{payload['version']}_{payload['build']}_macOS.zip"
    )
    if archive_file != expected_archive_name:
        fail(
            "schema v2 archive filename mismatch: "
            f"{archive_file!r} != {expected_archive_name!r}"
        )

    for key in ["integrated_release", "skill_release"]:
        if not re.fullmatch(r"[0-9]+(\.[0-9]+){0,2}", str(payload[key])):
            fail(f"{key} must be numeric: {payload[key]!r}")

    source_revision = str(payload["source_revision"])
    source_revision_short = str(payload["source_revision_short"])
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        fail("schema v2 source_revision must be a full lowercase Git SHA")
    if not re.fullmatch(r"[0-9a-f]{7,40}", source_revision_short):
        fail("schema v2 source_revision_short must be a lowercase Git SHA prefix")
    if not source_revision.startswith(source_revision_short):
        fail("source_revision_short is not a prefix of source_revision")
    if payload["source_dirty"] is not False:
        fail("schema v2 release manifests must record source_dirty as false")
    if not isinstance(payload["git_branch"], str) or not payload["git_branch"]:
        fail("git_branch must be a non-empty string")

    environment = payload["environment"]
    if not isinstance(environment, dict):
        fail("environment must be an object")
    for key in ["swift_version", "macos_version", "architecture"]:
        if not isinstance(environment.get(key), str) or not environment[key]:
            fail(f"environment.{key} must be a non-empty string")

    validation = payload["validation"]
    if not isinstance(validation, dict):
        fail("validation must be an object")
    for key in ["quality_gate_ran", "docus_benchmark_ran"]:
        if not isinstance(validation.get(key), bool):
            fail(f"validation.{key} must be boolean")
    if validation["quality_gate_ran"] != payload["quality_gate_ran"]:
        fail("validation.quality_gate_ran conflicts with quality_gate_ran")
    if validation["docus_benchmark_ran"]:
        if validation.get("docus_benchmark_mode") not in ("plan", "full"):
            fail("a DOCUS benchmark requires docus_benchmark_mode plan or full")
        if not validation["quality_gate_ran"]:
            fail("DOCUS benchmark evidence requires the quality gate")
    elif validation.get("docus_benchmark_mode") is not None:
        fail("docus_benchmark_mode must be null when DOCUS did not run")

    for key in ["skill_registry_sha256", "skill_registry_stub_sha256"]:
        if not re.fullmatch(r"[0-9a-f]{64}", str(payload[key])):
            fail(f"{key} must be a lowercase SHA-256")

    registry_relative_path = payload["skill_registry_relative_path"]
    if not isinstance(registry_relative_path, str) or not registry_relative_path:
        fail("skill_registry_relative_path must be a non-empty string")
    registry_path = PurePosixPath(registry_relative_path)
    if (
        registry_path.is_absolute()
        or "\\" in registry_relative_path
        or any(part in ("", ".", "..") for part in registry_path.parts)
    ):
        fail("skill_registry_relative_path must stay within the installed skills root")

    registry_chain = payload["skill_registry_chain"]
    if not isinstance(registry_chain, list) or not registry_chain:
        fail("skill_registry_chain must be a non-empty array")
    if len(registry_chain) > 16:
        fail("skill_registry_chain exceeds the supported maximum depth")

    chain_paths = []
    for index, item in enumerate(registry_chain):
        if not isinstance(item, dict):
            fail(f"skill_registry_chain[{index}] must be an object")
        relative_path = item.get("relative_path")
        item_digest = item.get("sha256")
        if not isinstance(relative_path, str) or not relative_path:
            fail(f"skill_registry_chain[{index}].relative_path must be a string")
        item_path = PurePosixPath(relative_path)
        if (
            item_path.is_absolute()
            or "\\" in relative_path
            or any(part in ("", ".", "..") for part in item_path.parts)
        ):
            fail(
                f"skill_registry_chain[{index}].relative_path escapes the skills root"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", str(item_digest)):
            fail(f"skill_registry_chain[{index}].sha256 must be a lowercase SHA-256")
        chain_paths.append(relative_path)

    if len(set(chain_paths)) != len(chain_paths):
        fail("skill_registry_chain contains a duplicate path")
    if chain_paths[0] != "scientific-data-analysis/public_surface_registry.yaml":
        fail("skill_registry_chain must begin at the mother-skill registry")
    if chain_paths[-1] != registry_relative_path:
        fail("skill_registry_relative_path does not match the registry chain")
    if registry_chain[0]["sha256"] != payload["skill_registry_stub_sha256"]:
        fail("skill_registry_stub_sha256 does not match the registry chain")
    if registry_chain[-1]["sha256"] != payload["skill_registry_sha256"]:
        fail("skill_registry_sha256 does not match the registry chain")

print("Scientific Workbench release manifest verified.")
PY

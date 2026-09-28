#!/usr/bin/env python3
"""Current-contract integrity gate for the scientific-data skill family v2.8."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - datanalysis includes PyYAML.
    yaml = None


SKILL_NAMES = [
    "scientific-data-analysis",
    "scientific-data-astro",
    "scientific-data-documents",
    "scientific-data-notebooks",
    "scientific-data-maintainer",
]
EXPECTED_CAPABILITIES = 61
EXPECTED_MAINTAINER_IDS = {
    "external_astro_tools_local_validation",
    "capability_probe_matrix",
    "portable_smoke_test",
    "validate_skill_samples",
    "sync_public_surface_docs",
    "skill_surface_audit",
}
MODULE_FIELDS = ("owner_module", "child_skill_path", "delegation_mode", "wrapper_status")
SHARED_HELPERS = (
    "provenance_utils.py",
    "public_contract.py",
    "public_surface_registry.py",
    "run_bundle.py",
    "child_skill_dispatch.py",
    "path_safety.py",
)


def _family_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if all((candidate / name).is_dir() for name in SKILL_NAMES):
            return candidate
    raise RuntimeError("could not locate the five-skill family root")


FAMILY = _family_root()
MOTHER = FAMILY / "scientific-data-analysis"
MAINTAINER = FAMILY / "scientific-data-maintainer"


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _simple_yaml_value(path: Path, key: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip().strip("\"'")
    return None


def _frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter must start on line 1")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("frontmatter closing delimiter is missing") from exc
    body = "\n".join(lines[1:end])
    if yaml is not None:
        try:
            loaded = yaml.safe_load(body)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML frontmatter: {exc}") from exc
        if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
            raise ValueError("frontmatter must be a YAML mapping")
        return {key: str(value) if value is not None else "" for key, value in loaded.items()}

    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() or ":" not in line:
            raise ValueError(f"fallback parser only accepts flat key/value frontmatter: {line}")
        key, value = line.split(":", 1)
        value = value.strip()
        if value[:1] not in {"\"", "'"} and re.search(r":\s", value):
            raise ValueError(f"unquoted colon in frontmatter value: {line}")
        values[key.strip()] = value.strip("\"'")
    return values


def _parse_registry_entries(path: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        start = re.match(r"^\s*-\s+id\s*:\s*(.+?)\s*$", line)
        if start:
            if current is not None:
                entries.append(current)
            current = {"id": start.group(1).strip().strip("\"'")}
            continue
        if current is None:
            continue
        field = re.match(r"^\s{4}([A-Za-z0-9_]+)\s*:\s*(.*?)\s*$", line)
        if field:
            current[field.group(1)] = field.group(2).strip().strip("\"'")
    if current is not None:
        entries.append(current)
    return entries


def _resolve_registry(stub: Path, *, max_depth: int = 8) -> tuple[Path, list[Path], list[dict[str, str]]]:
    current = stub.expanduser().absolute()
    visited: list[Path] = []
    for _ in range(max_depth + 1):
        resolved = current.resolve()
        if not _within(resolved, FAMILY.resolve()):
            raise ValueError(f"registry target escapes skill family: {resolved}")
        if resolved in visited:
            raise ValueError(f"registry cycle detected at {resolved}")
        if not resolved.is_file():
            raise FileNotFoundError(f"registry target missing: {resolved}")
        visited.append(resolved)
        entries = _parse_registry_entries(resolved)
        if entries:
            return resolved, visited, entries
        target = _simple_yaml_value(resolved, "canonical_registry")
        if not target:
            raise ValueError(f"registry has neither entries nor canonical_registry: {resolved}")
        current = current.parent / target
    raise ValueError(f"registry chain exceeds max depth {max_depth}: {stub}")


def _resolve_module_map(stub: Path, *, max_depth: int = 8) -> tuple[Path, list[dict[str, Any]]]:
    current = stub.expanduser().absolute()
    visited: list[Path] = []
    for _ in range(max_depth + 1):
        resolved = current.resolve()
        if not _within(resolved, FAMILY.resolve()):
            raise ValueError(f"module map escapes skill family: {resolved}")
        if resolved in visited:
            raise ValueError(f"module map cycle detected at {resolved}")
        if not resolved.is_file():
            raise FileNotFoundError(f"module map target missing: {resolved}")
        visited.append(resolved)
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        capabilities = payload.get("capabilities")
        if isinstance(capabilities, list):
            return resolved, capabilities
        target = payload.get("canonical_fixture")
        if not target:
            raise ValueError(f"module map has neither capabilities nor canonical_fixture: {resolved}")
        current = current.parent / str(target)
    raise ValueError(f"module map chain exceeds max depth {max_depth}: {stub}")


def _router_probe() -> dict[str, Any]:
    code = r'''
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "fixtures"))
import scientific_workflow_router as router
module_map = router._module_map()
metadata = {
    item["capability_id"]: router.module_metadata_for(item["label"], item["capability_id"])
    for item in module_map["capabilities"]
}
rejected = router.explain_capability(
    "physical_qa.py",
    [],
    [{"label": "physical_qa.py", "reason": "fixture rejection"}],
)
print(json.dumps({
    "resolved_path": module_map.get("_resolved_path"),
    "metadata": metadata,
    "rejected_explain": rejected,
}, sort_keys=True))
'''
    proc = subprocess.run(
        [sys.executable, "-c", code, str(MOTHER)],
        cwd=MOTHER,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"router metadata probe failed rc={proc.returncode}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _router_broken_map_probe() -> dict[str, Any]:
    code = r'''
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "fixtures"))
import scientific_workflow_router as router
router.MODULE_MAP_PATH = root / "references" / "__v2_8_intentionally_missing_module_map__.json"
router._MODULE_MAP_CACHE = None
sys.argv = ["scientific_workflow_router.py", "plan", str(root / "SKILL.md")]
raise SystemExit(router.main())
'''
    proc = subprocess.run(
        [sys.executable, "-c", code, str(MOTHER)],
        cwd=MOTHER,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pass
    return {
        "returncode": proc.returncode,
        "payload": payload,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _load_registry_helper(path: Path):
    spec = importlib.util.spec_from_file_location("_v2_8_registry_helper", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load registry helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exercise_registry_helper(path: Path) -> None:
    helper = _load_registry_helper(path)
    with tempfile.TemporaryDirectory(prefix="sda-v2-8-registry-") as raw_tmp:
        base = Path(raw_tmp)
        family = base / "family"
        family.mkdir()
        terminal = family / "terminal.yaml"
        terminal.write_text(
            "entries:\n"
            "  - id: alpha\n"
            "    label: Alpha\n"
            "    script: scripts/alpha.py\n",
            encoding="utf-8",
        )
        first = family / "first.yaml"
        second = family / "second.yaml"
        first.write_text("canonical_registry: second.yaml\n", encoding="utf-8")
        second.write_text("canonical_registry: terminal.yaml\n", encoding="utf-8")
        loaded = helper.load_public_surface_registry(first, family_root=family)
        if [item.get("id") for item in loaded] != ["alpha"]:
            raise AssertionError("registry helper did not resolve a valid chain")

        cycle_a = family / "cycle-a.yaml"
        cycle_b = family / "cycle-b.yaml"
        cycle_a.write_text("canonical_registry: cycle-b.yaml\n", encoding="utf-8")
        cycle_b.write_text("canonical_registry: cycle-a.yaml\n", encoding="utf-8")
        try:
            helper.load_public_surface_registry(cycle_a, family_root=family)
        except ValueError as exc:
            if "cycle" not in str(exc).lower():
                raise AssertionError(f"cycle error is not explicit: {exc}") from exc
        else:
            raise AssertionError("registry cycle was accepted")

        try:
            helper.load_public_surface_registry(first, family_root=family, max_depth=1)
        except ValueError as exc:
            if "depth" not in str(exc).lower():
                raise AssertionError(f"depth error is not explicit: {exc}") from exc
        else:
            raise AssertionError("registry chain exceeding max_depth was accepted")

        outside = base / "outside.yaml"
        outside.write_text(terminal.read_text(encoding="utf-8"), encoding="utf-8")
        escape = family / "escape.yaml"
        escape.write_text("canonical_registry: ../outside.yaml\n", encoding="utf-8")
        try:
            helper.load_public_surface_registry(escape, family_root=family)
        except ValueError as exc:
            if "escape" not in str(exc).lower():
                raise AssertionError(f"out-of-family error is not explicit: {exc}") from exc
        else:
            raise AssertionError("out-of-family registry target was accepted")


def _shared_helper_hashes() -> dict[str, dict[str, str]]:
    hashes: dict[str, dict[str, str]] = {}
    for helper in SHARED_HELPERS:
        per_skill: dict[str, str] = {}
        for skill in SKILL_NAMES:
            path = FAMILY / skill / "fixtures/_internal" / helper
            if not path.is_file():
                raise FileNotFoundError(f"shared helper missing: {path}")
            per_skill[skill] = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[helper] = per_skill
    return hashes


def _common_contract_probe() -> dict[str, Any]:
    code = r'''
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "fixtures"))
from _internal import child_skill_dispatch as dispatch
from _internal import path_safety
from _internal import provenance_utils as provenance
from _internal import public_contract

failures = []
statuses = ["ok", "warning", "blocked", "fail", "broken"]
severity = {"ok": 0, "warning": 1, "blocked": 2, "fail": 3, "broken": 4}
app = {"ok": "PASS", "warning": "WARNING", "blocked": "BLOCKED_CONTROLADO", "fail": "FAIL", "broken": "ROTO"}
matrix_cases = 0
for tool_status in statuses:
    for qa_status in statuses:
        payload = provenance.standard_tool_payload(
            "v2_8_matrix",
            status=tool_status,
            qa={"status": qa_status, "findings": [f"qa={qa_status}"]},
        )
        expected_status = max((tool_status, qa_status), key=lambda value: severity[value])
        if payload.get("app_status") != app[expected_status]:
            failures.append(f"status matrix {tool_status}/{qa_status}: expected {app[expected_status]}, got {payload.get('app_status')}")
        if qa_status in {"blocked", "fail", "broken"} and not payload.get("errors"):
            failures.append(f"status matrix {tool_status}/{qa_status}: severe QA finding missing from errors")
        matrix_cases += 1

aliases = {}
for source, expected_internal, expected_app in (
    ("BLOCKED_CONTROLADO", "blocked", "BLOCKED_CONTROLADO"),
    ("ROTO", "broken", "ROTO"),
):
    payload = provenance.standard_tool_payload("v2_8_alias", status=source)
    aliases[source] = {"status": payload.get("status"), "app_status": payload.get("app_status")}
    if payload.get("status") != expected_internal or payload.get("app_status") != expected_app:
        failures.append(f"alias {source}: got status={payload.get('status')} app_status={payload.get('app_status')}")

nonfinite = provenance.standard_tool_payload(
    "v2_8_nonfinite",
    status="ok",
    results={"nan": float("nan"), "positive": float("inf"), "negative": float("-inf")},
    qa={"status": "ok", "findings": []},
)
try:
    json.dumps(nonfinite, allow_nan=False)
except ValueError as exc:
    failures.append(f"non-finite payload is not strict JSON: {exc}")
finding_text = " ".join(str(item) for item in nonfinite.get("qa", {}).get("findings", []))
if "non-finite" not in finding_text.lower() or "$.results.nan" not in finding_text:
    failures.append("non-finite conversion lacks an explicit path-aware QA finding")
if nonfinite.get("app_status") != "WARNING":
    failures.append(f"non-finite conversion must downgrade to WARNING, got {nonfinite.get('app_status')}")
buffer = io.StringIO()
try:
    with contextlib.redirect_stdout(buffer):
        rendered = public_contract.emit_payload(nonfinite)
    json.loads(rendered)
except Exception as exc:
    failures.append(f"public emit_payload rejected strict non-finite envelope: {type(exc).__name__}: {exc}")

try:
    with tempfile.TemporaryDirectory(prefix="v2_8_atomic_emit_") as raw:
        probe_root = Path(raw)
        for alias_kind in ("symlink", "hardlink"):
            target = probe_root / f"{alias_kind}-target.txt"
            alias = probe_root / f"{alias_kind}-summary.json"
            target.write_text("V28_IMMUTABLE_TARGET\n", encoding="utf-8")
            if alias_kind == "symlink":
                alias.symlink_to(target)
            else:
                os.link(target, alias)
            alias_buffer = io.StringIO()
            with contextlib.redirect_stdout(alias_buffer):
                public_contract.emit_payload(nonfinite, alias)
            if target.read_text(encoding="utf-8") != "V28_IMMUTABLE_TARGET\n":
                failures.append(f"atomic emit mutated {alias_kind} target")
            try:
                json.loads(alias.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"atomic emit left invalid {alias_kind} output: {type(exc).__name__}: {exc}")
            if alias.is_symlink() or alias.samefile(target):
                failures.append(f"atomic emit kept {alias_kind} output aliased to protected target")
except Exception as exc:
    failures.append(f"atomic emit alias probe failed: {type(exc).__name__}: {exc}")

path_safety_cases = 0
try:
    with tempfile.TemporaryDirectory(prefix="v2_8_path_safety_") as raw:
        probe_root = Path(raw)
        protected_tree = probe_root / "protected-tree"
        output_tree = probe_root / "output-tree"
        protected_tree.mkdir()
        output_tree.mkdir()
        protected = protected_tree / "raw.dat"
        protected.write_text("V28_PROTECTED\n", encoding="utf-8")
        symlink = probe_root / "symlink-output.dat"
        symlink.symlink_to(protected)
        hardlink = probe_root / "hardlink-output.dat"
        os.link(protected, hardlink)
        output_member = output_tree / "summary.json"
        os.link(protected, output_member)

        for label, candidate in (
            ("exact", protected),
            ("symlink", symlink),
            ("hardlink", hardlink),
            ("tree_member_hardlink", output_member),
            ("output_tree_hardlink", output_tree),
        ):
            if not path_safety.output_overlaps_input(candidate, protected_tree):
                failures.append(f"path safety missed {label} alias/tree overlap")
            path_safety_cases += 1

        same_output = probe_root / "same-output.json"
        output_collisions = path_safety.find_output_input_collisions(
            [],
            [("summary", same_output), ("manifest", same_output)],
        )
        if not any(item.get("collision_kind") == "output_output_alias" for item in output_collisions):
            failures.append("path safety missed exact output/output alias")
        path_safety_cases += 1

        normal_output_dir = probe_root / "normal-derived"
        normal_summary = normal_output_dir / "summary.json"
        try:
            path_safety.ensure_safe_paths(
                inputs=[path_safety.operand("raw", protected)],
                outputs=[
                    path_safety.operand("output-dir", normal_output_dir, tree=True),
                    path_safety.operand("summary", normal_summary),
                ],
            )
        except path_safety.PathSafetyError as exc:
            failures.append(f"path safety rejected normal summary inside output directory: {exc}")
        path_safety_cases += 1

        try:
            path_safety.ensure_safe_paths(
                inputs=[path_safety.operand("raw-tree", protected_tree, tree=True)],
                outputs=[path_safety.operand("output-tree", output_tree, tree=True)],
            )
        except path_safety.PathSafetyError:
            pass
        else:
            failures.append("path safety accepted output tree hard-linked to protected tree")
        path_safety_cases += 1
except Exception as exc:
    failures.append(f"path safety probe failed: {type(exc).__name__}: {exc}")

sentinel = "V28_SYNTHETIC_SECRET_SENTINEL"
secret_command = provenance.command_payload(
    [
        "tool",
        "--token",
        sentinel,
        f"--api-key={sentinel}",
        f"API_KEY={sentinel}",
        f"https://example.invalid/run?token={sentinel}",
        f"Authorization: Bearer {sentinel}",
        f"Authorization=Bearer {sentinel}",
    ]
)
secret_rendered = json.dumps(secret_command, sort_keys=True)
if sentinel in secret_rendered:
    failures.append("synthetic secret sentinel survived command redaction")
if secret_command.get("redacted") is not True:
    failures.append("command payload does not truthfully declare redaction")

missing_child = "scientific-data-v2-8-intentionally-missing-child"
capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    child_rc = dispatch.main("/tmp/sda-v2-8-wrapper/fake_wrapper.py", missing_child)
child_stdout = capture.getvalue()
try:
    child_payload = json.loads(child_stdout)
except json.JSONDecodeError as exc:
    child_payload = {}
    failures.append(f"missing-child fallback is not JSON: {exc}")
required = {
    "tool", "status", "contract_version", "app_status", "command", "inputs",
    "outputs", "typed_artifacts", "errors", "qa", "provenance", "app_hints",
    "next_actions", "original_modified",
}
missing_fields = sorted(required - set(child_payload))
if missing_fields:
    failures.append("missing-child envelope lacks fields: " + ", ".join(missing_fields))
if child_rc == 0 or str(child_payload.get("app_status", "")).upper() != "FAIL":
    failures.append(f"missing-child fallback must return nonzero FAIL, got rc={child_rc} app_status={child_payload.get('app_status')}")
error_kinds = [item.get("kind") for item in child_payload.get("errors", []) if isinstance(item, dict)]
if not error_kinds or any(kind not in provenance.APP_ERROR_KINDS for kind in error_kinds):
    failures.append(f"missing-child fallback has invalid error kinds: {error_kinds}")
if "traceback" in child_stdout.lower():
    failures.append("missing-child fallback leaked a traceback")

print(json.dumps({
    "failures": failures,
    "matrix_cases": matrix_cases,
    "aliases": aliases,
    "atomic_alias_targets_preserved": not any(item.startswith("atomic emit") for item in failures),
    "path_safety_cases": path_safety_cases,
    "nonfinite_app_status": nonfinite.get("app_status"),
    "secret_redacted": sentinel not in secret_rendered,
    "missing_child": {
        "returncode": child_rc,
        "app_status": child_payload.get("app_status"),
        "error_kinds": error_kinds,
        "required_fields_present": not missing_fields,
    },
}, sort_keys=True))
'''
    proc = subprocess.run(
        [sys.executable, "-c", code, str(MOTHER)],
        cwd=MOTHER,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"common contract probe failed rc={proc.returncode}: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"common contract probe emitted non-JSON stdout: {proc.stdout!r}") from exc


def _broken_symlinks(root: Path) -> list[str]:
    broken: list[str] = []
    for current, directories, files in os.walk(root, followlinks=False):
        for name in [*directories, *files]:
            item = Path(current) / name
            if item.is_symlink() and not item.exists():
                broken.append(str(item))
    return sorted(broken)


def _hardcoded_active_paths() -> list[str]:
    active = [
        MOTHER / "fixtures/scientific_workflow_router.py",
        MOTHER / "fixtures/_internal/public_surface_registry.py",
        MOTHER / "references/v2-3-mother-router-module-map.json",
        MOTHER / "references/v2-8-family-integrity-hardening.md",
        MAINTAINER / "fixtures/_internal/public_surface_registry.py",
        MAINTAINER / "fixtures/v2_6_measured_usage_common.py",
        MAINTAINER / "fixtures/portable_smoke_test.py",
        MAINTAINER / "fixtures/skill_surface_audit.py",
        MAINTAINER / "fixtures/audit_v2_8_family_integrity_regression.py",
        MAINTAINER / "references/v2-8-current-release-gates.md",
    ]
    for skill in SKILL_NAMES:
        root = FAMILY / skill
        active.extend([root / "SKILL.md", root / "agents/openai.yaml", root / "public_surface_registry.yaml"])
        active.extend(root / "fixtures/_internal" / helper for helper in SHARED_HELPERS)
    forbidden = "/" + "Users/"
    return [str(path) for path in active if forbidden in path.read_text(encoding="utf-8", errors="strict")]


def main() -> int:
    errors: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}

    for skill in SKILL_NAMES:
        skill_file = FAMILY / skill / "SKILL.md"
        try:
            metadata = _frontmatter(skill_file)
            if metadata.get("name") != skill or not metadata.get("description"):
                raise ValueError(f"expected name={skill!r} and non-empty description")
        except Exception as exc:
            errors.append({"check": "frontmatter", "skill": skill, "detail": str(exc)})
    checks["frontmatter"] = {"skills_checked": len(SKILL_NAMES)}

    expected_policies = {
        FAMILY / "scientific-data-analysis": "true",
        FAMILY / "scientific-data-astro": "true",
        FAMILY / "scientific-data-documents": "true",
        FAMILY / "scientific-data-notebooks": "true",
        FAMILY / "scientific-data-maintainer": "false",
    }
    for root, expected in expected_policies.items():
        agents = root / "agents/openai.yaml"
        actual = _simple_yaml_value(agents, "allow_implicit_invocation") if agents.is_file() else None
        if actual != expected:
            errors.append({"check": "agents_policy", "skill": root.name, "expected": expected, "actual": actual})
    checks["agents_policy"] = {
        "implicit_domain_skills": sorted(root.name for root, value in expected_policies.items() if value == "true"),
        "maintainer_implicit": False,
    }

    canonical_paths: dict[str, str] = {}
    registry_releases: dict[str, str | None] = {}
    registry_entries: list[dict[str, str]] = []
    fingerprints: set[str] = set()
    for skill in SKILL_NAMES:
        try:
            registry_stub = FAMILY / skill / "public_surface_registry.yaml"
            release = _simple_yaml_value(registry_stub, "release")
            registry_releases[skill] = release
            if release != "v2.8":
                raise ValueError(f"registry stub release must be v2.8, found {release!r}")
            canonical, chain, entries = _resolve_registry(registry_stub)
            ids = [item.get("id", "") for item in entries]
            if len(entries) != EXPECTED_CAPABILITIES or len(set(ids)) != EXPECTED_CAPABILITIES or "" in ids:
                raise ValueError(f"expected 61 unique non-empty IDs, got rows={len(entries)} unique={len(set(ids))}")
            required = {"id", "label", "script", "visible_block", "kind"}
            for item in entries:
                missing = sorted(required - set(item))
                if missing:
                    raise ValueError(f"registry {item.get('id')} misses fields: {', '.join(missing)}")
            fingerprint = hashlib.sha256(canonical.read_bytes()).hexdigest()
            fingerprints.add(fingerprint)
            canonical_paths[skill] = str(canonical)
            if not registry_entries:
                registry_entries = entries
        except Exception as exc:
            errors.append({"check": "registry", "skill": skill, "detail": str(exc)})
    if len(fingerprints) != 1:
        errors.append({"check": "registry_fingerprint", "detail": f"expected one canonical fingerprint, found {len(fingerprints)}"})
    checks["registry"] = {
        "rows": len(registry_entries),
        "canonical_paths": canonical_paths,
        "fingerprints": len(fingerprints),
        "stub_releases": registry_releases,
    }

    registry_by_id = {item["id"]: item for item in registry_entries if item.get("id")}
    maintainer_ids = {item["id"] for item in registry_entries if item.get("kind") == "maintainer_only"}
    if maintainer_ids != EXPECTED_MAINTAINER_IDS:
        errors.append({"check": "maintainer_exposure", "expected": sorted(EXPECTED_MAINTAINER_IDS), "actual": sorted(maintainer_ids)})
    checks["maintainer_exposure"] = {"maintainer_only_ids": sorted(maintainer_ids)}

    module_rows: list[dict[str, Any]] = []
    try:
        map_path, module_rows = _resolve_module_map(MOTHER / "references/v2-3-mother-router-module-map.json")
        expected_map_path = (MAINTAINER / ".cache/archived_references/v2-3-mother-router-module-map.json").resolve()
        if map_path != expected_map_path:
            raise ValueError(f"module map resolved to {map_path}, expected {expected_map_path}")
        module_ids = [str(item.get("capability_id", "")) for item in module_rows]
        if len(module_rows) != EXPECTED_CAPABILITIES or len(set(module_ids)) != EXPECTED_CAPABILITIES:
            raise ValueError(f"expected 61 unique module-map rows, got rows={len(module_rows)} unique={len(set(module_ids))}")
        if set(module_ids) != set(registry_by_id):
            raise ValueError("module-map IDs differ from canonical registry IDs")
        for item in module_rows:
            capability_id = str(item["capability_id"])
            missing = [field for field in MODULE_FIELDS if not item.get(field)]
            if missing:
                raise ValueError(f"module-map {capability_id} misses fields: {', '.join(missing)}")
            child = FAMILY / str(item["child_skill_path"])
            script = str(item.get("script_path_historico", ""))
            if not (MOTHER / script).is_file():
                raise ValueError(f"mother compatibility path missing for {capability_id}: {script}")
            if not (child / script).is_file():
                raise ValueError(f"owning-root script missing for {capability_id}: {child / script}")
            if registry_by_id[capability_id].get("script") != script:
                raise ValueError(f"registry/module-map script mismatch for {capability_id}")
        checks["module_map"] = {"rows": len(module_rows), "resolved_path": str(map_path)}
    except Exception as exc:
        errors.append({"check": "module_map", "detail": str(exc)})

    try:
        probe = _router_probe()
        expected_map_path = str((MAINTAINER / ".cache/archived_references/v2-3-mother-router-module-map.json").resolve())
        if probe.get("resolved_path") != expected_map_path:
            raise ValueError(f"router resolved path mismatch: {probe.get('resolved_path')}")
        map_by_id = {str(item["capability_id"]): item for item in module_rows}
        mismatches: list[dict[str, Any]] = []
        for capability_id, expected in map_by_id.items():
            actual = probe.get("metadata", {}).get(capability_id, {})
            differing = {field: {"expected": expected.get(field), "actual": actual.get(field)} for field in MODULE_FIELDS if expected.get(field) != actual.get(field)}
            if differing:
                mismatches.append({"capability_id": capability_id, "fields": differing})
            if actual.get("wrapper_status") in {"module_map_error", "module_map_missing", "module_map_missing_known_capability", "compact_stub_fallback"}:
                mismatches.append({"capability_id": capability_id, "fields": {"wrapper_status": actual.get("wrapper_status")}})
        rejected = probe.get("rejected_explain") or {}
        if any(rejected.get(field) is None for field in MODULE_FIELDS):
            mismatches.append({"capability_id": "rejected_explain", "fields": {field: rejected.get(field) for field in MODULE_FIELDS}})
        if mismatches:
            raise ValueError(f"router metadata mismatches: {json.dumps(mismatches, sort_keys=True)}")
        checks["router_metadata"] = {"rows": len(map_by_id), "rejected_explain_enriched": True}
    except Exception as exc:
        errors.append({"check": "router_metadata", "detail": str(exc)})

    broken_probe = _router_broken_map_probe()
    broken_status = str((broken_probe.get("payload") or {}).get("status", "")).lower()
    if (
        broken_probe["returncode"] == 0
        or broken_status not in {"fail", "failed", "roto"}
        or "traceback" in (broken_probe["stdout"] + broken_probe["stderr"]).lower()
    ):
        errors.append(
            {
                "check": "router_broken_map_fail_closed",
                "returncode": broken_probe["returncode"],
                "status": broken_status,
                "stderr": broken_probe["stderr"],
            }
        )
    checks["router_broken_map_fail_closed"] = {"returncode": broken_probe["returncode"], "status": broken_status}

    for helper_root in (FAMILY / skill for skill in SKILL_NAMES):
        try:
            _exercise_registry_helper(helper_root / "fixtures/_internal/public_surface_registry.py")
        except Exception as exc:
            errors.append({"check": "registry_helper_invariants", "skill": helper_root.name, "detail": str(exc)})
    checks["registry_helper_invariants"] = {"skills_checked": SKILL_NAMES, "cycle": "rejected", "max_depth": "enforced", "out_of_family": "rejected"}

    try:
        helper_hashes = _shared_helper_hashes()
        mismatched_helpers = {
            helper: values
            for helper, values in helper_hashes.items()
            if len(set(values.values())) != 1
        }
        if mismatched_helpers:
            raise ValueError(f"shared helper hashes differ across roots: {json.dumps(mismatched_helpers, sort_keys=True)}")
        checks["shared_helper_hashes"] = {
            helper: next(iter(values.values())) for helper, values in helper_hashes.items()
        }
    except Exception as exc:
        errors.append({"check": "shared_helper_hashes", "detail": str(exc)})

    try:
        contract_probe = _common_contract_probe()
        if contract_probe.get("failures"):
            raise ValueError("; ".join(str(item) for item in contract_probe["failures"]))
        checks["common_contract"] = {key: value for key, value in contract_probe.items() if key != "failures"}
    except Exception as exc:
        errors.append({"check": "common_contract", "detail": str(exc)})

    broken_symlinks: list[str] = []
    for skill in SKILL_NAMES:
        broken_symlinks.extend(_broken_symlinks(FAMILY / skill))
    if broken_symlinks:
        errors.append({"check": "symlinks", "broken": broken_symlinks})
    checks["symlinks"] = {"broken": len(broken_symlinks)}

    hardcoded = _hardcoded_active_paths()
    if hardcoded:
        errors.append({"check": "hardcoded_active_paths", "paths": hardcoded})
    checks["hardcoded_active_paths"] = {"violations": hardcoded}

    status = "PASS" if not errors else "FAIL"
    payload = {
        "tool": "audit_v2_8_family_integrity_regression",
        "release": "v2.8",
        "status": status,
        "checks": checks,
        "errors": errors,
        "warnings": [],
        "original_modified": False,
        "gate_scope": "current family integrity invariants; historical snapshot regressions are not release blockers",
        "next_actions": [] if not errors else [{"label": "Correct the failing v2.8 invariant and rerun this gate."}],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

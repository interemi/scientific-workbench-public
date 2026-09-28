"""Earliest-possible output/input collision guard for astro public CLIs.

The public wrappers call this module before dispatching to their heavier fixture
bodies.  It deliberately uses only the standard library and never writes an
artifact: unsafe invocations receive one stdout JSON envelope and return code 2.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from _internal.path_safety import (
    canonical_path,
    find_output_input_collisions,
    path_is_within,
    paths_alias,
)
from _internal.provenance_utils import standard_tool_payload


@dataclass
class PathPlan:
    inputs: list[tuple[str, str | Path | None]] = field(default_factory=list)
    outputs: list[tuple[str, str | Path | None]] = field(default_factory=list)
    output_dirs: list[tuple[str, str | Path | None]] = field(default_factory=list)
    forced_collisions: list[dict[str, str]] = field(default_factory=list)
    isolate_output_dirs_from_file_parents: bool = False

    def input(self, label: str, value: str | Path | None) -> None:
        if value is not None and not _looks_like_url(value):
            self.inputs.append((label, value))

    def input_many(self, label: str, values: Iterable[str | Path]) -> None:
        for index, value in enumerate(values, start=1):
            self.input(f"{label}[{index}]", value)

    def output(self, label: str, value: str | Path | None) -> None:
        if value is not None:
            self.outputs.append((label, value))

    def output_dir(self, label: str, value: str | Path | None) -> None:
        if value is not None:
            self.output_dirs.append((label, value))
            self.outputs.append((label, value))


COMMON_BOOLEAN_OPTIONS = {
    "--allow-unregistered-stack",
    "--clean-derived",
    "--compile-report",
    "--continue-run",
    "--crpix-center",
    "--dry-run",
    "--execute-notebook",
    "--force",
    "--force-simple-fallback",
    "--include-color-term",
    "--no-plots",
    "--no-same-exptime",
    "--no-same-object",
    "--no-stacks",
    "--no-validate",
    "--no-verify",
    "--normalize",
    "--optimal-extraction",
    "--overwrite",
    "--probe",
    "--require-apt",
    "--require-stilts",
    "--same-exptime",
    "--same-object",
    "--scale-dark",
    "--skip-reduced-fits",
    "--skip-report-project",
    "--skip-solved",
    "--skip-systematic-grid",
    "--trust-notebook-code",
    "--fetch-official-samples",
    "--fetch-official-sidecars",
    "--concise",
    "--rm-nan",
    "--use-sextractor",
    "--ucd",
    "--validate",
    "--no-ucd",
}


def _looks_like_url(value: str | Path) -> bool:
    text = str(value).strip().lower()
    return "://" in text or text.startswith("data:")


def _add_transitive_json_paths(plan: PathPlan, label: str, value: str | Path | None) -> None:
    if value is None:
        return
    source = Path(value).expanduser()
    try:
        if not source.is_file() or source.stat().st_size > 20 * 1024 * 1024:
            return
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    stack: list[object] = [payload]
    discovered = 0
    while stack and discovered < 10_000:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
            continue
        if isinstance(item, list):
            stack.extend(item)
            continue
        if not isinstance(item, str) or _looks_like_url(item):
            continue
        text = item.strip()
        if not text or not (
            text.startswith(("/", "~"))
            or "/" in text
            or Path(text).suffix.lower() in {".json", ".csv", ".fits", ".fit", ".txt", ".log", ".dat", ".ipynb"}
        ):
            continue
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = source.parent / candidate
        try:
            exists = candidate.exists()
        except OSError:
            exists = False
        if exists:
            discovered += 1
            plan.input(f"{label} referenced path[{discovered}]", candidate)


def _option_values(argv: Sequence[str], flag: str) -> list[str]:
    values: list[str] = []
    index = 0
    prefix = flag + "="
    while index < len(argv):
        token = argv[index]
        if token.startswith(prefix):
            values.append(token[len(prefix) :])
        elif token == flag and index + 1 < len(argv):
            values.append(argv[index + 1])
            index += 1
        index += 1
    return values


def _option(argv: Sequence[str], flag: str) -> str | None:
    values = _option_values(argv, flag)
    return values[-1] if values else None


def _positionals(
    argv: Sequence[str],
    *,
    extra_boolean: Iterable[str] = (),
    option_arities: dict[str, int | str] | None = None,
) -> list[str]:
    booleans = COMMON_BOOLEAN_OPTIONS | set(extra_boolean)
    arities = option_arities or {}
    values: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            values.extend(argv[index + 1 :])
            break
        if not token.startswith("-") or token == "-":
            values.append(token)
            index += 1
            continue
        if "=" in token:
            index += 1
            continue
        if token in booleans:
            index += 1
            continue
        arity = arities.get(token, 1)
        if arity in {"+", "*"}:
            index += 1
            while index < len(argv) and not argv[index].startswith("-"):
                index += 1
            continue
        index += 1 + int(arity)
    return values


def _common_outputs(plan: PathPlan, argv: Sequence[str]) -> None:
    for flag in (
        "--summary-json",
        "--output-json",
        "--output-csv",
        "--output",
        "--manifest-json",
        "--report-md",
        "--preview",
        "--comparison-png",
        "--audit-json",
        "--coefficients-csv",
        "--residual-csv",
        "--residual-plot",
        "--output-table",
        "--output-path",
        "--output-zip",
        "--trace-plot",
        "--plot",
        "--html-report",
    ):
        plan.output(flag, _option(argv, flag))
    for flag in ("--output-dir", "--log-dir", "--extract-all-orders-dir"):
        plan.output_dir(flag, _option(argv, flag))


def _normalize_output_aliases(
    plan: PathPlan,
    primary_flag: str,
    alias_flag: str,
    *,
    reject_distinct: bool,
) -> None:
    primary = next((value for label, value in plan.outputs if label == primary_flag), None)
    alias = next((value for label, value in plan.outputs if label == alias_flag), None)
    if primary is None or alias is None:
        return
    if paths_alias(primary, alias):
        removed = False
        normalized: list[tuple[str, str | Path | None]] = []
        for label, value in plan.outputs:
            if label == alias_flag and not removed:
                removed = True
                continue
            normalized.append((label, value))
        plan.outputs = normalized
        return
    if reject_distinct:
        plan.forced_collisions.append(
            {
                "flag": primary_flag,
                "input": alias_flag,
                "input_path": str(canonical_path(alias)),
                "output_path": str(canonical_path(primary)),
                "collision_kind": "ambiguous_fallback_aliases",
            }
        )


def _reserve_output_subtrees(
    plan: PathPlan,
    reserved: Iterable[tuple[str, str | Path]],
) -> None:
    """Reject user-selected artifacts inside tool-owned internal workspaces."""
    requested = list(plan.outputs)
    for output_label, output_value in requested:
        if output_value is None or output_label in {"--output-dir", "--log-dir", "--extract-all-orders-dir"}:
            continue
        for reserved_label, reserved_root in reserved:
            if not path_is_within(output_value, reserved_root):
                continue
            plan.forced_collisions.append(
                {
                    "flag": output_label,
                    "input": reserved_label,
                    "input_path": str(canonical_path(reserved_root)),
                    "output_path": str(canonical_path(output_value)),
                    "collision_kind": "reserved_output_subtree",
                }
            )


def _plan_external_preflight(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    for flag in (
        "--java-command",
        "--stilts-command",
        "--stilts-jar",
        "--topcat-command",
        "--topcat-jar",
        "--apt-command",
        "--apt-preferences",
    ):
        plan.input(flag, _option(argv, flag))
    _add_external_environment_inputs(plan)
    _common_outputs(plan, argv)
    return plan


def _add_external_environment_inputs(plan: PathPlan) -> None:
    command_variables = {
        "JAVA_COMMAND",
        "STILTS_COMMAND",
        "TOPCAT_COMMAND",
        "APT_COMMAND",
    }
    for variable in (
        "JAVA_COMMAND",
        "STILTS_COMMAND",
        "STILTS_JAR",
        "TOPCAT_COMMAND",
        "TOPCAT_JAR",
        "APT_COMMAND",
        "APT_PREFERENCES",
    ):
        raw = os.environ.get(variable, "").strip()
        if not raw:
            continue
        value = raw
        # Match the backend resolver: an existing path is one executable even
        # when its unquoted name contains spaces.
        if variable in command_variables and not Path(raw).expanduser().exists():
            try:
                tokens = shlex.split(raw)
            except ValueError:
                tokens = [raw]
            if not tokens:
                continue
            executable = shutil.which(tokens[0])
            value = executable or tokens[0]
        candidate = Path(value).expanduser()
        if candidate.exists():
            plan.input(f"env:{variable}", candidate)
    for command_name in ("java", "stilts", "topcat", "APT.csh", "APT.bat", "AperturePhotometryTool"):
        resolved = shutil.which(command_name)
        if resolved:
            plan.input(f"PATH:{command_name}", resolved)
    for label, candidate in (
        ("default APT preferences", Path.home() / ".AperturePhotometryTool" / "APT.pref"),
        (
            "default APT application JAR",
            Path("/Applications/Aperture Photometry Tool.app/Contents/Resources/Java/APT.jar"),
        ),
    ):
        if candidate.exists():
            plan.input(label, candidate)


def _plan_inspect_fits(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    if positional:
        plan.input("path", positional[0])
    _common_outputs(plan, argv)
    return plan


def _plan_fits_rgb(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    plan.input("--input-root", _option(argv, "--input-root"))
    plan.output_dir("--output-dir", _option(argv, "--output-dir"))
    plan.output("--summary-json", _option(argv, "--summary-json"))
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        for label, name in (
            ("fixed FITS inventory", "fits_inventory.csv"),
            ("fixed RGB group summary", "rgb_group_summary.csv"),
            ("fixed run summary", "run_summary.json"),
            ("fixed manifest", "manifest.json"),
        ):
            plan.output(label, output_root / name)
    return plan


def _plan_rgb_export(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    if positional:
        plan.input("input_png", positional[0])
    if len(positional) > 1:
        plan.output("output_fits", positional[1])
        output_fits = Path(positional[1]).expanduser()
        if not _option(argv, "--manifest-json"):
            plan.output("default manifest", output_fits.with_suffix(".manifest.json"))
        if _option(argv, "--previous-png") and not _option(argv, "--comparison-png"):
            plan.output(
                "default comparison",
                output_fits.with_name(output_fits.stem + "_before_after.png"),
            )
    plan.input("--previous-png", _option(argv, "--previous-png"))
    _common_outputs(plan, argv)
    return plan


def _plan_stilts(argv: Sequence[str]) -> PathPlan:
    plan = _plan_external_preflight(argv)
    positional = _positionals(argv, extra_boolean={"--report-md"})
    if not positional:
        return plan
    command = positional[0]
    operands = positional[1:]
    if command in {"convert", "filter"} and len(operands) >= 2:
        plan.input("input", operands[0])
        plan.output("output", operands[1])
    elif command == "crossmatch-sky" and len(operands) >= 3:
        plan.input("left", operands[0])
        plan.input("right", operands[1])
        plan.output("output", operands[2])
    elif command in {"votlint", "lint-votable"} and len(operands) >= 2:
        plan.input("input", operands[0])
        plan.output("report", operands[1])
    log_dir = _option(argv, "--log-dir")
    if log_dir:
        for label, name in (
            ("fixed STILTS command log", "stilts_command.sh"),
            ("fixed STILTS stdout log", "stilts_stdout.txt"),
            ("fixed STILTS stderr log", "stilts_stderr.txt"),
        ):
            plan.output(label, Path(log_dir).expanduser() / name)
    return plan


def _plan_astrometry(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv)
    command = positional[0] if positional else None
    local_input_commands = {
        "preflight",
        "solve-web",
        "solve-local",
        "solve-local-best-effort",
        "stack-peers",
        "solve-web-best-effort",
        "verify-existing-wcs",
    }
    if command in local_input_commands and len(positional) > 1:
        plan.input("path", positional[1])
    for flag in ("--backend-config", "--solve-field-bin", "--verify-wcs"):
        plan.input(flag, _option(argv, flag))
    if not _option(argv, "--solve-field-bin"):
        solve_field = shutil.which("solve-field")
        if solve_field:
            plan.input("PATH:solve-field", solve_field)
    plan.input_many("--index-dir", _option_values(argv, "--index-dir"))
    plan.input_many("--index-file", _option_values(argv, "--index-file"))
    if command in {"stack-peers", "solve-local-best-effort", "solve-web-best-effort"} and len(positional) > 1:
        seed = Path(positional[1]).expanduser()
        match = re.match(r"^(.*)_([0-9]+)$", seed.stem)
        if match:
            plan.input_many("implicit peer", sorted(seed.parent.glob(f"{match.group(1)}_*.fits")))
    if command in {"solve-web", "solve-web-url", "solve-web-best-effort", "auth-check"} and not _option(argv, "--api-key"):
        if not os.environ.get("ASTROMETRY_NET_API_KEY", "").strip():
            key_candidates: list[Path] = []
            env_key_file = os.environ.get("ASTROMETRY_NET_API_KEY_FILE", "").strip()
            if env_key_file:
                key_candidates.append(Path(env_key_file).expanduser())
            key_candidates.extend(
                [
                    Path("~/.codex/secrets/astrometry_net_api_key").expanduser(),
                    Path("~/.codex/credentials/astrometry_net_api_key").expanduser(),
                    Path("~/.config/codex/astrometry_net_api_key").expanduser(),
                ]
            )
            plan.input_many("implicit credential file", [path for path in key_candidates if path.exists()])
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            ("internal existing-WCS verification", output_root / "existing_wcs_verification"),
            ("internal direct solve", output_root / "direct_solve"),
            ("internal aggressive solve", output_root / "direct_aggressive"),
            ("internal nearest stack solve", output_root / "stack_solve_nearest"),
            ("internal forward stack solve", output_root / "stack_solve_forward_window"),
            ("internal backward stack solve", output_root / "stack_solve_backward_window"),
        ]
        _reserve_output_subtrees(plan, reserved)
        for label, name in (
            ("fixed existing-WCS quicklook", "existing_wcs_quicklook.png"),
            ("fixed WCS quicklook", "qa_wcs_quicklook.png"),
            ("fixed compact visual review", "compact_visual_review.png"),
            ("fixed solve stdout", "solve_field.stdout.txt"),
            ("fixed solve stderr", "solve_field.stderr.txt"),
        ):
            plan.output(label, output_root / name)
    return plan


def _plan_radial_velocity(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    if not positional:
        return plan
    command = positional[0]
    operands = positional[1:]
    if command == "inspect" and operands:
        plan.input("input_path", operands[0])
    elif command == "scaffold-session" and operands:
        plan.output_dir("output_dir", operands[0])
        plan.input_many("inputs", operands[1:])
        plan.isolate_output_dirs_from_file_parents = True
    elif command in {"build-report", "validate-manifest"} and operands:
        plan.input("session_manifest", operands[0])
        _add_transitive_json_paths(plan, "session_manifest", operands[0])
    elif command == "package" and operands:
        plan.input("session_dir", operands[0])
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if command == "scaffold-session" and operands:
        output_dir = operands[0]
    if output_dir:
        output_root = Path(output_dir).expanduser()
        for label, name in (
            ("fixed session manifest", "session_manifest.json"),
            ("fixed session notes", "notes.md"),
            ("fixed session README", "README.md"),
            ("fixed RV report markdown", "rv_analysis_report.md"),
            ("fixed RV report TeX", "rv_analysis_report.tex"),
            ("fixed RV report PDF", "rv_analysis_report.pdf"),
            ("fixed RV report summary", "summary.json"),
        ):
            plan.output(label, output_root / name)
    output_zip = _option(argv, "--output-zip")
    if command == "package" and output_zip:
        zip_path = Path(output_zip).expanduser()
        plan.output("fixed package README sidecar", zip_path.with_suffix(".README.md"))
        plan.output("fixed package index sidecar", zip_path.with_suffix(".index.json"))
    return plan


def _plan_single_tree_input(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    if positional:
        plan.input("root", positional[-1])
    _common_outputs(plan, argv)
    return plan


def _plan_echelle(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv, extra_boolean={"--report-md"})
    if positional:
        plan.input("input", positional[0])
    plan.output_dir("--output-dir", _option(argv, "--output-dir"))
    plan.output("--summary-json", _option(argv, "--summary-json"))
    plan.output("--manifest-json", _option(argv, "--manifest-json"))
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        for label, name in (
            ("fixed files inventory", "files_inventory.csv"),
            ("fixed orders inventory", "orders_inventory.csv"),
            ("fixed report", "report.md"),
        ):
            plan.output(label, output_root / name)
        if not _option(argv, "--summary-json"):
            plan.output("default summary", output_root / "summary.json")
    return plan


def _plan_fxcor(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv)
    command = positional[0] if positional else None
    if len(positional) > 1:
        plan.input("practice_root" if command == "prepare-session" else "workspace", positional[1])
    plan.input("--manual-csv", _option(argv, "--manual-csv"))
    for command_name in ("cl", "mkiraf"):
        resolved = shutil.which(command_name)
        if resolved:
            plan.input(f"PATH:{command_name}", resolved)
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            ("internal FXCOR data workspace", output_root / "data"),
            ("internal FXCOR logs workspace", output_root / "logs"),
            ("internal FXCOR parsed workspace", output_root / "parsed"),
            ("internal FXCOR scripts workspace", output_root / "scripts"),
            ("internal IRAF parameter workspace", output_root / "uparm"),
        ]
        _reserve_output_subtrees(plan, reserved)
        for label, name in (
            ("fixed FXCOR configuration", "fxcor_cases.json"),
            ("fixed manual overrides", "manual_overrides.csv"),
            ("fixed IRAF login", "login.cl"),
        ):
            plan.output(label, output_root / name)
    return plan


def _plan_legacy_rv(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv)
    if positional and positional[0] == "analyze":
        positional = positional[1:]
    plan.input_many("inputs", positional)
    for index, value in enumerate(positional, start=1):
        _add_transitive_json_paths(plan, f"inputs[{index}]", value)
    for flag in ("--fits-root", "--calibration-csv"):
        plan.input(flag, _option(argv, flag))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        _reserve_output_subtrees(plan, [("internal RV figures workspace", output_root / "figures")])
        for label, name in (
            ("fixed all-order RV table", "rv_orders_all.csv"),
            ("fixed filtered RV table", "rv_orders_filtered.csv"),
            ("fixed RV summary table", "rv_summary.csv"),
            ("fixed v sin i summary", "vsini_summary.csv"),
            ("fixed markdown summary", "summary.md"),
        ):
            plan.output(label, output_root / name)
    return plan


def _plan_sb2(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv)
    if positional and positional[0] in {"fit", "fit-orders"}:
        positional = positional[1:]
    plan.input_many("inputs", positional)
    plan.input_many("--fxcor-csv", _option_values(argv, "--fxcor-csv"))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        _reserve_output_subtrees(plan, [("internal SB2 figures workspace", output_root / "figures")])
        plan.output("fixed SB2 orders table", output_root / "sb2_double_gaussian_orders.csv")
        plan.output("fixed SB2 markdown summary", output_root / "summary.md")
    return plan


def _plan_li(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(
        argv,
        option_arities={"--continuum-window": 2, "--integration-window": 2},
    )
    if positional and positional[0] == "measure":
        positional = positional[1:]
    if positional:
        plan.input("fits_path", positional[0])
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        _reserve_output_subtrees(plan, [("internal lithium figures workspace", output_root / "figures")])
        plan.output("fixed lithium plot", output_root / "figures" / "li6708_equivalent_width.png")
        plan.output("fixed lithium table", output_root / "li6708_summary.csv")
        plan.output("fixed lithium report", output_root / "li6708_summary.md")
        if not _option(argv, "--summary-json"):
            plan.output("default lithium summary", output_root / "li6708_summary.json")
    return plan


def _plan_external_reference(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    for flag in (
        "--rv-summary",
        "--gzleo-fits",
        "--li-summary",
        "--istarmod-summary",
    ):
        value = _option(argv, flag)
        plan.input(flag, value)
        _add_transitive_json_paths(plan, flag, value)
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        plan.output("fixed external-reference report", output_root / "external_reference_check.md")
        if not _option(argv, "--summary-json"):
            plan.output("default external-reference summary", output_root / "external_reference_check.json")
    return plan


def _plan_istarmod(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv)
    command = positional[0] if positional else None
    if len(positional) > 1:
        plan.input("path", positional[1])
    plan.input("--sm-file", _option(argv, "--sm-file"))
    plan.input("--python-bin", _option(argv, "--python-bin"))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir and command == "prepare-copy":
        output_root = Path(output_dir).expanduser()
        _reserve_output_subtrees(plan, [("prepared iSTARMOD copy", output_root)])
        plan.output("fixed iSTARMOD copy manifest", output_root / ".istarmod_prepare.json")
    return plan


def _plan_legacy_report(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    command = positional[0] if positional else None
    if command == "scaffold" and len(positional) > 1:
        plan.output_dir("output_dir", positional[1])
    elif command == "populate" and len(positional) > 1:
        plan.input("project_dir", positional[1])
        for flag in (
            "--envcheck",
            "--inventory-summary",
            "--rv-summary",
            "--istarmod-summary",
            "--external-reference-summary",
        ):
            value = _option(argv, flag)
            plan.input(flag, value)
            _add_transitive_json_paths(plan, flag, value)
        for flag in ("--fxcor-summary", "--li-summary"):
            values = _option_values(argv, flag)
            plan.input_many(flag, values)
            for index, value in enumerate(values, start=1):
                _add_transitive_json_paths(plan, f"{flag}[{index}]", value)
    _common_outputs(plan, argv)
    return plan


def _plan_photometric(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    if positional:
        plan.input("input_table", positional[0])
    _common_outputs(plan, argv)
    _normalize_output_aliases(plan, "--summary-json", "--output-json", reject_distinct=False)
    return plan


def _plan_noise_budget(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    _common_outputs(plan, argv)
    _normalize_output_aliases(plan, "--summary-json", "--output-json", reject_distinct=True)
    return plan


def _plan_apt(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    plan.input("--apt-command", _option(argv, "--apt-command"))
    plan.input("--apt-preferences", _option(argv, "--apt-preferences"))
    _add_external_environment_inputs(plan)
    positional = _positionals(argv)
    command = positional[0] if positional else None
    operands = positional[1:]
    if command == "prepare-source-list" and len(operands) >= 2:
        plan.input("input_table", operands[0])
        plan.output("output_source_list", operands[1])
    elif command == "run-batch":
        plan.input("--image", _option(argv, "--image"))
        plan.input("--source-list", _option(argv, "--source-list"))
    elif command == "parse-results" and len(operands) >= 2:
        plan.input("input_table", operands[0])
        plan.output("output_table", operands[1])
    _common_outputs(plan, argv)
    log_dir = _option(argv, "--log-dir")
    if log_dir:
        for label, name in (
            ("fixed APT command log", "apt_command.sh"),
            ("fixed APT stdout log", "apt_stdout.txt"),
            ("fixed APT stderr log", "apt_stderr.txt"),
        ):
            plan.output(label, Path(log_dir).expanduser() / name)
    return plan


def _plan_teareduce_router(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    plan.input_many("inputs", _positionals(argv))
    plan.output("--summary-json", _option(argv, "--summary-json"))
    return plan


def _plan_spectra_coursework(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv, option_arities={"--line-window": 3})
    plan.input_many("spectra", positional)
    plan.input("--notebook", _option(argv, "--notebook"))
    plan.input_many("--stage-extra", _option_values(argv, "--stage-extra"))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            ("internal spectrum analysis workspace", output_root / "spectra_analysis"),
            ("internal report project", output_root / "report_project"),
            ("internal notebook workspace", output_root / "notebook"),
        ]
        _reserve_output_subtrees(plan, reserved)
        for label, path in (
            ("fixed spectrum inventory", output_root / "spectra_analysis" / "spectrum_inventory.csv"),
            ("fixed raw spectrum overlay", output_root / "spectra_analysis" / "overlay_raw.png"),
            ("fixed normalized spectrum overlay", output_root / "spectra_analysis" / "overlay_normalized.png"),
            ("fixed spectrum report", output_root / "spectra_analysis" / "report.md"),
            ("fixed coursework bundle report", output_root / "coursework_bundle_report.md"),
        ):
            plan.output(label, path)
        if not _option(argv, "--summary-json"):
            plan.output("default coursework summary", output_root / "summary.json")
    return plan


def _plan_reduce_ccd(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    for flag in (
        "--bias",
        "--dark",
        "--flat",
        "--science",
        "--master-bias",
        "--master-dark",
        "--master-flat",
    ):
        values = _option_values(argv, flag)
        plan.input_many(flag, values)
    output_dir = _option(argv, "--output-dir")
    _common_outputs(plan, argv)
    if output_dir:
        output_root = Path(output_dir).expanduser()
        if _option_values(argv, "--bias") and not _option(argv, "--master-bias"):
            plan.output("derived master bias", output_root / "master_bias.fits")
        if _option_values(argv, "--dark") and not _option(argv, "--master-dark"):
            plan.output("derived master dark", output_root / "master_dark.fits")
        if _option_values(argv, "--flat") and not _option(argv, "--master-flat"):
            plan.output("derived master flat", output_root / "master_flat.fits")
        for science in _option_values(argv, "--science"):
            plan.output("derived reduced science", output_root / f"reduced_{Path(science).name}")
    return plan


def _plan_spectral(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv, option_arities={"--line-window": 2})
    if positional:
        plan.input("input", positional[0])
    plan.input("--calibration-table", _option(argv, "--calibration-table"))
    _common_outputs(plan, argv)
    all_orders_dir = _option(argv, "--extract-all-orders-dir")
    if all_orders_dir:
        _reserve_output_subtrees(
            plan,
            [("internal all-orders export workspace", Path(all_orders_dir).expanduser())],
        )
    return plan


def _plan_spectroscopy_pipeline(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv, option_arities={"--line-window": 2})
    plan.input_many("science", positional)
    basenames = [Path(value).name for value in positional]
    for duplicate in sorted({name for name in basenames if basenames.count(name) > 1}):
        plan.forced_collisions.append(
            {
                "flag": "science",
                "input": f"duplicate science basename:{duplicate}",
                "input_path": duplicate,
                "output_path": duplicate,
                "collision_kind": "duplicate_science_product_identity",
            }
        )
    for flag in (
        "--bias",
        "--dark",
        "--flat",
        "--arc",
        "--master-bias",
        "--master-dark",
        "--master-flat",
        "--calibration-table",
    ):
        plan.input_many(flag, _option_values(argv, flag))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            ("internal calibration workspace", output_root / "calibration"),
            ("internal products workspace", output_root / "products"),
            ("internal reports workspace", output_root / "reports"),
        ]
        _reserve_output_subtrees(plan, reserved)
        for label, path in (
            ("fixed reduction audit", output_root / "calibration" / "audit.json"),
            ("fixed reduction manifest", output_root / "calibration" / "manifest.json"),
            ("fixed science-products table", output_root / "reports" / "science_products.csv"),
            ("fixed pipeline report", output_root / "reports" / "report.md"),
        ):
            plan.output(label, path)
    return plan


def _plan_aperture_photometry(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv, option_arities={"--center": 2})
    if positional:
        plan.input("fits_path", positional[0])
    plan.input("--positions-file", _option(argv, "--positions-file"))
    _common_outputs(plan, argv)
    return plan


def _plan_ascii_spectrum(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    plan.input_many("inputs", _positionals(argv, option_arities={"--line-window": 3}))
    output_dir = _option(argv, "--output-dir")
    plan.output_dir("--output-dir", output_dir)
    plan.output("--summary-json", _option(argv, "--summary-json"))
    plan.output("--manifest-json", _option(argv, "--manifest-json"))
    if output_dir and not _option(argv, "--summary-json"):
        plan.output("default summary", Path(output_dir).expanduser() / "summary.json")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        for label, name in (
            ("fixed inventory", "spectrum_inventory.csv"),
            ("fixed raw overlay", "overlay_raw.png"),
            ("fixed normalized overlay", "overlay_normalized.png"),
            ("fixed report", "report.md"),
        ):
            plan.output(label, output_root / name)
    return plan


def _plan_exoplanet_timeseries(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    plan.input_many(
        "inputs",
        _positionals(
            argv,
            option_arities={"--target-center": 2, "--aperture-radii": "+"},
        ),
    )
    plan.input("--reference-frame", _option(argv, "--reference-frame"))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        _reserve_output_subtrees(
            plan,
            [("internal reduced-frame workspace", output_root / "reduced_frames")],
        )
        for label, name in (
            ("fixed source map", "source_map.png"),
            ("fixed light-curve plot", "light_curve.png"),
            ("fixed candidate diagnostics", "candidate_diagnostics.csv"),
            ("fixed radius scan", "radius_scan.csv"),
            ("fixed light curve", "light_curve.csv"),
            ("fixed report", "report.md"),
        ):
            plan.output(label, output_root / name)
        for _input_label, input_value in list(plan.inputs):
            if input_value is None:
                continue
            input_path = Path(input_value).expanduser()
            try:
                if input_path.is_file():
                    plan.output(
                        "derived reduced frame",
                        output_root / "reduced_frames" / f"reduced_{input_path.name}",
                    )
            except OSError:
                continue
    return plan


def _plan_astrometry_index_health(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    if positional:
        plan.input("index_dir", positional[0])
    plan.output("--summary-json", _option(argv, "--summary-json"))
    return plan


def _plan_astrometry_local_smoke(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    for flag in (
        "--backend-config",
        "--direct-fits",
        "--compact-fits",
        "--existing-wcs-fits",
        "--spectroscopy-fits",
    ):
        plan.input(flag, _option(argv, flag))
    plan.input_many("--index-dir", _option_values(argv, "--index-dir"))
    solve_field = shutil.which("solve-field")
    if solve_field:
        plan.input("PATH:solve-field", solve_field)
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            (f"internal {case_id} case", output_root / case_id)
            for case_id in ("direct", "compact", "existing_wcs", "spectroscopy")
        ]
        _reserve_output_subtrees(plan, reserved)
        for label, case_root in reserved:
            plan.output(f"{label} summary", Path(case_root) / "summary.json")
    return plan


def _plan_fits_quicklook(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv, option_arities={"--center": 2})
    if positional:
        plan.input("fits_path", positional[0])
    plan.input("--region-file", _option(argv, "--region-file"))
    plan.output("--output", _option(argv, "--output"))
    return plan


def _plan_teareduce_bridge(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    positional = _positionals(argv)
    if not positional:
        return plan
    command = positional[0]
    operands = positional[1:]
    if command == "statsummary" and operands:
        plan.input("input", operands[0])
    elif command == "imshow-fits" and operands:
        plan.input("input", operands[0])
        plan.output("--output", _option(argv, "--output"))
    elif command == "notebook-scan":
        plan.input_many("paths", operands)
    plan.output("--summary-json", _option(argv, "--summary-json"))
    plan.output("--manifest-json", _option(argv, "--manifest-json"))
    return plan


def _plan_teareduce_cookbook(argv: Sequence[str], default_notebook_name: str) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    plan.input("--notebook", _option(argv, "--notebook"))
    plan.input_many("--sample", _option_values(argv, "--sample"))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            ("internal copied-notebook workspace", output_root / "teareduce_copy"),
            ("internal official-input workspace", output_root / "official_inputs"),
        ]
        _reserve_output_subtrees(plan, reserved)
        if not _option(argv, "--report-md"):
            plan.output("default report", output_root / "report.md")
        notebook = _option(argv, "--notebook")
        notebook_name = Path(notebook).name if notebook else default_notebook_name
        if notebook_name.lower().endswith(".ipynb.txt"):
            notebook_name = notebook_name[:-4]
        plan.output("executed notebook copy", output_root / "teareduce_copy" / notebook_name)
        if not notebook:
            plan.output("downloaded official notebook", output_root / "official_inputs" / default_notebook_name)
    return plan


def _plan_teareduce_notebook_workflow(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    positional = _positionals(argv)
    if positional:
        plan.input("notebook", positional[0])
    plan.input_many("--sidecar", _option_values(argv, "--sidecar"))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            ("internal copied-notebook workspace", output_root / "teareduce_copy"),
            ("internal native comparison workspace", output_root / "native_stack"),
            ("internal sidecar workspace", output_root / "sidecars"),
        ]
        _reserve_output_subtrees(plan, reserved)
        if not _option(argv, "--report-md"):
            plan.output("default report", output_root / "report.md")
        if positional:
            notebook_name = Path(positional[0]).name
            if notebook_name.lower().endswith(".ipynb.txt"):
                notebook_name = notebook_name[:-4]
            plan.output("executed notebook copy", output_root / "teareduce_copy" / notebook_name)
    return plan


def _plan_teareduce_notebook_runner(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    plan.input_many("paths", _positionals(argv))
    plan.input_many("--stage-extra", _option_values(argv, "--stage-extra"))
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = canonical_path(output_dir)
        try:
            occupied = Path(output_dir).expanduser()
            output_conflict = occupied.is_symlink() or (
                occupied.exists() and (not occupied.is_dir() or any(occupied.iterdir()))
            )
        except OSError:
            output_conflict = True
        if output_conflict:
            plan.forced_collisions.append(
                {
                    "flag": "--output-dir",
                    "input": "pre-existing output content",
                    "input_path": str(output_root),
                    "output_path": str(output_root),
                    "collision_kind": "occupied_output_workspace",
                }
            )
        explicit_notebooks = [
            Path(value).expanduser()
            for value in _positionals(argv)
            if Path(value).expanduser().is_file()
        ]
        stems = [path.stem for path in explicit_notebooks]
        for duplicate in sorted({stem for stem in stems if stems.count(stem) > 1}):
            plan.forced_collisions.append(
                {
                    "flag": "paths",
                    "input": f"duplicate notebook basename:{duplicate}",
                    "input_path": duplicate,
                    "output_path": str(output_root / duplicate),
                    "collision_kind": "duplicate_notebook_output_workspace",
                }
            )
        for output_label, output_value in list(plan.outputs):
            if output_value is None or output_label == "--output-dir":
                continue
            candidate = canonical_path(output_value)
            if path_is_within(candidate, output_root) and candidate.parent != output_root:
                plan.forced_collisions.append(
                    {
                        "flag": output_label,
                        "input": "internal per-notebook workspace",
                        "input_path": str(output_root),
                        "output_path": str(candidate),
                        "collision_kind": "reserved_output_subtree",
                    }
                )
    return plan


def _plan_teareduce_healthcheck(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan()
    plan.input_many("paths", _positionals(argv))
    plan.output("--summary-json", _option(argv, "--summary-json"))
    plan.output("--manifest-json", _option(argv, "--manifest-json"))
    return plan


def _plan_teareduce_smoke(argv: Sequence[str]) -> PathPlan:
    plan = PathPlan(isolate_output_dirs_from_file_parents=True)
    search_roots = _option_values(argv, "--search-root")
    if not search_roots:
        search_roots = [
            str(path)
            for path in (Path.home() / "Desktop", Path.home() / "Documents")
            if path.exists()
        ]
    plan.input_many("--search-root", search_roots)
    for flag in ("--bias-notebook", "--flat-notebook", "--cr2-notebook", "--wavecal-notebook"):
        plan.input(flag, _option(argv, flag))
    for name in (
        "ftdz_45243.fits",
        "ftdz_45244.fits",
        "ftdz_45324.fits",
        "filter_NOT_49.txt",
        "49.txt",
        "filter_NOT_76.txt",
        "76.txt",
        "filter_NOT_78.txt",
        "78.txt",
    ):
        candidate = Path("/tmp") / name
        if candidate.exists():
            plan.input(f"implicit /tmp input:{name}", candidate)
    _common_outputs(plan, argv)
    output_dir = _option(argv, "--output-dir")
    if output_dir:
        output_root = Path(output_dir).expanduser()
        reserved = [
            (f"internal {route} route", output_root / route)
            for route in ("bias", "flat", "cr2images", "wavecal")
        ]
        _reserve_output_subtrees(plan, reserved)
        if not _option(argv, "--summary-json"):
            plan.output("default summary", output_root / "summary.json")
        for label, route_root in reserved:
            for name in ("summary.json", "report.md", "manifest.json"):
                plan.output(f"{label} {name}", Path(route_root) / name)
    return plan


PLANNERS = {
    "aperture_photometry.py": _plan_aperture_photometry,
    "ascii_spectrum_workbench.py": _plan_ascii_spectrum,
    "astrometry_index_healthcheck.py": _plan_astrometry_index_health,
    "astrometry_local_smoke_test.py": _plan_astrometry_local_smoke,
    "exoplanet_timeseries_workbench.py": _plan_exoplanet_timeseries,
    "fits_quicklook.py": _plan_fits_quicklook,
    "teareduce_bridge.py": _plan_teareduce_bridge,
    "teareduce_cookbook_cr2images_workflow.py": lambda argv: _plan_teareduce_cookbook(argv, "cr2images.ipynb"),
    "teareduce_cookbook_wavecal_workflow.py": lambda argv: _plan_teareduce_cookbook(argv, "wavecalib.ipynb"),
    "teareduce_flat_workflow.py": _plan_teareduce_notebook_workflow,
    "teareduce_master_bias_workflow.py": _plan_teareduce_notebook_workflow,
    "teareduce_notebook_runner.py": _plan_teareduce_notebook_runner,
    "teareduce_healthcheck.py": _plan_teareduce_healthcheck,
    "teareduce_smoke_test.py": _plan_teareduce_smoke,
    "external_astro_tools_preflight.py": _plan_external_preflight,
    "inspect_fits.py": _plan_inspect_fits,
    "fits_rgb_batch.py": _plan_fits_rgb,
    "rgb_visual_fits_export.py": _plan_rgb_export,
    "stilts_workbench.py": _plan_stilts,
    "astrometry_net_workbench.py": _plan_astrometry,
    "radial_velocity_workbench.py": _plan_radial_velocity,
    "legacy_spectroscopy_envcheck.py": _plan_single_tree_input,
    "echelle_multispec_inventory.py": _plan_echelle,
    "fxcor_iraf_workbench.py": _plan_fxcor,
    "legacy_rv_coursework_workbench.py": _plan_legacy_rv,
    "sb2_double_gaussian_workbench.py": _plan_sb2,
    "li6708_equivalent_width_workbench.py": _plan_li,
    "legacy_external_reference_check.py": _plan_external_reference,
    "istarmod_workbench.py": _plan_istarmod,
    "legacy_spectroscopy_report_builder.py": _plan_legacy_report,
    "photometric_solution.py": _plan_photometric,
    "photometry_noise_budget.py": _plan_noise_budget,
    "apt_workbench.py": _plan_apt,
    "teareduce_router.py": _plan_teareduce_router,
    "spectra_ascii_coursework_workbench.py": _plan_spectra_coursework,
    "reduce_ccd_batch.py": _plan_reduce_ccd,
    "spectral_workbench.py": _plan_spectral,
    "spectroscopy_pipeline_workbench.py": _plan_spectroscopy_pipeline,
}

TRUST_REQUIRED_NOTEBOOK_EXECUTORS = {
    "teareduce_cookbook_cr2images_workflow.py",
    "teareduce_cookbook_wavecal_workflow.py",
    "teareduce_flat_workflow.py",
    "teareduce_master_bias_workflow.py",
    "teareduce_notebook_runner.py",
    "teareduce_smoke_test.py",
}


def _output_output_collisions(
    outputs: Sequence[tuple[str, str | Path | None]],
) -> list[dict[str, str]]:
    collisions: list[dict[str, str]] = []
    for index, (left_label, left) in enumerate(outputs):
        if left is None:
            continue
        for right_label, right in outputs[index + 1 :]:
            if right is None or not paths_alias(left, right):
                continue
            collisions.append(
                {
                    "flag": left_label,
                    "input": right_label,
                    "input_path": str(canonical_path(right)),
                    "output_path": str(canonical_path(left)),
                    "collision_kind": "output_output_alias",
                }
            )
    return collisions


def _file_parent_collisions(plan: PathPlan) -> list[dict[str, str]]:
    if not plan.isolate_output_dirs_from_file_parents:
        return []
    collisions: list[dict[str, str]] = []
    for output_label, output_dir in plan.output_dirs:
        if output_dir is None:
            continue
        for input_label, input_value in plan.inputs:
            if input_value is None:
                continue
            input_path = Path(input_value).expanduser()
            try:
                if input_path.is_dir():
                    continue
            except OSError:
                pass
            parent = canonical_path(input_path).parent
            # A dedicated child directory next to a file input is the normal,
            # safe layout.  Block only reusing the input's own directory or an
            # ancestor that contains it; derived-file aliases are checked
            # separately against their concrete names.
            if not (
                paths_alias(output_dir, parent)
                or path_is_within(parent, output_dir)
            ):
                continue
            collisions.append(
                {
                    "flag": output_label,
                    "input": f"directory containing {input_label}",
                    "input_path": str(parent),
                    "output_path": str(canonical_path(output_dir)),
                    "collision_kind": "output_directory_overlaps_input_directory",
                }
            )
    return collisions


def _output_tree_contains_inputs(plan: PathPlan) -> list[dict[str, str]]:
    collisions: list[dict[str, str]] = []
    for output_label, output_dir in plan.output_dirs:
        if output_dir is None:
            continue
        for input_label, input_value in plan.inputs:
            if input_value is None or not path_is_within(input_value, output_dir):
                continue
            collisions.append(
                {
                    "flag": output_label,
                    "input": input_label,
                    "input_path": str(canonical_path(input_value)),
                    "output_path": str(canonical_path(output_dir)),
                    "collision_kind": "output_tree_contains_input",
                }
            )
    return collisions


def find_plan_collisions(plan: PathPlan) -> list[dict[str, str]]:
    collisions = list(plan.forced_collisions)
    collisions.extend(find_output_input_collisions(plan.inputs, plan.outputs))
    for item in collisions:
        item.setdefault("collision_kind", "output_input_alias_or_tree_overlap")
    collisions.extend(_output_output_collisions(plan.outputs))
    collisions.extend(_file_parent_collisions(plan))
    collisions.extend(_output_tree_contains_inputs(plan))
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in collisions:
        key = (
            item["flag"],
            item["input"],
            item["input_path"],
            item["output_path"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def blocked_payload(
    tool: str,
    collisions: Sequence[dict[str, str]],
    argv: Sequence[str] = (),
) -> dict:
    message = "Unsafe output/input path collision blocked before execution."
    finding = (
        "No tool body, dependency bootstrap, output emitter, directory creation, "
        "or artifact write was allowed to run."
    )
    payload = standard_tool_payload(
        tool,
        status="blocked",
        notes=[
            "Choose output, summary, manifest, preview, report, and log paths outside protected inputs."
        ],
        artifacts={},
        results={"path_collisions": list(collisions)},
        qa={
            "status": "blocked",
            "findings": [finding],
            "metrics": {"collision_count": len(collisions)},
        },
        command=[tool, *argv],
        inputs=[item.get("input_path") for item in collisions],
    )
    errors = [
        {
            "kind": "output_conflict",
            "code": "unsafe_output_input_collision",
            "message": (
                f"{item['flag']} ({item['output_path']}) conflicts with "
                f"{item['input']} ({item['input_path']})."
            ),
        }
        for item in collisions
    ]
    payload.update(
        {
            "ok": False,
            "message": message,
            "error": {
                "kind": "output_conflict",
                "code": "unsafe_output_input_collision",
                "message": "At least one requested output aliases or overlaps protected input data.",
                "retryable": False,
            },
            "errors": errors,
        }
    )
    return payload


def preflight_astro_cli(script_file: str | Path, argv: Sequence[str]) -> int | None:
    """Return 2 after a stdout-only controlled block, otherwise return None."""
    script_name = Path(script_file).name
    planner = PLANNERS.get(script_name)
    if planner is None:
        return None
    plan = planner(list(argv))
    collisions = find_plan_collisions(plan)
    if not collisions:
        if script_name not in TRUST_REQUIRED_NOTEBOOK_EXECUTORS or "--trust-notebook-code" in argv:
            return None
        message = (
            "Notebook execution is arbitrary code and is blocked by default. Review every selected notebook "
            "and pass --trust-notebook-code only after explicit confirmation."
        )
        payload = standard_tool_payload(
            Path(script_name).stem,
            status="blocked",
            notes=[message],
            artifacts={},
            results={"blocked_reason": message, "error_type": "untrusted_notebook_code"},
            qa={"status": "blocked", "findings": [message], "metrics": {"blocking_count": 1}},
            command=[Path(script_name).stem, *argv],
        )
        print(json.dumps(payload, ensure_ascii=True, allow_nan=False))
        return 2
    print(json.dumps(blocked_payload(Path(script_name).stem, collisions, argv), ensure_ascii=True, allow_nan=False))
    return 2

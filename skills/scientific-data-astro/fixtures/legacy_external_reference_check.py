#!/usr/bin/env python3
"""Compare Practice 1 legacy spectroscopy results against fixed primary references."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.provenance_utils import public_path, standard_qa_payload, standard_tool_payload, write_manifest
from _internal.runtime_common import clean_known_stderr, configure_runtime


TOOL_NAME = "legacy_external_reference_check.check"


class InputValidationError(Exception):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


PW_AND_REFERENCE = {
    "target": "PW And",
    "source": "Lopez-Santiago et al. 2003, A&A 411, 489",
    "url": "https://doi.org/10.1051/0004-6361:20031377",
    "rv_helio_kms": -11.15,
    "vsini_kms": 22.6,
    "li_ew_milliangstrom": 273.0,
}

GZ_LEO_REFERENCE = {
    "target": "GZ Leo / 2RE J1101+223 / HD 95559",
    "primary_source": "Galvez et al. 2009, AJ 137, 3965",
    "primary_url": "https://arxiv.org/abs/0901.1634",
    "supporting_source": "Jeffries et al. 1995, MNRAS 276, 397",
    "supporting_url": "https://adsabs.harvard.edu/pdf/1995MNRAS.276..397J",
    "period_days": 1.5260,
    "t_conjunction_hjd_minus_2400000": 49051.312,
    "gamma_kms": 2.93,
    "kp_kms": 108.92,
    "ks_kms": 110.43,
    "eccentricity": 0.0073,
    "primary_vsini_kms": 26.23,
    "primary_vsini_err_kms": 1.13,
    "secondary_vsini_kms": 26.92,
    "secondary_vsini_err_kms": 1.14,
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Run the narrow external-reference QA for Practice 1.")
    check.add_argument("--rv-summary", required=True, help="JSON from legacy_rv_coursework_workbench.py analyze.")
    check.add_argument("--gzleo-fits", help="Original or copied FITS for 2REJ1101+22/GZ Leo, used to compute orbital phase.")
    check.add_argument("--li-summary", help="Optional JSON from li6708_equivalent_width_workbench.py.")
    check.add_argument("--istarmod-summary", help="Optional JSON from istarmod_workbench.py run-sm.")
    check.add_argument("--output-dir", required=True)
    check.add_argument("--summary-json")
    check.add_argument("--manifest-json")
    return parser.parse_args()


def fail_validation(issues: list[str]) -> None:
    if issues:
        raise InputValidationError(issues)


def output_file_issue(path: str | Path | None, label: str) -> str | None:
    if not path:
        return None
    candidate = Path(path).expanduser()
    if candidate.exists() and candidate.is_dir():
        return f"{label} apunta a un directorio, no a un archivo: {public_path(candidate)}"
    probe = candidate.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"{label} no puede escribirse porque un componente padre no es directorio: {public_path(probe)}"
    return None


def output_dir_issue(output_dir: Path) -> str | None:
    if output_dir.exists() and not output_dir.is_dir():
        return f"--output-dir existe pero no es un directorio: {public_path(output_dir)}"
    probe = output_dir.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and not probe.is_dir():
        return f"--output-dir no puede crearse porque un componente padre no es directorio: {public_path(probe)}"
    return None


def blocked_payload(args, issues: list[str]) -> dict:
    return standard_tool_payload(
        TOOL_NAME,
        status="blocked",
        notes=[
            "Validacion de entrada fallida antes de comparar contra referencias externas.",
            "La comprobacion se bloquea para evitar informes parciales o JSON corruptos.",
        ],
        artifacts={"summary_json": args.summary_json, "output_dir": args.output_dir},
        results={
            "input_validation_issues": issues,
            "rv_summary": args.rv_summary,
            "gzleo_fits": args.gzleo_fits,
            "li_summary": args.li_summary,
            "istarmod_summary": args.istarmod_summary,
        },
        qa=standard_qa_payload(status="blocked", findings=issues, metrics={"issue_count": len(issues)}),
    )


def emit_check_payload(
    payload: dict,
    args,
    *,
    manifest_inputs: list[Path] | None = None,
    manifest_outputs: list[Path] | None = None,
    manifest_notes: list[str] | None = None,
) -> int:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)
    print(rendered)
    if args.summary_json:
        try:
            summary_path = Path(args.summary_json).expanduser()
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            message = clean_known_stderr(f"Could not write summary JSON: {exc}") or f"Could not write summary JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    if args.manifest_json:
        try:
            write_manifest(
                args.manifest_json,
                inputs=manifest_inputs or [],
                outputs=manifest_outputs or [],
                parameters={"tool": TOOL_NAME},
                command=" ".join(sys.argv),
                notes=manifest_notes or payload.get("notes", []),
            )
        except OSError as exc:
            message = clean_known_stderr(f"Could not write manifest JSON: {exc}") or f"Could not write manifest JSON: {exc}"
            print(message, file=sys.stderr)
            return 2
    return 2 if payload["status"] == "blocked" else (1 if payload["status"] == "fail" else 0)


def safe_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        rendered = float(value)
    except (TypeError, ValueError):
        return None
    return rendered if math.isfinite(rendered) else None


def load_json(path: str | None, label: str, *, required: bool = False) -> dict:
    if not path:
        if required:
            raise InputValidationError([f"Falta indicar {label}."])
        return {}
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        if required:
            raise InputValidationError([f"No existe {label}: {public_path(candidate)}"])
        raise InputValidationError([f"Se indico {label}, pero no existe: {public_path(candidate)}"])
    if not candidate.is_file():
        raise InputValidationError([f"{label} no es un archivo: {public_path(candidate)}"])
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputValidationError([f"No se pudo leer {label} como JSON: {public_path(candidate)}: {exc}"]) from exc
    if not isinstance(payload, dict):
        raise InputValidationError([f"{label} debe contener un objeto JSON: {public_path(candidate)}"])
    return payload


def comparison(metric: str, observed: float | None, reference: float | None, tolerance: float, *, units: str) -> dict:
    observed = safe_float(observed)
    reference = safe_float(reference)
    delta = None if observed is None or reference is None else observed - reference
    status = "missing" if delta is None else ("ok" if abs(delta) <= tolerance else "warning")
    return {
        "metric": metric,
        "observed": observed,
        "reference": reference,
        "delta": delta,
        "tolerance": tolerance,
        "units": units,
        "status": status,
    }


def first_by_case(rows: list[dict], case_id: str) -> dict | None:
    for row in rows:
        if row.get("case_id") == case_id:
            return row
    return None


def value_by_case(rows: list[dict], case_id: str, key: str) -> float | None:
    row = first_by_case(rows, case_id)
    if not row:
        return None
    value = row.get(key)
    return safe_float(value)


def parse_istarmod_log(summary: dict) -> dict:
    candidates = []
    artifacts = summary.get("artifacts", {})
    if artifacts.get("log_path"):
        candidates.append(Path(artifacts["log_path"]).expanduser())
    for item in artifacts.get("artifact_files", []) or []:
        path = Path(item).expanduser()
        if path.suffix.lower() == ".log":
            candidates.append(path)
    parsed = {}
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        vrad_matches = re.findall(r"V_rad\s*=\s*([-+]?\d+(?:\.\d+)?)", text)
        vrot_matches = re.findall(r"V_rot\s*=\s*([-+]?\d+(?:\.\d+)?)", text)
        ew_match = re.search(r"EW\s*=\s*([-+]?\d+(?:\.\d+)?)\s*\+-\s*([-+]?\d+(?:\.\d+)?)", text)
        if vrad_matches:
            parsed["rv_kms"] = safe_float(vrad_matches[-1])
        if vrot_matches:
            value = safe_float(vrot_matches[-1])
            parsed["vsini_kms"] = abs(value) if value is not None else None
        if ew_match:
            parsed["ew_angstrom"] = safe_float(ew_match.group(1))
            parsed["ew_err_angstrom"] = safe_float(ew_match.group(2))
        if parsed:
            parsed["source_log"] = str(path)
            break
    return parsed


def read_hjd_minus_2400000(fits_path: str | None) -> dict:
    if not fits_path:
        return {}
    from astropy.io import fits

    path = Path(fits_path).expanduser().resolve()
    if not path.exists():
        raise InputValidationError([f"No existe --gzleo-fits: {public_path(path)}"])
    if not path.is_file():
        raise InputValidationError([f"--gzleo-fits no es un archivo: {public_path(path)}"])
    try:
        with fits.open(path, memmap=False, ignore_missing_end=True) as hdul:
            header = hdul[0].header
            mjd = header.get("MJD-OBS")
            jd = header.get("JD")
            hjd = header.get("HJD")
            date_obs = header.get("DATE-OBS")
    except Exception as exc:
        raise InputValidationError([f"No se pudo leer --gzleo-fits como FITS: {public_path(path)}: {exc}"]) from exc
    if hjd is not None:
        value = safe_float(hjd)
        if value is None:
            return {"fits_path": str(path), "date_obs": date_obs, "time_warning": "HJD no finito"}
        hjd_minus = value - 2400000.0 if value > 2400000.0 else value
        source = "HJD"
    elif jd is not None:
        value = safe_float(jd)
        if value is None:
            return {"fits_path": str(path), "date_obs": date_obs, "time_warning": "JD no finito"}
        hjd_minus = value - 2400000.0
        source = "JD"
    elif mjd is not None:
        # MJD = JD - 2400000.5. The Galvez et al. table is HJD-2400000;
        # heliocentric correction is negligible for this coarse QA threshold.
        value = safe_float(mjd)
        if value is None:
            return {"fits_path": str(path), "date_obs": date_obs, "time_warning": "MJD-OBS no finito"}
        hjd_minus = value + 0.5
        source = "MJD-OBS + 0.5"
    else:
        return {"fits_path": str(path), "date_obs": date_obs}
    return {"fits_path": str(path), "date_obs": date_obs, "hjd_minus_2400000": hjd_minus, "time_source": source}


def gzleo_expected_velocities(hjd_minus_2400000: float) -> dict:
    ref = GZ_LEO_REFERENCE
    phase = ((hjd_minus_2400000 - ref["t_conjunction_hjd_minus_2400000"]) / ref["period_days"]) % 1.0
    sine = math.sin(2.0 * math.pi * phase)
    # Sign convention chosen to reproduce the published FOCES02 table in Galvez et al. 2009.
    primary = ref["gamma_kms"] - ref["kp_kms"] * sine
    secondary = ref["gamma_kms"] + ref["ks_kms"] * sine
    return {
        "phase": phase,
        "primary_expected_rv_kms": primary,
        "secondary_expected_rv_kms": secondary,
        "gamma_kms": ref["gamma_kms"],
    }


def find_rv_summary(rv_payload: dict, case_id: str) -> dict | None:
    for row in rv_payload.get("results", {}).get("rv_summaries", []):
        if row.get("case_id") == case_id:
            return row
    return None


def assignment_score(observed_a: float | None, observed_b: float | None, expected_primary: float, expected_secondary: float, *, swapped: bool) -> float | None:
    observed_a = safe_float(observed_a)
    observed_b = safe_float(observed_b)
    expected_primary = safe_float(expected_primary)
    expected_secondary = safe_float(expected_secondary)
    if observed_a is None or observed_b is None:
        return None
    if expected_primary is None or expected_secondary is None:
        return None
    if swapped:
        return abs(observed_b - expected_primary) + abs(observed_a - expected_secondary)
    return abs(observed_a - expected_primary) + abs(observed_b - expected_secondary)


def comparison_findings(prefix: str, comparisons: list[dict]) -> list[str]:
    findings = []
    for item in comparisons:
        slug = re.sub(r"[^a-z0-9]+", "_", item["metric"].lower()).strip("_")
        if item["status"] == "missing":
            findings.append(f"{prefix}:{slug}_missing")
        elif item["status"] == "warning":
            findings.append(f"{prefix}:{slug}_outside_tolerance")
    return findings


def build_pw_and_check(rv_payload: dict, li_payload: dict, istarmod_payload: dict) -> dict:
    rv_rows = rv_payload.get("results", {}).get("rv_summaries", [])
    vsini_rows = rv_payload.get("results", {}).get("vsini_rows", [])
    li_results = (li_payload.get("results") or li_payload) if li_payload else {}
    istarmod_results = parse_istarmod_log(istarmod_payload) if istarmod_payload else {}

    rv_value = value_by_case(rv_rows, "pwand_rv", "vhelio_media_kms")
    vsini_fwhm = value_by_case(vsini_rows, "pwand_vsini36", "vsini_interp_kms")
    vsini_istarmod = istarmod_results.get("vsini_kms")
    li_ew = safe_float(li_results.get("ew_milliangstrom"))

    comparisons = [
        comparison("PW And RV heliocentrica", rv_value, PW_AND_REFERENCE["rv_helio_kms"], 2.5, units="km/s"),
        comparison("PW And v sin i desde FWHM-CCF", vsini_fwhm, PW_AND_REFERENCE["vsini_kms"], 4.0, units="km/s"),
        comparison("PW And v sin i desde iSTARMOD", vsini_istarmod, PW_AND_REFERENCE["vsini_kms"], 4.0, units="km/s"),
        comparison("PW And EW Li I 6707.8", li_ew, PW_AND_REFERENCE["li_ew_milliangstrom"], 30.0, units="mA"),
    ]
    findings = []
    findings.extend(comparison_findings("pw_and", comparisons))
    if comparisons[1]["status"] == "warning" and comparisons[2]["status"] == "ok":
        findings.append("vsini_fwhm_disagrees_but_istarmod_matches_reference")
    elif comparisons[1]["status"] == "warning":
        findings.append("vsini_fwhm_disagrees_with_reference")
    findings = sorted(set(findings))
    return {
        "reference": PW_AND_REFERENCE,
        "observed": {
            "rv_helio_kms": rv_value,
            "vsini_fwhm_kms": vsini_fwhm,
            "vsini_istarmod_kms": vsini_istarmod,
            "li_ew_milliangstrom": li_ew,
        },
        "comparisons": comparisons,
        "findings": findings,
    }


def build_gzleo_check(rv_payload: dict, gzleo_fits: str | None) -> dict:
    rv_rows = rv_payload.get("results", {}).get("rv_summaries", [])
    vsini_rows = rv_payload.get("results", {}).get("vsini_rows", [])
    comp_a = find_rv_summary(rv_payload, "rej_compA_rv")
    comp_b = find_rv_summary(rv_payload, "rej_compB_rv")
    obs_a = safe_float(comp_a.get("vhelio_media_kms")) if comp_a else None
    obs_b = safe_float(comp_b.get("vhelio_media_kms")) if comp_b else None

    time_info = read_hjd_minus_2400000(gzleo_fits)
    expected = {}
    direct_score = None
    swapped_score = None
    component_swap_suspected = False
    ccf_suggestion = {}
    rv_comparisons = []
    if time_info.get("hjd_minus_2400000") is not None:
        expected = gzleo_expected_velocities(time_info["hjd_minus_2400000"])
        direct_score = assignment_score(obs_a, obs_b, expected["primary_expected_rv_kms"], expected["secondary_expected_rv_kms"], swapped=False)
        swapped_score = assignment_score(obs_a, obs_b, expected["primary_expected_rv_kms"], expected["secondary_expected_rv_kms"], swapped=True)
        component_swap_suspected = swapped_score is not None and direct_score is not None and swapped_score + 20.0 < direct_score
        rv_comparisons = [
            comparison("GZ Leo compA vs primaria publicada", obs_a, expected["primary_expected_rv_kms"], 15.0, units="km/s"),
            comparison("GZ Leo compB vs secundaria publicada", obs_b, expected["secondary_expected_rv_kms"], 15.0, units="km/s"),
            comparison("GZ Leo compB vs primaria publicada si swap", obs_b, expected["primary_expected_rv_kms"], 15.0, units="km/s"),
            comparison("GZ Leo compA vs secundaria publicada si swap", obs_a, expected["secondary_expected_rv_kms"], 25.0, units="km/s"),
        ]
        ccf_suggestion = {
            "use_as_review_hint_only": True,
            "broad_first_pass_window": 275,
            "component_pass_window": 60,
            "expected_primary_wincenter_kms": round(expected["primary_expected_rv_kms"], 1),
            "expected_secondary_wincenter_kms": round(expected["secondary_expected_rv_kms"], 1),
            "note": "Usar estos centros para revisar picos CCF; no sustituyen la inspeccion manual de fxcor.",
        }

    vsini_a = value_by_case(vsini_rows, "rej_vsini36_compA_k0", "vsini_interp_kms")
    vsini_b = value_by_case(vsini_rows, "rej_vsini36_compB_k1", "vsini_interp_kms")
    vsini_comparisons = [
        comparison("GZ Leo v sin i componente A", vsini_a, GZ_LEO_REFERENCE["primary_vsini_kms"], 6.0, units="km/s"),
        comparison("GZ Leo v sin i componente B", vsini_b, GZ_LEO_REFERENCE["secondary_vsini_kms"], 10.0, units="km/s"),
    ]
    findings = []
    if not time_info.get("hjd_minus_2400000"):
        findings.append("orbital_phase_unavailable")
    if component_swap_suspected:
        findings.append("component_swap_or_ccf_center_suspected")
    rv_findings = comparison_findings("gz_leo", rv_comparisons[:2])
    vsini_findings = comparison_findings("gz_leo", vsini_comparisons)
    findings.extend(rv_findings)
    findings.extend(vsini_findings)
    if any(item["status"] in {"warning", "missing"} for item in rv_comparisons[:2]):
        findings.append("published_orbit_rv_mismatch_requires_manual_ccf_review")
    if any(item["status"] in {"warning", "missing"} for item in vsini_comparisons):
        findings.append("vsini_disagrees_with_galvez2009")
    findings = sorted(set(findings))
    return {
        "reference": GZ_LEO_REFERENCE,
        "time": time_info,
        "expected_from_orbit": expected,
        "observed": {
            "compA_rv_kms": obs_a,
            "compB_rv_kms": obs_b,
            "compA_vsini_kms": vsini_a,
            "compB_vsini_kms": vsini_b,
        },
        "assignment_scores": {
            "direct": direct_score,
            "swapped": swapped_score,
        },
        "component_swap_suspected": component_swap_suspected,
        "rv_comparisons": rv_comparisons,
        "vsini_comparisons": vsini_comparisons,
        "ccf_window_suggestion": ccf_suggestion,
        "findings": findings,
    }


def write_report(path: Path, payload: dict) -> None:
    results = payload["results"]
    lines = [
        "# Comparación externa estrecha de la Práctica 1",
        "",
        "Este informe es una capa de QA: no sustituye `fxcor`, la calibración FWHM--v sin i ni `iSTARMOD`.",
        "",
        "## PW And",
        "",
    ]
    for item in results["pw_and"]["comparisons"]:
        lines.append(
            f"- {item['metric']}: observado `{item['observed']}`, referencia `{item['reference']}` {item['units']}, delta `{item['delta']}` -> `{item['status']}`."
        )
    lines.extend(["", "## GZ Leo / 2REJ1101+223", ""])
    gz = results["gz_leo"]
    if gz["expected_from_orbit"]:
        lines.append(
            f"- Fase orbital estimada: `{gz['expected_from_orbit']['phase']:.4f}` usando `{gz['time'].get('time_source')}`."
        )
        lines.append(
            f"- RV esperada primaria/secundaria: `{gz['expected_from_orbit']['primary_expected_rv_kms']:.2f}` / `{gz['expected_from_orbit']['secondary_expected_rv_kms']:.2f}` km/s."
        )
    lines.append(f"- Component swap suspected: `{gz['component_swap_suspected']}`.")
    for item in gz["rv_comparisons"] + gz["vsini_comparisons"]:
        lines.append(
            f"- {item['metric']}: observado `{item['observed']}`, referencia `{item['reference']}` {item['units']}, delta `{item['delta']}` -> `{item['status']}`."
        )
    if gz.get("ccf_window_suggestion"):
        suggestion = gz["ccf_window_suggestion"]
        lines.extend(
            [
                "",
                "## Sugerencia para revisar CCF",
                "",
                f"- Primera pasada amplia: `window={suggestion['broad_first_pass_window']}`.",
                f"- Pasadas por componente: `window={suggestion['component_pass_window']}`.",
                f"- Centro primaria esperado: `wincenter≈{suggestion['expected_primary_wincenter_kms']}` km/s.",
                f"- Centro secundaria esperado: `wincenter≈{suggestion['expected_secondary_wincenter_kms']}` km/s.",
            ]
        )
    lines.extend(["", "## Findings", ""])
    for finding in payload.get("qa", {}).get("findings", []):
        lines.append(f"- `{finding}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_check(args):
    ensure_datanalysis_runtime("legacy_external_reference_check")
    configure_runtime("legacy_external_reference_check")
    output_dir = Path(args.output_dir).expanduser().resolve()
    report_md = output_dir / "external_reference_check.md"
    if not args.summary_json:
        args.summary_json = str(output_dir / "external_reference_check.json")
    summary_json = Path(args.summary_json).expanduser().resolve()
    preflight_issues = []
    for issue in [
        output_dir_issue(output_dir),
        output_file_issue(report_md, "report Markdown"),
        output_file_issue(summary_json, "summary JSON"),
        output_file_issue(args.manifest_json, "manifest JSON"),
    ]:
        if issue:
            preflight_issues.append(issue)
    fail_validation(preflight_issues)

    rv_payload = load_json(args.rv_summary, "--rv-summary", required=True)
    li_payload = load_json(args.li_summary, "--li-summary")
    istarmod_payload = load_json(args.istarmod_summary, "--istarmod-summary")

    pw = build_pw_and_check(rv_payload, li_payload, istarmod_payload)
    gz = build_gzleo_check(rv_payload, args.gzleo_fits)

    def scoped(scope: str, items: list[str]) -> list[str]:
        return [item if item.startswith(f"{scope}:") else f"{scope}:{item}" for item in items]

    findings = []
    findings.extend(scoped("pw_and", pw["findings"]))
    findings.extend(scoped("gz_leo", gz["findings"]))
    findings = sorted(set(findings))
    status = "warning" if findings else "ok"
    notes = [
        "Comparacion externa estrecha basada solo en referencias primarias fijas de esta practica.",
        "No se hace scraping general de literatura ni se sustituyen resultados del guion.",
    ]
    if gz.get("component_swap_suspected"):
        notes.append("La comparacion orbital sugiere revisar etiquetas de componente o centros de CCF en GZ Leo.")

    payload = standard_tool_payload(
        TOOL_NAME,
        status=status,
        notes=notes,
        artifacts={"report_md": str(report_md), "summary_json": str(summary_json)},
        results={
            "pw_and": pw,
            "gz_leo": gz,
            "reference_matches": {
                "pw_and": [item for item in pw["comparisons"] if item["status"] == "ok"],
                "gz_leo": [item for item in gz["rv_comparisons"] + gz["vsini_comparisons"] if item["status"] == "ok"],
            },
            "warnings": findings,
            "component_swap_suspected": gz.get("component_swap_suspected", False),
            "ccf_window_suggestion": gz.get("ccf_window_suggestion", {}),
        },
        qa=standard_qa_payload(status=status, findings=findings, metrics={"finding_count": len(findings)}),
    )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_report(report_md, payload)
    except OSError as exc:
        raise InputValidationError([f"No se pudo escribir el informe en {public_path(report_md)}: {exc}"]) from exc
    inputs = [Path(args.rv_summary).expanduser().resolve()]
    for raw in [args.li_summary, args.istarmod_summary, args.gzleo_fits]:
        if raw:
            inputs.append(Path(raw).expanduser().resolve())
    return emit_check_payload(payload, args, manifest_inputs=inputs, manifest_outputs=[summary_json, report_md], manifest_notes=notes)


def main():
    args = parse_args()
    if args.command == "check":
        try:
            return cmd_check(args)
        except InputValidationError as exc:
            return emit_check_payload(blocked_payload(args, exc.issues), args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

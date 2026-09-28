#!/usr/bin/env python3
"""Generate previews with native Quick Look when possible, with safe fallbacks."""

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.path_safety import find_output_input_collisions
from _internal.pdfium_backend import render_pdf_pages
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.public_contract import build_preflight_payload, build_tool_payload, emit_payload
from _internal.runtime_common import clean_known_stderr, configure_runtime, find_executable


IWORK_SUFFIXES = {".pages", ".numbers", ".key"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input file path.")
    parser.add_argument("--output", required=True, help="Output PNG path.")
    parser.add_argument("--size", type=int, default=1800, help="Thumbnail size.")
    parser.add_argument("--timeout-sec", type=float, default=20.0, help="Timeout for native Quick Look preview generation.")
    parser.add_argument("--preflight-only", action="store_true", help="Only report capability/preflight status without generating a preview.")
    parser.add_argument("--summary-json", help="Optional JSON status summary.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    return parser.parse_args()


def _emit_collision_only(args, input_path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing Quick Look outputs that overlap the input file or package."
    payload = build_tool_payload(
        "quicklook_bridge",
        status="blocked",
        notes=[message, "No preview, summary, or manifest was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "input": public_path(input_path),
            "collisions": collisions,
        },
        qa={
            "status": "blocked",
            "findings": [{"severity": "high", "title": "Input/output collision", "detail": message}],
            "metrics": {"blocking_count": len(collisions)},
        },
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def _preflight_output_safety(args, input_path: Path, output_path: Path) -> int | None:
    requested = [
        ("--output", output_path),
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
        ("derived:qlmanage-preview", output_path.parent / f"{input_path.name}.png"),
    ]
    collisions = find_output_input_collisions([("input", input_path)], requested)
    return _emit_collision_only(args, input_path, collisions) if collisions else None


def _optional_dependency(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def build_capability_report(input_path: Path) -> dict:
    suffix = input_path.suffix.lower()
    qlmanage = find_executable(["qlmanage"])
    capabilities = {
        "platform": sys.platform,
        "native_quicklook": bool(qlmanage),
        "qlmanage_path": public_path(qlmanage) if qlmanage else None,
        "image_fallback": _optional_dependency("PIL"),
        "pdf_fallback": _optional_dependency("pypdfium2"),
        "iwork_zip_preview": suffix in IWORK_SUFFIXES,
    }
    blocking_findings = []
    warning_findings = []
    recommendation = "Native Quick Look is ready."
    if sys.platform != "darwin":
        warning_findings.append("Quick Look native previews are only available on macOS.")
    if not capabilities["native_quicklook"]:
        warning_findings.append("qlmanage is not available, so native Quick Look cannot be used.")
    fallback_ready = False
    if suffix in IWORK_SUFFIXES:
        fallback_ready = capabilities["image_fallback"]
        if not fallback_ready:
            blocking_findings.append("Pillow is required to convert embedded iWork preview assets into PNG output.")
    elif suffix == ".pdf":
        fallback_ready = capabilities["pdf_fallback"]
        if not fallback_ready:
            blocking_findings.append("pypdfium2 is required for the PDF first-page fallback.")
    elif suffix in IMAGE_SUFFIXES:
        fallback_ready = capabilities["image_fallback"]
        if not fallback_ready:
            blocking_findings.append("Pillow is required for the direct image-to-PNG fallback.")
    else:
        fallback_ready = False
        if not capabilities["native_quicklook"]:
            blocking_findings.append("This file family has no portable fallback when native Quick Look is unavailable.")
    if blocking_findings:
        status = "blocked"
        recommendation = "Install the missing fallback dependency or run on macOS with qlmanage available."
    elif warning_findings:
        status = "warning"
        recommendation = "Proceed, but expect fallback rendering or platform limitations."
    else:
        status = "ok"
    return {
        "status": status,
        "blocking_findings": blocking_findings,
        "warning_findings": warning_findings,
        "recommendation": recommendation,
        "capabilities": capabilities,
    }


def _blocked_qa(title: str, detail: str) -> dict:
    return {
        "status": "blocked",
        "findings": [{"severity": "high", "title": title, "detail": detail}],
        "metrics": {"blocking_count": 1},
    }


def _emit_blocked(args, input_path: Path, output_path: Path, message: str, *, title: str = "Preview generation blocked", capability_report: dict | None = None) -> int:
    cleaned = clean_known_stderr(message) or message
    report = capability_report or build_capability_report(input_path)
    payload = build_tool_payload(
        "quicklook_bridge",
        status="blocked",
        notes=["Preview generation was blocked before a usable PNG could be produced."],
        artifacts={"summary_json": args.summary_json},
        results={
            "input": public_path(input_path),
            "output": public_path(output_path),
            "native_error": cleaned,
            **report,
        },
        qa=_blocked_qa(title, cleaned),
        legacy={
            "input": public_path(input_path),
            "output": None,
            "method": "blocked",
            "used_fallback": False,
            "native_error": cleaned,
        },
    )
    emit_payload(payload, args.summary_json)
    return 2


def validate_output_target(output_path: Path) -> str | None:
    parent = output_path.parent
    if parent.exists() and not parent.is_dir():
        return f"Output parent exists and is not a directory: {parent}"
    if output_path.exists() and output_path.is_dir():
        return f"Output path exists and is a directory, not a PNG file path: {output_path}"
    return None


def ensure_png(image_path, output_path):
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return str(output_path.resolve())


def try_qlmanage(input_path, output_path, size, timeout_sec):
    configure_runtime("quicklook_bridge")
    qlmanage = find_executable(["qlmanage"])
    if qlmanage is None:
        return {
            "ok": False,
            "method": "qlmanage",
            "preview_path": None,
            "native_error": "qlmanage is not available on this machine.",
        }
    try:
        result = subprocess.run(
            [qlmanage, "-t", "-s", str(size), "-o", str(output_path.parent), str(input_path)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "method": "qlmanage",
            "preview_path": None,
            "native_error": f"qlmanage timed out after {timeout_sec:g} seconds.",
        }
    generated = output_path.parent / f"{input_path.name}.png"
    if result.returncode == 0 and generated.exists():
        generated.replace(output_path)
        return {
            "ok": True,
            "method": "qlmanage",
            "preview_path": str(output_path.resolve()),
            "native_error": None,
        }
    return {
        "ok": False,
        "method": "qlmanage",
        "preview_path": None,
        "native_error": (result.stderr or result.stdout or "qlmanage failed").strip(),
    }


def extract_iwork_preview(input_path, output_path):
    preferred = ["preview-web.jpg", "preview.jpg", "preview-micro.jpg"]
    with zipfile.ZipFile(input_path) as zf:
        names = zf.namelist()
        candidates = []
        for name in preferred:
            for member in names:
                if member.endswith(name):
                    candidates.append(member)
        if not candidates:
            candidates = [
                member
                for member in names
                if "preview" in member.lower() and Path(member).suffix.lower() in IMAGE_SUFFIXES
            ]
        if not candidates:
            candidates = [
                member
                for member in names
                if Path(member).suffix.lower() in IMAGE_SUFFIXES
            ]
        if not candidates:
            return None
        chosen = candidates[0]
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="quicklook-preview-",
            suffix=Path(chosen).suffix,
            dir=output_path.parent,
            delete=False,
        ) as handle:
            handle.write(zf.read(chosen))
            temp = Path(handle.name)
    try:
        return ensure_png(temp, output_path)
    finally:
        if temp.exists():
            temp.unlink()


def render_pdf_preview(input_path, output_path):
    rendered = render_pdf_pages(input_path, [(1, output_path)])
    return str(rendered[0].resolve()) if rendered else None


def image_preview(input_path, output_path):
    return ensure_png(input_path, output_path)


def fallback_preview(input_path, output_path):
    suffix = input_path.suffix.lower()
    if suffix in IWORK_SUFFIXES:
        preview = extract_iwork_preview(input_path, output_path)
        if preview:
            return {"ok": True, "method": "iwork_preview_asset", "preview_path": preview}
    if suffix == ".pdf":
        preview = render_pdf_preview(input_path, output_path)
        if preview:
            return {"ok": True, "method": "pdf_first_page", "preview_path": preview}
    if suffix in IMAGE_SUFFIXES:
        preview = image_preview(input_path, output_path)
        return {"ok": True, "method": "image_copy", "preview_path": preview}
    return {"ok": False, "method": "fallback", "preview_path": None}


def generate_preview(input_path, output_path, size=1800, timeout_sec=20.0):
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    native = try_qlmanage(input_path, output_path, size=size, timeout_sec=timeout_sec)
    if native["ok"]:
        native["used_fallback"] = False
        return native
    fallback = fallback_preview(input_path, output_path)
    fallback["native_error"] = native.get("native_error")
    fallback["used_fallback"] = bool(fallback["ok"])
    return fallback


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    collision_status = _preflight_output_safety(args, input_path, output_path)
    if collision_status is not None:
        raise SystemExit(collision_status)
    if not input_path.exists():
        raise SystemExit(_emit_blocked(args, input_path, output_path, f"File not found: {input_path}", title="Input missing"))
    ensure_datanalysis_runtime("quicklook_bridge", strict=False)
    capability_report = build_capability_report(input_path)
    if args.preflight_only:
        payload = build_preflight_payload(
            "quicklook_bridge",
            status=capability_report["status"],
            capabilities=capability_report["capabilities"],
            recommendation=capability_report["recommendation"],
            blocking_findings=capability_report["blocking_findings"],
            warning_findings=capability_report["warning_findings"],
            notes=[
                "This preflight checks whether Quick Look native rendering or a portable fallback is available for the requested file family.",
            ],
            artifacts={"summary_json": args.summary_json},
            results={"input": public_path(input_path), "output": public_path(output_path)},
        )
        emit_payload(payload, args.summary_json)
        return
    output_error = validate_output_target(output_path)
    if output_error:
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                output_error,
                title="Invalid output path",
                capability_report=capability_report,
            )
        )
    if capability_report["status"] == "blocked":
        payload = build_preflight_payload(
            "quicklook_bridge",
            status="blocked",
            capabilities=capability_report["capabilities"],
            recommendation=capability_report["recommendation"],
            blocking_findings=capability_report["blocking_findings"],
            warning_findings=capability_report["warning_findings"],
            notes=["Preview generation was blocked before launch because neither the native route nor the required fallback was available."],
            artifacts={"summary_json": args.summary_json},
            results={"input": public_path(input_path), "output": public_path(output_path)},
        )
        emit_payload(payload, args.summary_json)
        raise SystemExit(2)
    try:
        result = generate_preview(input_path, output_path, size=args.size, timeout_sec=args.timeout_sec)
    except Exception as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or exc.__class__.__name__
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                message,
                title="Preview renderer failed",
                capability_report=capability_report,
            )
        ) from None
    if not result.get("ok"):
        message = result.get("native_error") or "Could not generate a preview with native or fallback methods."
        raise SystemExit(
            _emit_blocked(
                args,
                input_path,
                output_path,
                message,
                title="Preview generation failed",
                capability_report=capability_report,
            )
        )
    payload = build_tool_payload(
        "quicklook_bridge",
        status="warning" if result.get("used_fallback") else "ok",
        notes=[
            "This bridge prefers native Quick Look on macOS and falls back only when a safe local renderer is available.",
        ],
        artifacts={"summary_json": args.summary_json, "preview_png": output_path, "manifest_json": args.manifest_json},
        results={
            "input": public_path(input_path),
            "output": result["preview_path"],
            "method": result["method"],
            "used_fallback": result.get("used_fallback", False),
            "native_error": result.get("native_error"),
            **capability_report,
        },
        qa={
            "status": "warning" if result.get("used_fallback") else "ok",
            "findings": [result["native_error"]] if result.get("used_fallback") and result.get("native_error") else [],
            "metrics": {"used_fallback": bool(result.get("used_fallback"))},
        },
        legacy={
            "input": public_path(input_path),
            "output": result["preview_path"],
            "method": result["method"],
            "used_fallback": result.get("used_fallback", False),
            "native_error": result.get("native_error"),
        },
    )
    print(json.dumps(payload["results"], indent=2, ensure_ascii=True))
    if args.summary_json:
        emit_payload(payload, args.summary_json)
        print(f"Saved summary: {public_path(args.summary_json)}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=[output_path],
            parameters={"size": args.size, "method": result["method"]},
            notes=[result.get("native_error")] if result.get("native_error") else [],
        )
        print(f"Saved manifest: {public_path(args.manifest_json)}")


if __name__ == "__main__":
    main()

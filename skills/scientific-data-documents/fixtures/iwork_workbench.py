#!/usr/bin/env python3
"""Deep iWork package inspection and export helper for .pages, .numbers, and .key files."""

import argparse
import csv
import json
import math
import zipfile
from pathlib import Path

from document_semantics import extract_iwork_package, safe_output_name
from _internal.path_safety import find_output_input_collisions
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.runtime_common import clean_known_stderr
from quicklook_bridge import generate_preview


IWORK_SUFFIXES = {".pages", ".numbers", ".key"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input .pages/.numbers/.key file.")
    parser.add_argument("--output-dir", required=True, help="Directory for extracted assets and reports.")
    parser.add_argument("--output-json", help="Optional JSON summary path.")
    parser.add_argument("--contact-sheet", help="Optional PNG contact sheet path.")
    parser.add_argument("--html-report", help="Optional HTML summary report path.")
    parser.add_argument("--native-preview", help="Optional native Quick Look PNG path.")
    parser.add_argument("--enable-ocr", action="store_true", help="Run OCR on extracted previews when useful.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    return parser.parse_args()


def _emit_collision_only(args, input_path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing iWork outputs that overlap the input package."
    payload = build_tool_payload(
        "iwork_workbench",
        status="blocked",
        notes=[message, "No output files were written and the input package was not modified."],
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


def _preflight_output_safety(args, input_path: Path) -> int | None:
    output_dir = Path(args.output_dir).expanduser()
    requested = [
        ("--output-dir", output_dir),
        ("--output-json", args.output_json),
        ("--contact-sheet", args.contact_sheet),
        ("--html-report", args.html_report),
        ("--native-preview", args.native_preview),
        ("--manifest-json", args.manifest_json),
        ("derived:report.md", output_dir / "report.md"),
        ("derived:member_manifest.csv", output_dir / "member_manifest.csv"),
        ("derived:contact_sheet.png", output_dir / "contact_sheet.png"),
        ("derived:summary.json", output_dir / "summary.json"),
    ]
    if output_dir.is_dir():
        requested.extend(
            ("existing-output-member", item)
            for item in output_dir.rglob("*")
            if item.is_file()
        )
    collisions = find_output_input_collisions([("input", input_path)], requested)
    return _emit_collision_only(args, input_path, collisions) if collisions else None


def classify_asset(name):
    lower = name.lower()
    if "screenshot" in lower:
        return "screenshot"
    if "logo" in lower:
        return "logo"
    if "spectra" in lower or "spectrum" in lower:
        return "spectra"
    if "timeseries" in lower or "time_series" in lower or "lightcurve" in lower:
        return "time-series"
    if lower.endswith(".pdf") and "equation-" in lower:
        return "equation"
    if lower.endswith((".jpg", ".jpeg", ".png")):
        return "image"
    if lower.endswith(".iwa"):
        return "iwa"
    return "other"


def topic_hints(asset_names):
    counts = {}
    for name in asset_names:
        kind = classify_asset(name)
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def create_contact_sheet(image_paths, output_path):
    try:
        from PIL import Image, ImageOps, ImageDraw
    except Exception:
        return False
    if not image_paths:
        return False
    thumbs = []
    for path in image_paths[:9]:
        try:
            image = Image.open(path).convert("RGB")
            image.thumbnail((320, 220))
            canvas = Image.new("RGB", (340, 260), (247, 249, 252))
            offset = ((340 - image.width) // 2, 10 + (220 - image.height) // 2)
            canvas.paste(image, offset)
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 232), Path(path).name[:40], fill=(40, 40, 40))
            thumbs.append(canvas)
        except Exception:
            continue
    if not thumbs:
        return False
    cols = min(3, len(thumbs))
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = Image.new("RGB", (cols * 340, rows * 260), (255, 255, 255))
    for idx, thumb in enumerate(thumbs):
        x = (idx % cols) * 340
        y = (idx // cols) * 260
        sheet.paste(thumb, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return True


def write_markdown(summary, output_dir):
    numbers_summary = summary.get("numbers_summary") or {}
    lines = [
        "# iWork Package Report",
        "",
        f"- Input: `{summary['path']}`",
        f"- Package type: `{summary.get('package_type', 'unknown')}`",
        f"- Member count: `{summary.get('member_count', 0)}`",
        f"- Preview files: `{len(summary.get('preview_files', []))}`",
        f"- Image assets: `{summary.get('image_asset_count', 0)}`",
        f"- Equation PDFs: `{summary.get('equation_pdf_count', 0)}`",
        "",
        "## Bundle metadata",
    ]
    bundle_metadata = summary.get("bundle_metadata", {})
    if bundle_metadata:
        for key, value in bundle_metadata.items():
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- No bundle metadata recovered")
    lines.extend([
        "",
        "## Build history",
    ])
    build_history = summary.get("build_history", [])
    if isinstance(build_history, list) and build_history:
        for item in build_history:
            lines.append(f"- `{item}`")
    else:
        lines.append("- No build history recovered")
    lines.extend([
        "",
        "## Structure hints",
    ])
    structure = summary.get("structure_hints", {})
    for key, value in sorted(structure.get("counts", {}).items()):
        lines.append(f"- `{key}`: {value}")
    for item in structure.get("roles", []):
        lines.append(f"- `{item}`")
    lines.extend([
        "",
        "## Topic hints",
    ])
    for key, value in sorted(summary.get("topic_hints", {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Member distribution"])
    for key, value in sorted(summary.get("member_extension_counts", {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Asset hints"])
    for item in summary.get("asset_name_hints", [])[:20]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## IWA hints"])
    for item in summary.get("document_iwa_hints", [])[:20]:
        lines.append(f"- `{item}`")
    if numbers_summary.get("sheets"):
        lines.extend(["", "## Numbers sheets and tables"])
        for sheet in numbers_summary["sheets"]:
            lines.append(f"- Sheet `{sheet['sheet']}`")
            for table in sheet["tables"][:6]:
                lines.append(
                    f"  Table `{table['name']}`: rows={table['rows']}, cols={table['cols']}, formulas={table['formula_count']}"
                )
    path = output_dir / "report.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def write_html(summary, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    numbers_summary = summary.get("numbers_summary") or {}
    gallery = ""
    if summary.get("contact_sheet"):
        gallery += f"<p><img src='{summary['contact_sheet']}' style='max-width:100%;border:1px solid #ccd;'></p>"
    if summary.get("native_preview"):
        gallery += f"<p><img src='{summary['native_preview']}' style='max-width:100%;border:1px solid #ccd;'></p>"
    numbers_html = ""
    if numbers_summary.get("sheets"):
        rows = []
        for sheet in numbers_summary["sheets"]:
            for table in sheet["tables"]:
                rows.append(
                    f"<tr><td>{sheet['sheet']}</td><td>{table['name']}</td><td>{table['rows']}</td><td>{table['cols']}</td><td>{table['formula_count']}</td></tr>"
                )
        numbers_html = (
            "<h2>Numbers tables</h2>"
            "<table border='1' cellspacing='0' cellpadding='6'>"
            "<tr><th>Sheet</th><th>Table</th><th>Rows</th><th>Cols</th><th>Formulas</th></tr>"
            + "".join(rows)
            + "</table>"
        )
    html = f"""<!doctype html>
<html><head><meta charset='utf-8'><title>iWork Package Report</title>
<style>
body {{ font-family: Georgia, serif; margin: 2rem; color: #18344c; background: #f7fafc; }}
h1,h2 {{ color: #114a72; }}
code {{ background: #eaf2f8; padding: 0.1rem 0.3rem; }}
.card {{ background: white; border: 1px solid #d7e2ea; border-radius: 12px; padding: 1rem 1.2rem; margin-bottom: 1rem; }}
table {{ background: white; border-collapse: collapse; width: 100%; }}
</style></head><body>
<h1>iWork Package Report</h1>
<div class='card'>
<p><strong>Input:</strong> <code>{summary['path']}</code></p>
<p><strong>Type:</strong> <code>{summary.get('package_type')}</code> |
<strong>Members:</strong> {summary.get('member_count', 0)} |
<strong>Images:</strong> {summary.get('image_asset_count', 0)} |
<strong>Equations:</strong> {summary.get('equation_pdf_count', 0)}</p>
<p><strong>Best preview method:</strong> {summary.get('native_preview_method', 'not requested')}</p>
</div>
<div class='card'>{gallery or '<p>No gallery assets generated.</p>'}</div>
<div class='card'><h2>Topic hints</h2><pre>{json.dumps(summary.get('topic_hints', {}), indent=2, ensure_ascii=True)}</pre></div>
<div class='card'><h2>Bundle metadata</h2><pre>{json.dumps(summary.get('bundle_metadata', {}), indent=2, ensure_ascii=True)}</pre></div>
<div class='card'><h2>Structure hints</h2><pre>{json.dumps(summary.get('structure_hints', {}), indent=2, ensure_ascii=True)}</pre></div>
{numbers_html}
</body></html>"""
    output_path.write_text(html)
    return output_path


def generate_native_preview(input_path, output_path):
    result = generate_preview(input_path, output_path, size=1800)
    if result.get("ok"):
        return result.get("preview_path"), result.get("native_error"), result.get("method")
    return None, result.get("native_error"), result.get("method")


def _payload_status_from_qa(qa):
    status = qa.get("status")
    if status in {"blocked", "fail"}:
        return status
    return "ok" if status == "ok" else "warning"


def _build_qa(summary):
    findings = []
    member_count = int(summary.get("member_count") or 0)
    image_count = int(summary.get("image_asset_count") or 0)
    equation_count = int(summary.get("equation_pdf_count") or 0)
    preview_count = len(summary.get("preview_files") or [])
    exported_count = len(summary.get("exported_assets") or [])
    if member_count == 0:
        findings.append(
            {
                "severity": "high",
                "title": "Empty iWork package",
                "detail": "The iWork ZIP has no members to inspect.",
            }
        )
    if preview_count == 0 and image_count == 0:
        findings.append(
            {
                "severity": "medium",
                "title": "No embedded preview assets",
                "detail": "No preview or image assets were found; layout and visual QA are limited.",
            }
        )
    numbers_summary = summary.get("numbers_summary") or {}
    if isinstance(numbers_summary, dict) and numbers_summary.get("error"):
        findings.append(
            {
                "severity": "low",
                "title": "Numbers parser warning",
                "detail": str(numbers_summary["error"]),
            }
        )
    if summary.get("native_preview_error"):
        findings.append(
            {
                "severity": "medium",
                "title": "Native preview unavailable",
                "detail": str(summary["native_preview_error"]),
            }
        )
    status = "warning" if findings else "ok"
    if any(finding["severity"] == "high" for finding in findings):
        status = "blocked"
    return {
        "status": status,
        "findings": findings,
        "metrics": {
            "member_count": member_count,
            "image_asset_count": image_count,
            "equation_pdf_count": equation_count,
            "preview_file_count": preview_count,
            "exported_asset_count": exported_count,
        },
    }


def _build_payload(args, summary, qa):
    out = Path(args.output_json) if args.output_json else Path(args.output_dir) / "summary.json"
    return build_tool_payload(
        "iwork_workbench",
        status=_payload_status_from_qa(qa),
        notes=[
            "iWork inspection is non-destructive and package-oriented; it does not guarantee a faithful editable roundtrip.",
        ],
        artifacts={
            "summary_json": str(out),
            "report_markdown": summary.get("report_markdown"),
            "member_manifest_csv": summary.get("member_manifest_csv"),
            "contact_sheet": summary.get("contact_sheet"),
            "native_preview": summary.get("native_preview"),
            "html_report": summary.get("html_report"),
        },
        results=summary,
        qa=qa,
        inputs=[args.input],
        legacy=summary,
    )


def _emit_blocked(args, message, *, error_type=None, input_path=None):
    summary = {
        "path": str(Path(input_path or args.input)),
        "package_type": Path(args.input).suffix.lower(),
        "error": message,
    }
    if error_type:
        summary["error_type"] = error_type
    qa = {
        "status": "blocked",
        "findings": [{"severity": "high", "title": "iWork inspection blocked", "detail": message}],
        "metrics": {"blocking_count": 1},
    }
    payload = _build_payload(args, summary, qa)
    emit_payload(payload, args.output_json)
    return 2


def write_member_manifest(input_path, output_dir):
    manifest_path = output_dir / "member_manifest.csv"
    with zipfile.ZipFile(input_path) as zf, manifest_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["member_path", "extension", "kind", "size_bytes"])
        writer.writeheader()
        for info in zf.infolist():
            member_path = info.filename
            extension = Path(member_path).suffix.lower() or "<none>"
            writer.writerow(
                {
                    "member_path": member_path,
                    "extension": extension,
                    "kind": classify_asset(member_path),
                    "size_bytes": info.file_size,
                }
            )
    return manifest_path


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()
    collision_status = _preflight_output_safety(args, input_path)
    if collision_status is not None:
        raise SystemExit(collision_status)
    if not input_path.exists():
        raise SystemExit(_emit_blocked(args, f"File not found: {input_path}", error_type="FileNotFoundError", input_path=input_path))
    if input_path.suffix.lower() not in IWORK_SUFFIXES:
        raise SystemExit(
            _emit_blocked(
                args,
                f"Unsupported iWork suffix {input_path.suffix.lower()!r}; expected one of .pages, .numbers, or .key.",
                error_type="UnsupportedFormat",
                input_path=input_path,
            )
        )
    if not zipfile.is_zipfile(input_path):
        raise SystemExit(_emit_blocked(args, f"Input is not a readable iWork ZIP package: {input_path}", error_type="BadZipFile", input_path=input_path))
    output_dir = Path(args.output_dir)
    if output_dir.exists() and not output_dir.is_dir():
        raise SystemExit(
            _emit_blocked(
                args,
                f"Output target exists and is not a directory: {output_dir}",
                error_type="NotADirectoryError",
                input_path=input_path,
            )
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        summary = extract_iwork_package(input_path, max_chars=4000, output_dir=output_dir, enable_ocr=args.enable_ocr)
    except zipfile.BadZipFile as exc:
        raise SystemExit(
            _emit_blocked(args, f"Input is not a readable iWork ZIP package: {input_path}", error_type=exc.__class__.__name__, input_path=input_path)
        ) from None
    except Exception as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or exc.__class__.__name__
        raise SystemExit(_emit_blocked(args, f"Could not inspect iWork package: {message}", error_type=exc.__class__.__name__, input_path=input_path)) from None
    summary["path"] = str(input_path.resolve())
    summary["topic_hints"] = topic_hints(summary.get("asset_name_hints", []))

    with zipfile.ZipFile(input_path) as zf:
        preview_targets = []
        for name in summary.get("preview_files", [])[:4]:
            target = output_dir / safe_output_name(name)
            if not target.exists():
                try:
                    target.write_bytes(zf.read(name))
                except Exception:
                    continue
            preview_targets.append(target)

    report_path = write_markdown(summary, output_dir)
    manifest_path = write_member_manifest(input_path, output_dir)
    html_path = None
    if args.contact_sheet:
        contact_sheet_path = Path(args.contact_sheet)
    else:
        contact_sheet_path = output_dir / "contact_sheet.png"
    if create_contact_sheet(preview_targets, contact_sheet_path):
        summary["contact_sheet"] = str(contact_sheet_path.resolve())
        print(f"Saved contact sheet: {contact_sheet_path.resolve()}")
    if args.native_preview:
        try:
            native_preview, native_error, preview_method = generate_native_preview(input_path, args.native_preview)
        except Exception as exc:
            native_preview = None
            preview_method = "native_preview"
            native_error = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or exc.__class__.__name__
        if native_preview:
            summary["native_preview"] = native_preview
            summary["native_preview_method"] = preview_method
            print(f"Saved preview: {native_preview}")
        if native_error:
            summary["native_preview_error"] = native_error
    summary["report_markdown"] = str(report_path.resolve())
    summary["member_manifest_csv"] = str(manifest_path.resolve())
    if args.html_report:
        html_path = write_html(summary, args.html_report)
        summary["html_report"] = str(html_path.resolve())

    print(f"iWork file: {input_path.resolve()}")
    print(f"package_type: {summary.get('package_type')}")
    print(f"member_count: {summary.get('member_count')}")
    print(f"image_asset_count: {summary.get('image_asset_count')}")
    print(f"equation_pdf_count: {summary.get('equation_pdf_count')}")
    build_history = summary.get("build_history", [])
    if isinstance(build_history, list) and build_history:
        print("build_history: " + json.dumps(build_history, ensure_ascii=True))
    if summary.get("bundle_metadata"):
        print("bundle_metadata: " + json.dumps(summary["bundle_metadata"], ensure_ascii=True))
    print("topic_hints: " + json.dumps(summary.get("topic_hints", {}), ensure_ascii=True))
    print(f"Saved report: {report_path.resolve()}")
    print(f"Saved manifest: {manifest_path.resolve()}")
    if html_path is not None:
        print(f"Saved HTML report: {html_path.resolve()}")

    if args.output_json:
        out = Path(args.output_json)
    else:
        out = output_dir / "summary.json"
    qa = _build_qa(summary)
    payload = _build_payload(args, summary, qa)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    print(f"Saved summary: {out.resolve()}")
    if args.manifest_json:
        outputs = [report_path, manifest_path, out]
        if summary.get("contact_sheet"):
            outputs.append(summary["contact_sheet"])
        if summary.get("native_preview"):
            outputs.append(summary["native_preview"])
        if html_path is not None:
            outputs.append(html_path)
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=outputs,
            parameters={"enable_ocr": args.enable_ocr},
            command="iwork_workbench.py",
            notes=["Generated non-destructive iWork inspection artifacts."],
        )
        print(f"Saved manifest: {Path(args.manifest_json).resolve()}")


if __name__ == "__main__":
    main()

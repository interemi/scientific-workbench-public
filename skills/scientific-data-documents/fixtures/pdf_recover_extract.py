#!/usr/bin/env python3
"""Recover text, images, and rough tables from scanned or low-quality PDFs."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.path_safety import find_output_input_collisions
from _internal.pdfium_backend import extract_pdf_images
from _internal.public_contract import build_tool_payload, emit_payload
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input PDF path.")
    parser.add_argument("--output-dir", required=True, help="Directory for extracted artifacts.")
    parser.add_argument("--summary-json", help="Optional summary JSON.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest.")
    return parser.parse_args()


def _emit_collision_only(input_path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing PDF recovery outputs that overlap the input PDF."
    payload = build_tool_payload(
        "pdf_recover_extract",
        status="blocked",
        notes=[message, "No recovery artifact, summary, or manifest was written."],
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
    outputs: list[tuple[str, Path | str | None]] = [
        ("--output-dir", output_dir),
        ("--summary-json", args.summary_json),
        ("--manifest-json", args.manifest_json),
        ("derived:ocr_layout.json", output_dir / "ocr_layout.json"),
        ("derived:ocr_layout.md", output_dir / "ocr_layout.md"),
    ]
    if output_dir.is_dir():
        outputs.extend(
            ("existing-output-member", item)
            for item in output_dir.rglob("*")
            if item.is_file()
        )
    collisions = find_output_input_collisions([("input", input_path)], outputs)
    return _emit_collision_only(input_path, collisions) if collisions else None


def load_dependencies():
    try:
        import pypdfium2
    except ImportError as exc:
        raise SystemExit(
            "pypdfium2 is not installed. Select the Full Python profile for PDF rendering."
        ) from exc
    try:
        import pdfplumber
    except ImportError as exc:
        raise SystemExit(
            "pdfplumber is not installed. Install requirements-full.txt or add pdfplumber to the active environment."
        ) from exc
    try:
        from _internal.ocr_utils import ocr_pdf
    except ImportError as exc:
        raise SystemExit(
            "OCR helpers are not available. Install the optional OCR stack from requirements-full.txt."
        ) from exc
    return pdfplumber, ocr_pdf


def extract_native_text(path, pdfplumber, max_pages=5):
    texts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:max_pages]:
            texts.append(page.extract_text() or "")
    return "\n\n".join(texts).strip()


def extract_page_images(path, output_dir, max_pages=5):
    return extract_pdf_images(path, output_dir, max_pages=max_pages)


def group_ocr_rows(items, y_tol=16):
    rows = []
    for item in items:
        box = item.get("box") or []
        if not box:
            continue
        center_y = sum(point[1] for point in box) / len(box)
        center_x = sum(point[0] for point in box) / len(box)
        text = item.get("text", "").strip()
        if not text:
            continue
        matched = False
        for row in rows:
            if abs(row["y"] - center_y) <= y_tol:
                row["items"].append((center_x, text))
                row["y_values"].append(center_y)
                row["y"] = sum(row["y_values"]) / len(row["y_values"])
                matched = True
                break
        if not matched:
            rows.append({"y": center_y, "y_values": [center_y], "items": [(center_x, text)]})
    structured = []
    for row in sorted(rows, key=lambda item: item["y"]):
        structured.append([text for _, text in sorted(row["items"], key=lambda item: item[0])])
    return structured


def save_ocr_tables(ocr_summary, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for page_index, page in enumerate(ocr_summary.get("pages", []), start=1):
        rows = group_ocr_rows(page.get("items", []))
        if len(rows) < 2:
            continue
        if max((len(row) for row in rows), default=0) < 2:
            continue
        target = output_dir / f"page_{page_index:02d}_ocr_table.csv"
        with target.open("w", newline="") as handle:
            csv_writer = csv.writer(handle)
            csv_writer.writerows(rows)
        outputs.append(str(target.resolve()))
    return outputs


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()
    collision_status = _preflight_output_safety(args, input_path)
    if collision_status is not None:
        raise SystemExit(collision_status)
    if not input_path.exists():
        raise SystemExit(f"File not found: {input_path}")
    ensure_datanalysis_runtime("pdf_recover_extract", strict=False)
    pdfplumber, ocr_pdf = load_dependencies()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    native_text = extract_native_text(input_path, pdfplumber)
    images = extract_page_images(input_path, output_dir / "figures")
    ocr_summary = ocr_pdf(input_path, output_dir / "ocr_pages", max_pages=5)
    ocr_tables = save_ocr_tables(ocr_summary, output_dir / "ocr_tables")
    layout_json = output_dir / "ocr_layout.json"
    layout_md = output_dir / "ocr_layout.md"
    layout_json.write_text(json.dumps(ocr_summary, indent=2, ensure_ascii=True) + "\n")
    page_blocks = []
    for page_index, page in enumerate(ocr_summary.get("pages", []), start=1):
        page_blocks.append(f"# Page {page_index}")
        for block in page.get("blocks", []):
            text = (block.get("text") or "").strip()
            if text:
                page_blocks.append(text)
                page_blocks.append("")
    layout_md.write_text("\n".join(page_blocks).strip() + "\n")

    summary = {
        "path": str(input_path.resolve()),
        "native_text_excerpt": native_text[:4000],
        "ocr_text_excerpt": (ocr_summary.get("text") or "")[:4000],
        "figure_count": len(images),
        "figures": images[:20],
        "ocr_table_exports": ocr_tables,
        "ocr_backend": "rapidocr",
        "ocr_page_count": len(ocr_summary.get("pages", [])),
        "ocr_layout_json": str(layout_json.resolve()),
        "ocr_layout_markdown": str(layout_md.resolve()),
    }
    payload = build_tool_payload(
        "pdf_recover_extract",
        status="ok",
        notes=[
            "Recovery output is heuristic: OCR text, image extraction, and table grouping should be reviewed before citation or reporting.",
        ],
        artifacts={
            "summary_json": args.summary_json,
            "ocr_layout_json": str(layout_json.resolve()),
            "ocr_layout_markdown": str(layout_md.resolve()),
        },
        results=summary,
        qa={
            "status": "ok",
            "findings": [],
            "metrics": {
                "figure_count": len(images),
                "ocr_page_count": len(ocr_summary.get("pages", [])),
                "ocr_table_export_count": len(ocr_tables),
            },
        },
        legacy=summary,
    )
    emit_payload(payload, args.summary_json)
    if args.summary_json:
        print(f"Saved summary: {Path(args.summary_json).resolve()}")
    if args.manifest_json:
        write_manifest(
            args.manifest_json,
            inputs=[input_path],
            outputs=images + ocr_tables + ocr_summary.get("rendered_images", []) + [layout_json, layout_md],
            parameters={"command": "pdf_recover_extract"},
        )
        print(f"Saved manifest: {Path(args.manifest_json).resolve()}")


if __name__ == "__main__":
    main()

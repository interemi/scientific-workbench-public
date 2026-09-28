#!/usr/bin/env python3
"""OCR and PDF rasterization helpers."""

import json
import subprocess
from pathlib import Path

from _internal.pdfium_backend import render_pdf_pages as render_selected_pdf_pages
from _internal.runtime_common import configure_runtime


def ensure_cache_dirs():
    return configure_runtime("ocr_utils")


def normalize_ocr_text(text):
    lines = []
    for raw in str(text).splitlines():
        line = " ".join(raw.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def box_center(box):
    return (
        sum(point[0] for point in box) / len(box),
        sum(point[1] for point in box) / len(box),
    )


def group_items_into_lines(items, y_tolerance=18):
    lines = []
    for item in items:
        box = item.get("box") or []
        if not box:
            continue
        text = normalize_ocr_text(item.get("text", ""))
        if not text:
            continue
        center_x, center_y = box_center(box)
        matched = None
        for line in lines:
            if abs(line["y"] - center_y) <= y_tolerance:
                matched = line
                break
        if matched is None:
            matched = {"y": center_y, "items": []}
            lines.append(matched)
        matched["items"].append({"x": center_x, "text": text, "confidence": item.get("confidence"), "box": box})
        matched["y"] = sum(entry["box"][0][1] for entry in matched["items"]) / len(matched["items"])
    normalized = []
    for line in sorted(lines, key=lambda entry: entry["y"]):
        ordered = sorted(line["items"], key=lambda entry: entry["x"])
        normalized.append(
            {
                "y": line["y"],
                "text": " ".join(entry["text"] for entry in ordered).strip(),
                "items": ordered,
            }
        )
    return normalized


def group_lines_into_blocks(lines, gap_tolerance=26):
    blocks = []
    current = []
    previous_y = None
    for line in lines:
        if previous_y is not None and abs(line["y"] - previous_y) > gap_tolerance and current:
            blocks.append({"lines": current, "text": "\n".join(item["text"] for item in current).strip()})
            current = []
        current.append(line)
        previous_y = line["y"]
    if current:
        blocks.append({"lines": current, "text": "\n".join(item["text"] for item in current).strip()})
    return blocks


def markdown_from_blocks(blocks):
    chunks = [block["text"] for block in blocks if block.get("text")]
    return "\n\n".join(chunks).strip()


def enrich_ocr_payload(payload):
    lines = group_items_into_lines(payload.get("items", []))
    blocks = group_lines_into_blocks(lines)
    payload["lines"] = lines
    payload["blocks"] = blocks
    payload["markdown"] = markdown_from_blocks(blocks)
    if not payload.get("text"):
        payload["text"] = normalize_ocr_text(payload["markdown"])
    return payload


def run_rapidocr(image_path):
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    result, _ = engine(str(image_path))
    items = []
    for entry in result or []:
        box, text, score = entry
        items.append(
            {
                "text": normalize_ocr_text(text),
                "confidence": float(score),
                "box": box,
            }
        )
    text = "\n".join(item["text"] for item in items if item["text"])
    return {"backend": "rapidocr", "items": items, "text": normalize_ocr_text(text)}


def run_apple_vision_binary(image_path):
    binary = Path(__file__).resolve().with_name("apple_vision_ocr_bin")
    if not binary.exists():
        return None
    result = subprocess.run([str(binary), str(image_path)], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except Exception:
        return None
    text = normalize_ocr_text(payload.get("text", ""))
    return {"backend": "apple_vision_bin", "items": payload.get("lines", []), "text": text}


def ocr_image(image_path):
    ensure_cache_dirs()
    errors = []
    for func in (run_rapidocr, run_apple_vision_binary):
        try:
            result = func(image_path)
            if result and result.get("text"):
                return enrich_ocr_payload(result)
        except Exception as exc:
            errors.append(f"{func.__name__}: {exc}")
    return enrich_ocr_payload({"backend": "none", "items": [], "text": "", "errors": errors})


def render_pdf_pages(pdf_path, output_dir, max_pages=3, zoom=2.0):
    output_dir = Path(output_dir)
    requests = [(number, output_dir / f"page_{number:02d}.png") for number in range(1, max_pages + 1)]
    return render_selected_pdf_pages(pdf_path, requests, scale=zoom)


def ocr_pdf(pdf_path, output_dir, max_pages=3):
    images = render_pdf_pages(pdf_path, output_dir, max_pages=max_pages)
    pages = []
    text_blocks = []
    for image in images:
        result = ocr_image(image)
        pages.append({"image": str(image.resolve()), **result})
        if result.get("markdown") or result.get("text"):
            text_blocks.append(result.get("markdown") or result["text"])
    return {
        "pages": pages,
        "text": normalize_ocr_text("\n\n".join(text_blocks)),
        "rendered_images": [str(path.resolve()) for path in images],
    }

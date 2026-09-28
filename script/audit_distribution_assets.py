#!/usr/bin/env python3
"""Inspect metadata and PDF text in reachable Git assets using the core environment."""

import argparse
import hashlib
import io
import json
from pathlib import Path

from audit_publication_history import ROOT, audit, git, scan_text


def inspect_assets(root=ROOT):
    # Import only when invoked with the prepared scientific core environment.
    from astropy.io import fits
    from PIL import Image
    from pypdf import PdfReader

    history = audit(root, history=True)
    records = []
    for item in history["binary_objects"]:
        data = git(root, "cat-file", "blob", item["object"])
        row = {**item, "sha256": hashlib.sha256(data).hexdigest(),
               "ownership": "not_established_by_metadata"}
        text = ""
        try:
            if data.startswith(b"%PDF"):
                reader = PdfReader(io.BytesIO(data))
                if reader.is_encrypted:
                    raise ValueError("encrypted PDF cannot be fully inspected")
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                metadata = dict(reader.metadata or {})
                text += "\n" + json.dumps(metadata, default=str)
                row.update(kind="pdf", pages=len(reader.pages), text_characters=len(text),
                           metadata_keys=sorted(metadata), attachment_count=len(reader.attachments),
                           has_open_action="/OpenAction" in reader.trailer["/Root"])
                if row["attachment_count"]:
                    row["manual_review"] = "embedded attachments are not inspected by this script"
            elif data.startswith(b"SIMPLE  ="):
                with fits.open(io.BytesIO(data), mode="readonly") as hdus:
                    row.update(kind="fits", hdus=[{
                        "shape": list(hdu.data.shape) if hdu.data is not None else None,
                        "dtype": str(hdu.data.dtype) if hdu.data is not None else None,
                    } for hdu in hdus])
                    text = "\n".join(str(hdu.header) for hdu in hdus)
            elif data.startswith(b"\x89PNG"):
                with Image.open(io.BytesIO(data)) as image:
                    row.update(kind="png", dimensions=list(image.size), metadata_keys=sorted(image.info))
                    text = json.dumps({"info": image.info, "exif": dict(image.getexif())}, default=str)
            else:
                row.update(kind="other", manual_review="binary format not parsed")
            secrets, _, privacy = scan_text(text.encode(), set(item["paths"]), item["object"], set())
            row.update(potential_secrets=secrets, privacy_findings=privacy,
                       extracted_text_sha256=hashlib.sha256(text.encode()).hexdigest())
        except Exception as error:
            # Preserve a failed-object record without exposing document contents.
            row["inspection_error"] = error.__class__.__name__
        records.append(row)
    return {"schema_version": 1, "head": history["head"], "commits": history["commits"],
            "scope": "Unique binary blobs in reachable commit trees; PDF text and metadata, FITS headers, PNG metadata",
            "limits": ["Metadata and synthetic-looking values do not prove ownership or redistribution rights.",
                       "No OCR, embedded attachment parsing, image interpretation or binary vulnerability scan.",
                       "Raw Git assets, historical reports and external datasets are never modified."],
            "objects": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.expanduser()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("choose a new output file outside the checkout")
    report = inspect_assets()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    counts = {"objects": len(report["objects"]),
              "inspection_errors": sum("inspection_error" in row for row in report["objects"]),
              "manual_reviews": sum("manual_review" in row for row in report["objects"]),
              "potential_secrets": sum(len(row.get("potential_secrets", [])) for row in report["objects"]),
              "privacy_findings": sum(len(row.get("privacy_findings", [])) for row in report["objects"])}
    print(json.dumps(counts))
    return int(bool(counts["inspection_errors"] or counts["potential_secrets"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ImportError) as error:
        raise SystemExit(f"Asset audit stopped: {error.__class__.__name__}; use the prepared core Python and a new output path.")

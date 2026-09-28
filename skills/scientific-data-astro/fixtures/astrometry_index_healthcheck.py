#!/usr/bin/env python3
"""Inspect a local Astrometry.net index directory and summarize obvious issues."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


INDEX_RE = re.compile(r"^index-(\d{4})(?:-(\d{2}))?\.fits$")


def portable_path(path: Path) -> str:
    home = Path.home()
    try:
        rel = path.expanduser().resolve().relative_to(home.resolve())
        return str(Path("~") / rel)
    except Exception:
        return str(path)


def scan_index_dir(index_dir: Path, suspicious_bytes: int) -> dict:
    fits_files = sorted(
        path for path in index_dir.iterdir() if path.is_file() and INDEX_RE.match(path.name)
    )
    series_counter: Counter[str] = Counter()
    suspicious_files = []
    largest_files = []
    latest_files = []

    total_bytes = 0
    for path in fits_files:
        match = INDEX_RE.match(path.name)
        if not match:
            continue
        series = match.group(1)
        series_counter[series] += 1
        stat = path.stat()
        total_bytes += stat.st_size
        if stat.st_size <= suspicious_bytes:
            suspicious_files.append(
                {
                    "path": portable_path(path),
                    "size_bytes": stat.st_size,
                    "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
        largest_files.append((stat.st_size, path))
        latest_files.append((stat.st_mtime, path, stat.st_size))

    largest_files.sort(reverse=True)
    latest_files.sort(reverse=True)

    recommendations = []
    if suspicious_files:
        recommendations.append(
            "Re-download the suspiciously tiny index FITS before trusting the local backend as fully clean."
        )
    else:
        recommendations.append(
            "No suspiciously tiny index FITS were detected in this directory."
        )
    recommendations.append(
        "Re-run this healthcheck after future index downloads, replacements, or directory reorganizations."
    )

    if "5200" not in series_counter and "5201" not in series_counter:
        recommendations.append(
            "For narrow direct-imaging fields, consider adding 5200-series LIGHT indexes."
        )

    return {
        "tool": "astrometry_index_healthcheck",
        "index_dir": portable_path(index_dir),
        "file_count": len(fits_files),
        "total_size_bytes": total_bytes,
        "total_size_gib": round(total_bytes / (1024 ** 3), 2),
        "series_counts": dict(sorted(series_counter.items())),
        "suspicious_small_file_threshold_bytes": suspicious_bytes,
        "suspicious_small_files": suspicious_files,
        "suspicious_small_file_count": len(suspicious_files),
        "largest_files": [
            {"path": portable_path(path), "size_bytes": size}
            for size, path in largest_files[:10]
        ],
        "latest_files": [
            {
                "path": portable_path(path),
                "size_bytes": size,
                "mtime_utc": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
            }
            for mtime, path, size in latest_files[:12]
        ],
        "recommendations": recommendations,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index_dir", help="Directory containing Astrometry.net index FITS files.")
    parser.add_argument(
        "--suspicious-bytes",
        type=int,
        default=4096,
        help="Flag files at or below this size as suspicious. Default: 4096.",
    )
    parser.add_argument("--summary-json", help="Optional path to write the JSON summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    index_dir = Path(args.index_dir).expanduser()
    if not index_dir.exists():
        raise SystemExit(f"Index directory not found: {index_dir}")
    if not index_dir.is_dir():
        raise SystemExit(f"Index path is not a directory: {index_dir}")

    summary = scan_index_dir(index_dir, suspicious_bytes=args.suspicious_bytes)
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.summary_json:
        out = Path(args.summary_json).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

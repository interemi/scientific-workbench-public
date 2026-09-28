#!/usr/bin/env python3
"""Inspect scientific container, archive, and serialized data formats safely."""

import argparse
import bz2
import gzip
import json
import lzma
import sqlite3
import tarfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

from _internal.datanalysis_bootstrap import ensure_datanalysis_runtime
from _internal.path_safety import canonical_path, find_output_input_collisions, paths_alias
from _internal.public_contract import build_tool_payload, emit_payload, resolve_output_path
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.run_bundle import add_run_bundle_argument, apply_run_bundle_defaults, finalize_existing_run_bundle


COMPRESSION_SUFFIXES = {".gz", ".bz2", ".xz"}


class UnsupportedContainerError(RuntimeError):
    """Raised when an existing file is outside this inspector's public scope."""


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Input container path.")
    parser.add_argument("--summary-json", help="Optional summary JSON using the standard top-level envelope.")
    parser.add_argument("--output-json", help="Optional output JSON path.")
    parser.add_argument("--manifest-json", help="Optional provenance manifest path.")
    add_run_bundle_argument(parser)
    return parser.parse_args()


def emit_collision_only(args, path: Path, collisions: list[dict[str, str]]) -> int:
    message = "Refusing unsafe or ambiguous container-inspection output paths."
    payload = build_tool_payload(
        "inspect_data_container",
        status="blocked",
        notes=[message, "No summary, manifest, or run-bundle file was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "path": public_path(path),
            "collisions": collisions,
        },
        qa={
            "status": "blocked",
            "findings": [message],
            "metrics": {"blocking_count": len(collisions)},
        },
        legacy={"blocked_reason": message, "collisions": collisions},
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def preflight_output_safety(args, path: Path) -> int | None:
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else None
    if args.summary_json and args.output_json and not paths_alias(args.summary_json, args.output_json):
        return emit_collision_only(
            args,
            path,
            [
                {
                    "flag": "--summary-json",
                    "input": "--output-json",
                    "input_path": str(canonical_path(args.output_json)),
                    "output_path": str(canonical_path(args.summary_json)),
                    "collision_kind": "ambiguous_fallback_aliases",
                }
            ],
        )
    summary_output = resolve_output_path(args.summary_json, args.output_json)
    outputs: list[tuple[str, Path | str | None]] = [
        ("--summary-json/--output-json", summary_output),
        ("--manifest-json", args.manifest_json),
        ("--run-dir", run_dir),
    ]
    if run_dir is not None:
        outputs.extend(
            (f"derived:{name}", run_dir / name)
            for name in ("summary.json", "manifest.json", "stdout.txt", "stderr.txt", "command.txt", "next_steps.md")
        )
    collisions = find_output_input_collisions([("path", path)], outputs)
    return emit_collision_only(args, path, collisions) if collisions else None


def array_summary(np, array):
    arr = np.asarray(array)
    summary = {"shape": list(arr.shape), "dtype": str(arr.dtype)}
    if arr.size and np.issubdtype(arr.dtype, np.number):
        finite = arr[np.isfinite(arr)] if np.issubdtype(arr.dtype, np.floating) else arr.reshape(-1)
        if finite.size:
            summary.update(
                {
                    "min": float(np.min(finite)),
                    "max": float(np.max(finite)),
                    "mean": float(np.mean(finite)),
                }
            )
    return summary


def optional_import(module_name, install_hint=None):
    try:
        return __import__(module_name)
    except ImportError as exc:
        hint = install_hint or module_name
        raise RuntimeError(f"Missing optional dependency '{module_name}' needed to inspect this file. Install '{hint}' to enable this format.") from exc


def preview_bytes(data):
    if not data:
        return {"preview_hex": "", "preview_text": ""}
    preview = data[:512]
    try:
        text = preview.decode("utf-8", "replace")
    except Exception:
        text = ""
    text = "".join(ch if ch.isprintable() or ch in "\n\t\r" else " " for ch in text).strip()
    return {"preview_hex": preview[:64].hex(), "preview_text": text[:240]}


def archive_path_issues(names):
    unsafe = []
    duplicates = []
    counts = Counter(names)
    for name, count in counts.items():
        if count > 1:
            duplicates.append(name)
    for name in names:
        normalized = name.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        if normalized.startswith("/") or ".." in parts:
            unsafe.append(name)
    warnings = []
    if unsafe:
        warnings.append(
            f"Archive contains {len(unsafe)} unsafe member path(s) with absolute or parent-directory traversal components; inspect before extraction."
        )
    if duplicates:
        warnings.append(f"Archive contains {len(duplicates)} duplicate member name(s); extraction order may overwrite files.")
    return warnings, unsafe[:20], duplicates[:20]


def attach_archive_findings(summary, names):
    warnings, unsafe, duplicates = archive_path_issues(names)
    if warnings:
        summary["archive_warnings"] = warnings
    if unsafe:
        summary["unsafe_members"] = unsafe
    if duplicates:
        summary["duplicate_members"] = duplicates
    return summary


def inspect_zip(path):
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        entries = []
        for info in zf.infolist()[:20]:
            entries.append(
                {
                    "name": info.filename,
                    "uncompressed_size": int(info.file_size),
                    "compressed_size": int(info.compress_size),
                }
            )
        return attach_archive_findings({"method": "zipfile", "entry_count": len(names), "entries": entries}, names)


def inspect_tar(path, mode):
    with tarfile.open(path, mode) as tf:
        all_members = tf.getmembers()
        members = []
        for member in all_members[:20]:
            members.append({"name": member.name, "size": int(member.size), "type": member.type.decode("ascii", "ignore")})
        return attach_archive_findings(
            {"method": "tarfile", "entry_count": len(all_members), "entries": members},
            [member.name for member in all_members],
        )


def inspect_stream(path, opener, method):
    try:
        with opener(path, "rb") as fh:
            preview = fh.read(512)
        summary = preview_bytes(preview)
        summary.update({"method": method, "compressed_size": int(Path(path).stat().st_size)})
    except Exception as exc:
        preview = Path(path).read_bytes()[:512]
        summary = preview_bytes(preview)
        summary.update({"method": f"{method}_recovered", "compressed_size": int(Path(path).stat().st_size), "recovery_error": str(exc)})
    return summary


def inspect_npy(path):
    import numpy as np

    array = np.load(path, allow_pickle=False)
    return {"method": "numpy", "arrays": {Path(path).name: array_summary(np, array)}}


def inspect_npz(path):
    import numpy as np

    bundle = np.load(path, allow_pickle=False)
    return {"method": "numpy", "arrays": {name: array_summary(np, bundle[name]) for name in bundle.files}}


def inspect_hdf5(path):
    h5py = optional_import("h5py")

    items = {}

    def visitor(name, obj):
        if isinstance(obj, h5py.Dataset):
            items[name] = {"kind": "dataset", "shape": list(obj.shape), "dtype": str(obj.dtype)}
        elif isinstance(obj, h5py.Group):
            items[name] = {"kind": "group"}

    with h5py.File(path, "r") as fh:
        fh.visititems(visitor)
    return {"method": "h5py", "items": dict(list(items.items())[:50])}


def inspect_mat(path):
    whosmat = optional_import("scipy.io").io.whosmat

    variables = {}
    for name, shape, dtype in whosmat(path):
        variables[name] = {"shape": list(shape), "dtype": str(dtype)}
    return {"method": "scipy_whosmat", "variables": variables}


def inspect_sqlite(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {}
        table_names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        for name in table_names[:20]:
            safe_name = name.replace('"', '""')
            cols = conn.execute(f'PRAGMA table_info("{safe_name}")').fetchall()
            count = conn.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
            tables[name] = {
                "row_count": int(count),
                "columns": [col[1] for col in cols],
            }
        return {"method": "sqlite3", "tables": tables}
    finally:
        conn.close()


def inspect_parquet_or_feather(path):
    pd = optional_import("pandas", install_hint="pandas pyarrow or fastparquet")

    suffix = Path(path).suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_feather(path)
    return {"method": "pandas", "rows": int(df.shape[0]), "columns": list(df.columns), "format": suffix}


def inspect_geojson(path):
    payload = json.loads(Path(path).read_text(errors="replace"))
    features = payload.get("features", []) if isinstance(payload, dict) else []
    geometry_types = Counter()
    sample_properties = []
    for feature in features[:20]:
        geometry = feature.get("geometry") or {}
        geometry_types[geometry.get("type", "Unknown")] += 1
        sample_properties.append(list((feature.get("properties") or {}).keys())[:10])
    return {
        "method": "geojson",
        "feature_count": len(features),
        "geometry_types": dict(geometry_types),
        "sample_property_keys": sample_properties[:5],
    }


def inspect_tiff(path):
    import tifffile

    with tifffile.TiffFile(path) as tif:
        series = []
        for item in tif.series[:8]:
            series.append({"shape": list(item.shape), "dtype": str(item.dtype), "axes": str(item.axes)})
        return {"method": "tifffile", "series_count": len(tif.series), "series": series}


def inspect_zarr(path):
    import zarr

    root = zarr.open(str(path), mode="r")
    arrays = {}

    def walk(group, prefix=""):
        for name, obj in group.members():
            full_name = f"{prefix}/{name}" if prefix else name
            if hasattr(obj, "shape") and hasattr(obj, "dtype"):
                arrays[full_name] = {"shape": list(obj.shape), "dtype": str(obj.dtype)}
            elif hasattr(obj, "members"):
                walk(obj, full_name)

    walk(root)
    return {"method": "zarr", "arrays": dict(list(arrays.items())[:40])}


def inspect_arrow_ipc(path):
    pyarrow = optional_import("pyarrow", install_hint="pyarrow")

    with pyarrow.memory_map(str(path), "r") as source:
        try:
            reader = pyarrow.ipc.open_file(source)
        except Exception:
            source.seek(0)
            reader = pyarrow.ipc.open_stream(source)
        schema = reader.schema
        row_count = 0
        for idx in range(reader.num_record_batches):
            row_count += reader.get_batch(idx).num_rows
        return {
            "method": "pyarrow_ipc",
            "rows": int(row_count),
            "columns": [field.name for field in schema],
        }


def inspect_netcdf(path):
    xr = optional_import("xarray")

    ds = xr.open_dataset(path)
    try:
        return {
            "method": "xarray",
            "dims": {key: int(value) for key, value in ds.sizes.items()},
            "data_vars": list(ds.data_vars),
            "coords": list(ds.coords),
        }
    finally:
        ds.close()


def detect_and_extract(path):
    suffixes = [item.lower() for item in path.suffixes]
    suffix = suffixes[-1] if suffixes else ""
    if len(suffixes) >= 2 and suffixes[-2:] == [".tar", ".gz"]:
        return inspect_tar(path, "r:gz")
    if len(suffixes) >= 2 and suffixes[-2:] == [".tar", ".bz2"]:
        return inspect_tar(path, "r:bz2")
    if len(suffixes) >= 2 and suffixes[-2:] == [".tar", ".xz"]:
        return inspect_tar(path, "r:xz")
    if suffix == ".npy":
        return inspect_npy(path)
    if suffix == ".npz":
        return inspect_npz(path)
    if suffix in {".h5", ".hdf5", ".hdf"}:
        return inspect_hdf5(path)
    if suffix == ".mat":
        return inspect_mat(path)
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return inspect_sqlite(path)
    if suffix in {".parquet", ".feather"}:
        return inspect_parquet_or_feather(path)
    if suffix == ".geojson":
        return inspect_geojson(path)
    if suffix in {".tif", ".tiff"}:
        return inspect_tiff(path)
    if suffix in {".arrow", ".ipc"}:
        return inspect_arrow_ipc(path)
    if suffix in {".nc", ".nc4", ".cdf", ".netcdf"}:
        return inspect_netcdf(path)
    if suffix == ".zarr":
        return inspect_zarr(path)
    if suffix == ".zip":
        return inspect_zip(path)
    if suffix == ".tar":
        return inspect_tar(path, "r:")
    if suffix == ".gz":
        return inspect_stream(path, gzip.open, "gzip_stream")
    if suffix == ".bz2":
        return inspect_stream(path, bz2.open, "bz2_stream")
    if suffix == ".xz":
        return inspect_stream(path, lzma.open, "xz_stream")
    raise UnsupportedContainerError(f"Unsupported container type: {suffix or '(none)'}")


def print_summary(path, summary):
    print(f"Container: {path.resolve()}")
    print(f"method: {summary['method']}")
    if "arrays" in summary:
        for name, item in summary["arrays"].items():
            print(f"- {name}: shape={tuple(item['shape'])}, dtype={item['dtype']}")
    if "items" in summary:
        for name, item in list(summary["items"].items())[:12]:
            print(f"- {name}: {json.dumps(item, ensure_ascii=True)}")
    if "variables" in summary:
        for name, item in list(summary["variables"].items())[:12]:
            print(f"- {name}: shape={tuple(item['shape'])}, dtype={item['dtype']}")
    if "tables" in summary:
        for name, item in list(summary["tables"].items())[:12]:
            print(f"- {name}: rows={item['row_count']}, columns={', '.join(item['columns'][:8])}")
    if "dims" in summary:
        print("dims: " + json.dumps(summary["dims"], ensure_ascii=True))
        print("data_vars: " + ", ".join(summary["data_vars"][:12]))
    if "geometry_types" in summary:
        print("geometry_types: " + json.dumps(summary["geometry_types"], ensure_ascii=True))
    if "series" in summary:
        for item in summary["series"][:8]:
            print(f"- series: {json.dumps(item, ensure_ascii=True)}")
    if "entries" in summary:
        for item in summary["entries"][:12]:
            print(f"- {json.dumps(item, ensure_ascii=True)}")
    if "archive_warnings" in summary:
        for warning in summary["archive_warnings"]:
            print(f"warning: {warning}")
    if "preview_text" in summary:
        if summary["preview_text"]:
            print("preview_text:")
            print(summary["preview_text"])
        print(f"preview_hex: {summary['preview_hex']}")


def build_failure_payload(args, path, status, message):
    summary_json_path = resolve_output_path(args.summary_json, args.output_json)
    return build_tool_payload(
        "inspect_data_container",
        status=status,
        notes=[message],
        artifacts={
            "summary_json": str(summary_json_path) if summary_json_path else None,
            "manifest_json": args.manifest_json,
        },
        results={"path": public_path(path), "error": message},
        qa={"status": status, "findings": [message], "metrics": {}},
    )


def emit_failure(args, path, status, message):
    payload = build_failure_payload(args, path, status, message)
    summary_json_path = resolve_output_path(args.summary_json, args.output_json)
    if summary_json_path:
        emit_payload(payload, summary_json_path)
    else:
        print(message)
    layout = getattr(args, "_run_bundle_layout", None)
    if layout is not None:
        finalize_existing_run_bundle(layout, payload, returncode=2)
    return 2


def output_parent_issue(raw_path, label):
    if not raw_path:
        return None
    parent = Path(raw_path).parent
    if parent.exists() and not parent.is_dir():
        return f"{label} parent exists but is not a directory: {parent}"
    return None


def main():
    args = parse_args()
    path = Path(args.path).expanduser()
    collision_status = preflight_output_safety(args, path)
    if collision_status is not None:
        return collision_status
    layout = apply_run_bundle_defaults(args)
    for label, raw_path in (("summary-json", resolve_output_path(args.summary_json, args.output_json)), ("manifest-json", args.manifest_json)):
        issue = output_parent_issue(raw_path, label)
        if issue:
            print(issue)
            return 2
    if not path.exists():
        return emit_failure(args, path, "blocked", f"File not found: {path}")
    ensure_datanalysis_runtime("inspect_data_container", strict=False)
    try:
        summary = detect_and_extract(path)
    except UnsupportedContainerError as exc:
        return emit_failure(args, path, "blocked", str(exc))
    except Exception as exc:
        summary = {"method": "recovery_fallback", "path": str(path.resolve()), "error": str(exc), **preview_bytes(path.read_bytes()[:512])}
    summary["path"] = str(path.resolve())
    print_summary(path, summary)
    summary_json_path = resolve_output_path(args.summary_json, args.output_json)
    notes = [
        "Use this inspection to understand container contents safely before deciding whether deeper extraction is worthwhile.",
    ]
    qa_findings = []
    if summary.get("method") == "recovery_fallback":
        qa_findings.append("The preferred structured reader failed and the inspector fell back to a raw-byte preview.")
    qa_findings.extend(summary.get("archive_warnings", []))
    payload = build_tool_payload(
        "inspect_data_container",
        status="warning" if qa_findings else "ok",
        notes=notes,
        artifacts={
            "summary_json": str(summary_json_path) if summary_json_path else None,
            "manifest_json": args.manifest_json,
        },
        results=summary,
        qa={
            "status": "warning" if qa_findings else "ok",
            "findings": qa_findings,
            "metrics": {"method": summary.get("method")},
        },
        legacy=summary,
    )
    if summary_json_path:
        out = Path(summary_json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        emit_payload(payload, out)
        print(f"Saved summary: {public_path(out)}")
    if args.manifest_json:
        outputs = [summary_json_path] if summary_json_path else []
        write_manifest(args.manifest_json, inputs=[path], outputs=outputs, parameters={"method": summary["method"]})
        print(f"Saved manifest: {public_path(args.manifest_json)}")
    if layout is not None:
        finalize_existing_run_bundle(layout, payload, returncode=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

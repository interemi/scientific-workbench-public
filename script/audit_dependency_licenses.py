#!/usr/bin/env python3
"""Index notice files in hash-verified dependency archives without extracting or executing them."""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import zipfile

from check_core_lock import ROOT

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_NOTICE_BYTES = 2 * 1024 * 1024


def notice_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("unsafe member name in dependency archive")
    return any(word in part.lower() for part in path.parts
               for word in ("license", "licence", "copying", "notice"))


def notice_record(name, stream, size):
    if size > MAX_NOTICE_BYTES:
        raise ValueError(f"notice exceeds inspection limit: {name}")
    data = stream.read(MAX_NOTICE_BYTES + 1)
    if len(data) != size:
        raise ValueError(f"invalid notice size: {name}")
    return {"member": name, "bytes": size, "sha256": hashlib.sha256(data).hexdigest()}


def inspect_archive(path, expected_hash):
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("dependency archive exceeds inspection limit")
    with path.open("rb") as stream:
        data = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("dependency archive exceeds inspection limit")
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("dependency archive hash differs from reviewed inventory")
    notices = []
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                candidate = notice_name(member.filename)
                if candidate and not member.is_dir():
                    if stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG):
                        raise ValueError("notice is a link or special member")
                    with archive.open(member) as stream:
                        notices.append(notice_record(member.filename, stream, member.file_size))
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive:
                candidate = notice_name(member.name)
                if candidate and not member.isdir():
                    if not member.isfile():
                        raise ValueError("notice is a link or special member")
                    with archive.extractfile(member) as stream:
                        notices.append(notice_record(member.name, stream, member.size))
    else:
        raise ValueError("unsupported dependency archive format")
    if len({n["member"] for n in notices}) != len(notices):
        raise ValueError("duplicate notice member names")
    return sorted(notices, key=lambda n: n["member"])


def inventory_records(root=ROOT):
    unique = {}
    for file, groups, profile in [
        ("core-wheel-inventory.json", ["runtime_packages"], "core"),
        ("full-package-inventory.json", ["runtime_packages", "build_packages"], "full"),
    ]:
        inventory = json.loads((root / "distribution" / file).read_text())
        for group in groups:
            for record in inventory[group]:
                filename = record.get("filename", record.get("wheel"))
                if not filename or Path(filename).name != filename or "\\" in filename:
                    raise ValueError("invalid dependency archive filename")
                key = (filename, record["sha256"])
                if key not in unique:
                    unique[key] = {"name": record["name"], "version": record["version"],
                                   "filename": filename, "sha256": record["sha256"], "profiles": []}
                unique[key]["profiles"].append(f"{profile}:{group}")
    return sorted(unique.values(), key=lambda r: (r["name"].lower(), r["version"]))


def audit(directories, root=ROOT):
    records = inventory_records(root)
    errors = []
    for record in records:
        try:
            candidates = [d / record["filename"] for d in directories if (d / record["filename"]).is_file()]
            if not candidates:
                raise ValueError("archive missing; download the reviewed filename before inspection")
            # A conflicting local copy must be investigated, not silently skipped.
            notices = [inspect_archive(path, record["sha256"]) for path in candidates]
            record["notices"] = notices[0]
            record["archive_verified"] = True
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
            record["archive_verified"] = False
            errors.append({"filename": record["filename"], "error": str(error)})
    return {"schema_version": 1, "technical_status": "PASS" if not errors else "FAIL",
            "license_review_complete": False,
            "scope": "Archive hashes and named notice files only; no legal interpretation, permission grant or complete vendored-component audit",
            "archive_count": len(records), "notice_count": sum(len(r.get("notices", [])) for r in records),
            "without_named_notices": [r["filename"] for r in records if r.get("archive_verified") and not r.get("notices")],
            "errors": errors, "packages": records}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives-dir", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    output = args.output.expanduser().absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("choose a new evidence file outside the checkout")
    directories = [p.expanduser().resolve() for p in args.archives_dir]
    if not all(p.is_dir() for p in directories):
        raise ValueError("each archive directory must exist")
    report = audit(directories)
    with output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("technical_status", "license_review_complete", "archive_count", "notice_count", "without_named_notices")}))
    return 0 if report["technical_status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Dependency notice audit stopped: {error}")

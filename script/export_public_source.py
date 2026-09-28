#!/usr/bin/env python3
"""Create a reviewable, history-free source snapshot from an exact Git commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCLUSIONS = ROOT / "distribution/public-source-exclusions.txt"
PROVENANCE_NAME = "SOURCE_PROVENANCE.json"
DOCUMENTATION_MAP = "distribution/public-documentation-map.json"
PRIVATE_CODE_PATH_MAP = "distribution/private-code-path-map.json"
SKILL_MANIFEST = "distribution/skill-manifest.json"
DOCUMENTATION_SUFFIXES = {".md", ".markdown", ".rst", ".txt", ".tex", ".pdf"}
ALLOWED_MODES = {"100644", "100755", "120000"}


class ExportError(RuntimeError):
    """Raised when a source snapshot cannot be created safely."""


def git(root: Path, *arguments: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if text else result.stderr.decode(errors="replace").strip()
        raise ExportError(f"git {' '.join(arguments)} failed: {stderr}")
    return result.stdout


def repository_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise ExportError(f"invalid exclusion path: {value!r}")
    parts = PurePosixPath(normalized.rstrip("/")).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ExportError(f"invalid exclusion path: {value!r}")
    return "/".join(parts) + ("/" if normalized.endswith("/") else "")


def load_exclusions(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    if not path.is_file():
        raise ExportError(f"exclusion file is missing: {path}")
    return parse_exclusions(path.read_text(encoding="utf-8"))


def parse_exclusions(text: str) -> tuple[str, ...]:
    exclusions: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        exclusions.append(repository_path(line))
    if len(exclusions) != len(set(exclusions)):
        raise ExportError("exclusion file contains duplicate paths")
    return tuple(sorted(exclusions))


def is_excluded(path: str, exclusions: tuple[str, ...]) -> bool:
    return any(
        path == exclusion
        or (exclusion.endswith("/") and path.startswith(exclusion))
        for exclusion in exclusions
    )


def tracked_entries(root: Path, commit: str) -> list[tuple[str, str, str]]:
    raw = git(root, "ls-tree", "-r", "-z", "--full-tree", commit, text=False)
    entries: list[tuple[str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        if kind != "blob" or mode not in ALLOWED_MODES:
            raise ExportError(
                f"unsupported Git entry for {raw_path.decode(errors='replace')}: {mode} {kind}"
            )
        path = raw_path.decode("utf-8")
        repository_path(path)
        entries.append((mode, object_id, path))
    return sorted(entries, key=lambda item: item[2])


def ensure_safe_destination(root: Path, output: Path) -> tuple[Path, Path]:
    source = root.resolve()
    requested = output.expanduser()
    if requested.exists() or requested.is_symlink():
        raise ExportError(f"output already exists and will not be overwritten: {requested}")
    destination = requested.resolve()
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ExportError("output must be outside the private repository")
    if not destination.parent.is_dir():
        raise ExportError(f"output parent does not exist: {destination.parent}")
    return source, destination


def validate_symlink(destination_root: Path, destination: Path, target: str) -> None:
    if not target or os.path.isabs(target):
        raise ExportError(f"unsafe symlink target for {destination.name}: {target!r}")
    resolved = (destination.parent / target).resolve(strict=False)
    try:
        resolved.relative_to(destination_root)
    except ValueError as error:
        raise ExportError(
            f"symlink would escape the public snapshot: {destination.name} -> {target}"
        ) from error


def prepare_documentation_editions(
    source: Path,
    entries: list[tuple[str, str, str]],
    retained: list[tuple[str, str, str]],
) -> tuple[dict[str, bytes], dict[str, dict], str | None]:
    """Read reviewed replacements from the selected commit, never the worktree."""
    indexed = {path: (mode, object_id) for mode, object_id, path in entries}
    if DOCUMENTATION_MAP not in indexed:
        return {}, {}, None
    retained_paths = {path for _, _, path in retained}

    def read_document(path: str) -> bytes:
        if path not in retained_paths or indexed[path][0] != "100644":
            raise ExportError(f"documentation must be a retained, non-executable regular file: {path}")
        return git(source, "cat-file", "blob", indexed[path][1], text=False)

    mapping_bytes = read_document(DOCUMENTATION_MAP)
    try:
        mapping = json.loads(mapping_bytes)
    except (ValueError, UnicodeError) as error:
        raise ExportError("invalid documentation mapping JSON") from error
    if (not isinstance(mapping, dict) or mapping.get("schema_version") != 1
            or not isinstance(mapping.get("replacements"), list)):
        raise ExportError("unsupported documentation mapping schema")

    replacements: dict[str, bytes] = {}
    provenance: dict[str, dict] = {}
    for record in mapping["replacements"]:
        if not isinstance(record, dict):
            raise ExportError("documentation replacement must be an object")
        path, edition = record.get("path"), record.get("edition")
        if not isinstance(path, str) or not isinstance(edition, str):
            raise ExportError("documentation replacement paths must be strings")
        if repository_path(path) != path or repository_path(edition) != edition:
            raise ExportError("documentation replacement paths must be canonical")
        if (not path.startswith("skills/") or not edition.startswith("docs/")
                or Path(path).suffix.lower() not in DOCUMENTATION_SUFFIXES
                or Path(edition).suffix.lower() != Path(path).suffix.lower()):
            raise ExportError(f"replacement must map skill documentation to a matching docs edition: {path}")
        if path in replacements:
            raise ExportError(f"duplicate documentation replacement: {path}")
        if not isinstance(record.get("reason"), str) or not record["reason"].strip():
            raise ExportError(f"documentation replacement needs a review reason: {path}")
        original, translated = read_document(path), read_document(edition)
        original_hash = hashlib.sha256(original).hexdigest()
        edition_hash = hashlib.sha256(translated).hexdigest()
        if original_hash != record.get("source_sha256"):
            raise ExportError(f"original documentation hash differs from reviewed mapping: {path}")
        if edition_hash != record.get("edition_sha256"):
            raise ExportError(f"English edition hash differs from reviewed mapping: {edition}")
        replacements[path] = translated
        provenance[path] = {
            "kind": "english_documentation_edition",
            "source_sha256": original_hash,
            "edition": edition,
            "edition_sha256": edition_hash,
            "reason": record["reason"],
        }

    if replacements:
        original_manifest = read_document(SKILL_MANIFEST)
        try:
            manifest = json.loads(original_manifest)
            if (manifest.get("schema_version") != 1
                    or not isinstance(manifest.get("files"), dict)
                    or "publication_documentation" in manifest):
                raise ValueError("unsupported or already transformed skill manifest")
            for path, blob in replacements.items():
                relative = path.removeprefix("skills/")
                record = manifest["files"][relative]
                if (record.get("kind") != "file" or record.get("executable") is not False
                        or record.get("sha256") != provenance[path]["source_sha256"]):
                    raise ValueError(f"original manifest does not match documentation: {path}")
                record["sha256"] = hashlib.sha256(blob).hexdigest()
                record["size"] = len(blob)
            manifest["publication_documentation"] = {
                "source_manifest_sha256": hashlib.sha256(original_manifest).hexdigest(),
                "mapping_sha256": hashlib.sha256(mapping_bytes).hexdigest(),
                "replacements": [{"path": path, **details} for path, details in sorted(provenance.items())],
            }
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ExportError(f"cannot derive the public skill manifest: {error}") from error
        replacements[SKILL_MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        provenance[SKILL_MANIFEST] = {
            "kind": "derived_skill_manifest",
            "source_sha256": hashlib.sha256(original_manifest).hexdigest(),
            "mapping_sha256": hashlib.sha256(mapping_bytes).hexdigest(),
        }
    return replacements, provenance, hashlib.sha256(mapping_bytes).hexdigest()


def prepare_code_path_editions(
    source: Path,
    entries: list[tuple[str, str, str]],
    retained: list[tuple[str, str, str]],
) -> tuple[dict[str, bytes], dict[str, dict], str | None]:
    """Apply exact, reviewed path edits to archived fixtures in the export only."""
    indexed = {path: (mode, object_id) for mode, object_id, path in entries}
    if PRIVATE_CODE_PATH_MAP not in indexed:
        return {}, {}, None
    retained_paths = {path for _, _, path in retained}
    if PRIVATE_CODE_PATH_MAP in retained_paths or indexed[PRIVATE_CODE_PATH_MAP][0] != "100644":
        raise ExportError("private code path policy must be a regular, excluded file")
    mapping_bytes = git(source, "cat-file", "blob", indexed[PRIVATE_CODE_PATH_MAP][1], text=False)
    try:
        mapping = json.loads(mapping_bytes)
    except (ValueError, UnicodeError) as error:
        raise ExportError("invalid private code path mapping JSON") from error
    if (not isinstance(mapping, dict) or mapping.get("schema_version") != 1
            or not isinstance(mapping.get("replacements"), list)):
        raise ExportError("unsupported private code path mapping schema")

    replacements: dict[str, bytes] = {}
    provenance: dict[str, dict] = {}
    for record in mapping["replacements"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ExportError("private code path replacement must name a file")
        path = record["path"]
        if (repository_path(path) != path or not path.startswith("skills/")
                or "/fixtures/" not in path or not path.endswith(".py")
                or path not in retained_paths or indexed[path][0] not in {"100644", "100755"}):
            raise ExportError(f"private code path replacement is outside reviewed fixtures: {path}")
        if path in replacements:
            raise ExportError(f"duplicate private code path replacement: {path}")
        if not isinstance(record.get("reason"), str) or not record["reason"].strip():
            raise ExportError(f"private code path replacement needs a review reason: {path}")
        changes = record.get("changes")
        if not isinstance(changes, list) or not changes:
            raise ExportError(f"private code path replacement needs exact edits: {path}")
        original = git(source, "cat-file", "blob", indexed[path][1], text=False)
        original_hash = hashlib.sha256(original).hexdigest()
        if original_hash != record.get("source_sha256"):
            raise ExportError(f"private code source hash differs from reviewed mapping: {path}")
        try:
            edition = original.decode("utf-8")
        except UnicodeError as error:
            raise ExportError(f"private code source is not UTF-8: {path}") from error
        for change in changes:
            if (not isinstance(change, dict) or not isinstance(change.get("from"), str)
                    or not isinstance(change.get("to"), str) or not change["from"]
                    or change["from"] == change["to"]
                    or type(change.get("count")) is not int or change["count"] < 1
                    or edition.count(change["from"]) != change["count"]):
                raise ExportError(f"private code edit does not match reviewed source: {path}")
            edition = edition.replace(change["from"], change["to"])
        translated = edition.encode("utf-8")
        edition_hash = hashlib.sha256(translated).hexdigest()
        if edition_hash != record.get("edition_sha256"):
            raise ExportError(f"private code edition hash differs from reviewed mapping: {path}")
        try:
            compile(edition, path, "exec")
        except SyntaxError as error:
            raise ExportError(f"private code edition does not parse: {path}") from error
        replacements[path] = translated
        provenance[path] = {
            "kind": "portable_historical_fixture",
            "source_sha256": original_hash,
            "edition_sha256": edition_hash,
            "reason": record["reason"],
        }
    return replacements, provenance, hashlib.sha256(mapping_bytes).hexdigest()


def export_repository(
    root: Path,
    output: Path,
    *,
    source_ref: str = "HEAD",
    exclusions_file: Path | None = None,
) -> dict[str, object]:
    source, destination = ensure_safe_destination(root, output)
    if git(source, "status", "--porcelain", "--untracked-files=all").strip():
        raise ExportError("the private repository is dirty; commit or preserve changes before export")

    commit = git(source, "rev-parse", "--verify", f"{source_ref}^{{commit}}").strip()
    tree = git(source, "rev-parse", f"{commit}^{{tree}}").strip()
    entries = tracked_entries(source, commit)
    exclusion_evidence = None
    if exclusions_file is None:
        exclusions = ()
    else:
        requested_policy = exclusions_file.expanduser().absolute()
        # Resolve parent aliases such as macOS /var -> /private/var, while
        # preserving the final entry so tracked symlink policies are rejected.
        canonical_policy = requested_policy.parent.resolve() / requested_policy.name
        try:
            policy_path = canonical_policy.relative_to(source).as_posix()
        except ValueError:
            policy_path = None
        if policy_path is not None:
            policy_entries = [(mode, oid) for mode, oid, path in entries if path == policy_path]
            if not policy_entries or policy_entries[0][0] != "100644":
                raise ExportError("exclusion policy must be a regular file in the selected commit")
            policy_bytes = git(source, "cat-file", "blob", policy_entries[0][1], text=False)
            exclusion_evidence = {"origin": "source_commit", "path": policy_path}
        else:
            try:
                policy_bytes = canonical_policy.read_bytes()
            except OSError as error:
                raise ExportError(f"cannot read external exclusion policy: {error}") from error
            exclusion_evidence = {"origin": "external_reviewed_file"}
        try:
            exclusions = parse_exclusions(policy_bytes.decode("utf-8"))
        except UnicodeError as error:
            raise ExportError("exclusion policy must contain UTF-8 text") from error
        exclusion_evidence["sha256"] = hashlib.sha256(policy_bytes).hexdigest()
    retained = [entry for entry in entries if not is_excluded(entry[2], exclusions)]
    excluded = [entry[2] for entry in entries if is_excluded(entry[2], exclusions)]
    if not retained:
        raise ExportError("the exclusion set would produce an empty snapshot")
    if any(path == PROVENANCE_NAME for _, _, path in retained):
        raise ExportError(f"tracked file conflicts with generated {PROVENANCE_NAME}")
    editions, transformations, mapping_hash = prepare_documentation_editions(source, entries, retained)
    code_editions, code_transformations, code_map_hash = prepare_code_path_editions(
        source, entries, retained
    )
    if code_editions:
        indexed = {path: object_id for _, object_id, path in entries}
        original_manifest = git(source, "cat-file", "blob", indexed[SKILL_MANIFEST], text=False)
        manifest_bytes = editions.get(SKILL_MANIFEST, original_manifest)
        try:
            manifest = json.loads(manifest_bytes)
            if manifest.get("schema_version") != 1 or "publication_code_paths" in manifest:
                raise ValueError("unsupported or already transformed skill manifest")
            for path, blob in code_editions.items():
                record = manifest["files"][path.removeprefix("skills/")]
                if record.get("kind") != "file" or record.get("sha256") != code_transformations[path]["source_sha256"]:
                    raise ValueError(f"original manifest does not match historical fixture: {path}")
                record["sha256"] = hashlib.sha256(blob).hexdigest()
                record["size"] = len(blob)
            manifest["publication_code_paths"] = {
                "mapping_sha256": code_map_hash,
                "replacements": [
                    {"path": path, **details} for path, details in sorted(code_transformations.items())
                ],
            }
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ExportError(f"cannot derive portable historical fixtures: {error}") from error
        editions.update(code_editions)
        transformations.update(code_transformations)
        editions[SKILL_MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        transformations[SKILL_MANIFEST] = {
            "kind": "derived_skill_manifest",
            "source_sha256": hashlib.sha256(original_manifest).hexdigest(),
            "documentation_mapping_sha256": mapping_hash,
            "code_path_mapping_sha256": code_map_hash,
        }

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    manifest_entries: list[dict[str, object]] = []
    try:
        for mode, object_id, relative in retained:
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            blob = editions.get(relative)
            if blob is None:
                blob = git(source, "cat-file", "blob", object_id, text=False)
            digest = hashlib.sha256(blob).hexdigest()
            if mode == "120000":
                link_target = blob.decode("utf-8")
                validate_symlink(temporary.resolve(), target, link_target)
                target.symlink_to(link_target)
                manifest_entries.append(
                    {
                        "path": relative,
                        "mode": mode,
                        "sha256": digest,
                        "target": link_target,
                    }
                )
                continue

            target.write_bytes(blob)
            target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            if mode == "100755":
                target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            manifest_entries.append(
                {
                    "path": relative,
                    "mode": mode,
                    "sha256": digest,
                    "bytes": len(blob),
                }
            )
            if relative in transformations:
                manifest_entries[-1]["transformation"] = transformations[relative]

        provenance: dict[str, object] = {
            "schema_version": 2 if transformations else 1,
            "product": "Scientific Workbench",
            "source_commit": commit,
            "source_tree": tree,
            "tracked_entries": len(entries),
            "exported_entries": len(manifest_entries),
            "excluded_paths": excluded,
            "files": manifest_entries,
        }
        if mapping_hash is not None:
            provenance["documentation_map_sha256"] = mapping_hash
        if code_map_hash is not None:
            provenance["private_code_path_map_sha256"] = code_map_hash
        if exclusion_evidence is not None:
            provenance["exclusion_policy"] = exclusion_evidence
        (temporary / PROVENANCE_NAME).write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-ref", default="HEAD")
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS)
    args = parser.parse_args()

    try:
        report = export_repository(
            ROOT,
            args.output,
            source_ref=args.source_ref,
            exclusions_file=args.exclusions,
        )
    except ExportError as error:
        parser.error(str(error))

    print(
        "Scientific Workbench public source snapshot created: "
        f"{args.output.expanduser().resolve()} "
        f"({report['exported_entries']} entries from {report['source_commit']})"
    )
    print("No Git repository, remote, release, or upload was created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

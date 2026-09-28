#!/usr/bin/env python3
"""Inventory public documentation and enforce the final publication language gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


TEXT_SUFFIXES = {".md", ".markdown", ".rst", ".tex"}
PLAIN_TEXT_DOC_NAME = re.compile(
    r"(?:readme|release|changelog|changes|install|contributing|authors|news|security)"
    r"(?:[._-].*)?", re.IGNORECASE,
)
BINARY_DOC_SUFFIXES = {".pdf"}
IGNORED_PARTS = {".git", ".build", "dist", "tmp", "__pycache__"}
THIRD_PARTY_NAMES = {"license", "license.txt", "license.md", "notice", "notice.txt"}
ACTIVE_USER_DOCS = {
    "README.md",
    "INSTALL.md",
    "CONTRIBUTING.md",
    "Guides/Scientific_Workbench_User_Guide.md",
    "docs/CAPABILITY_SETUP_MATRIX.md",
    "docs/CAPABILITY_VALIDATION_EVIDENCE.md",
    "docs/OPTIONAL_BACKENDS.md",
    "docs/WORKFLOW_REQUIREMENTS.md",
    "docs/TROUBLESHOOTING.md",
    "docs/SOURCE_DISTRIBUTION_BOUNDARY.md",
}

SPANISH_WORDS = {
    "abrir", "antes", "archivo", "archivos", "carpeta", "como", "comprueba",
    "con", "cuando", "datos", "de", "debe", "desde", "despues", "donde",
    "ejecuta", "ejecutar", "el", "en", "esta", "este", "falta", "guia",
    "hacer", "instalacion", "la", "las", "los", "mantener", "no", "para",
    "paso", "pero", "por", "puede", "que", "resultado", "resultados", "revisa",
    "se", "si", "sin", "solo", "tambien", "una", "usar", "usuario", "y",
}
ENGLISH_WORDS = {
    "a", "after", "and", "app", "before", "can", "check", "data", "do",
    "file", "files", "for", "from", "if", "in", "install", "is", "it",
    "must", "not", "of", "on", "only", "or", "output", "review", "run",
    "should", "the", "this", "to", "use", "user", "when", "with", "without",
    "workflow", "you",
}


def candidate_paths(root: Path) -> list[Path]:
    command = [
        "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
    ]
    output = subprocess.check_output(command, cwd=root)
    paths: list[Path] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8", errors="strict"))
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        paths.append(relative)
    return sorted(set(paths), key=lambda path: path.as_posix())


def is_third_party_legal_text(path: Path) -> bool:
    return path.name.lower() in THIRD_PARTY_NAMES or path.name.lower().startswith("license.")


def is_text_documentation(path: Path) -> bool:
    if is_third_party_legal_text(path):
        return False
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    if path.suffix.lower() == ".txt" and path.parts[0] == "docs":
        return True
    return (
        path.suffix.lower() in {"", ".txt"}
        and PLAIN_TEXT_DOC_NAME.fullmatch(path.name) is not None
    )


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return text


def language_evidence(text: str) -> dict[str, int | bool]:
    prose = strip_code(text).lower()
    words = re.findall(r"[a-záéíóúüñ]+", prose)
    spanish_score = sum(word in SPANISH_WORDS for word in words)
    english_score = sum(word in ENGLISH_WORDS for word in words)
    spanish_marks = len(re.findall(r"[áéíóúüñ¿¡]", prose))
    likely_spanish = (
        spanish_score >= 12 and spanish_score >= max(12, int(english_score * 0.75))
    ) or (spanish_marks >= 8 and spanish_score >= 6)
    return {
        "spanish_score": spanish_score,
        "english_score": english_score,
        "spanish_marks": spanish_marks,
        "likely_spanish": likely_spanish,
    }


def markdown_links(path: Path, text: str) -> list[str]:
    if path.suffix.lower() not in {".md", ".markdown"}:
        return []
    return re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)


def broken_links(root: Path, relative: Path, text: str) -> list[str]:
    broken: list[str] = []
    for raw_target in markdown_links(relative, text):
        target = raw_target.strip().strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if not target or any(marker in target for marker in ("${", "{{", "<path", "/path/to/")):
            continue
        resolved = (root / relative.parent / unquote(target)).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            broken.append(raw_target)
            continue
        if not resolved.exists():
            broken.append(raw_target)
    return broken


def pdf_groups(
    root: Path,
    binary_docs: list[Path],
    all_paths: set[Path],
) -> list[dict[str, object]]:
    grouped: dict[str, list[Path]] = {}
    for relative in binary_docs:
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        grouped.setdefault(digest, []).append(relative)

    groups: list[dict[str, object]] = []
    for digest, members in sorted(grouped.items()):
        members = sorted(members, key=lambda path: path.as_posix())
        tex_sources = sorted(
            {member.with_suffix(".tex") for member in members if member.with_suffix(".tex") in all_paths},
            key=lambda path: path.as_posix(),
        )
        groups.append({
            "sha256": digest,
            "pdfs": [member.as_posix() for member in members],
            "tex_sources": [source.as_posix() for source in tex_sources],
            "representative": members[0],
        })
    return groups


def review_pdf_language(root: Path, groups: list[dict[str, object]]) -> tuple[list[dict], list[dict]]:
    if not groups:
        return [], []
    swift = shutil.which("swift")
    extractor = root / "script/extract_pdf_text.swift"
    if swift is None:
        return [], [{"error": "Swift is unavailable; PDF language could not be reviewed"}]
    if not extractor.is_file():
        return [], [{"error": "script/extract_pdf_text.swift is missing"}]

    representatives = [group["representative"] for group in groups]
    result = subprocess.run(
        [swift, str(extractor), *(str(root / relative) for relative in representatives)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown Swift error"
        return [], [{"error": f"PDF text extraction failed: {detail}"}]

    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return [], [{"error": f"PDF text extractor returned invalid JSON: {error}"}]
    by_path = {Path(record["path"]).resolve(): record for record in records}
    spanish: list[dict] = []
    unreadable: list[dict] = []
    for group in groups:
        representative = group["representative"]
        record = by_path.get((root / representative).resolve())
        public_group = {
            "sha256": group["sha256"],
            "pdfs": group["pdfs"],
            "tex_sources": group["tex_sources"],
        }
        if record is None:
            unreadable.append({**public_group, "error": "PDF extractor omitted this document"})
            continue
        if record.get("error"):
            unreadable.append({**public_group, "error": record["error"]})
            continue
        evidence = language_evidence(record.get("text", ""))
        if evidence["likely_spanish"]:
            spanish.append({**public_group, **evidence})
    return spanish, unreadable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-english", action="store_true")
    parser.add_argument("--strict-links", action="store_true")
    parser.add_argument("--strict-portability", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    paths = candidate_paths(root)
    path_set = set(paths)
    text_docs = [path for path in paths if is_text_documentation(path)]
    binary_docs = [path for path in paths if path.suffix.lower() in BINARY_DOC_SUFFIXES]

    spanish_candidates: list[dict[str, object]] = []
    portable_path_findings: list[dict[str, object]] = []
    broken_link_findings: list[dict[str, object]] = []
    unsafe_user_guidance: list[dict[str, object]] = []

    for relative in text_docs:
        text = (root / relative).read_text(encoding="utf-8", errors="replace")
        evidence = language_evidence(text)
        if evidence["likely_spanish"]:
            spanish_candidates.append({"path": relative.as_posix(), **evidence})

        local_matches = sorted(set(re.findall(r"/(?:Users|var/folders)/[^\s)`'\"]+", text)))
        if local_matches:
            portable_path_findings.append({
                "path": relative.as_posix(),
                "matches": local_matches[:20],
            })

        missing = broken_links(root, relative, text)
        if missing:
            broken_link_findings.append({"path": relative.as_posix(), "targets": missing})

        if relative.as_posix() in ACTIVE_USER_DOCS and "danger-full-access" in text:
            unsafe_user_guidance.append({
                "path": relative.as_posix(),
                "term": "danger-full-access",
            })

    grouped_pdfs = pdf_groups(root, binary_docs, path_set)
    pdf_without_tex_source = [
        pdf
        for group in grouped_pdfs if not group["tex_sources"]
        for pdf in group["pdfs"]
    ]
    spanish_pdf_groups: list[dict] = []
    unreadable_pdf_groups: list[dict] = []
    if args.require_english:
        spanish_pdf_groups, unreadable_pdf_groups = review_pdf_language(root, grouped_pdfs)

    report = {
        "text_documents": len(text_docs),
        "binary_documents": len(binary_docs),
        "likely_spanish_documents": len(spanish_candidates),
        "portable_path_documents": len(portable_path_findings),
        "broken_link_documents": len(broken_link_findings),
        "unsafe_active_guidance": len(unsafe_user_guidance),
        "pdf_without_tex_source": len(pdf_without_tex_source),
        "unique_pdf_documents": len(grouped_pdfs),
        "likely_spanish_pdf_groups": len(spanish_pdf_groups),
        "unreadable_pdf_groups": len(unreadable_pdf_groups),
        "spanish_candidates": spanish_candidates,
        "portable_path_findings": portable_path_findings,
        "broken_link_findings": broken_link_findings,
        "unsafe_user_guidance_findings": unsafe_user_guidance,
        "pdf_without_tex_source_paths": pdf_without_tex_source,
        "pdf_source_groups": [
            {
                "sha256": group["sha256"],
                "pdfs": group["pdfs"],
                "tex_sources": group["tex_sources"],
            }
            for group in grouped_pdfs
        ],
        "spanish_pdf_findings": spanish_pdf_groups,
        "unreadable_pdf_findings": unreadable_pdf_groups,
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    failures: list[str] = []
    if args.require_english and spanish_candidates:
        failures.append(f"{len(spanish_candidates)} documents are likely Spanish")
    if args.strict_links and broken_link_findings:
        failures.append(f"{len(broken_link_findings)} documents contain broken local links")
    if args.strict_portability and portable_path_findings:
        failures.append(f"{len(portable_path_findings)} documents contain local absolute paths")
    if args.strict_portability and unsafe_user_guidance:
        failures.append(f"{len(unsafe_user_guidance)} active user documents contain unsafe guidance")
    if args.require_english and pdf_without_tex_source:
        failures.append(
            f"{len(pdf_without_tex_source)} PDFs have no tracked TeX source for language review"
        )
    if args.require_english and spanish_pdf_groups:
        failures.append(f"{len(spanish_pdf_groups)} unique PDF contents are likely Spanish")
    if args.require_english and unreadable_pdf_groups:
        failures.append(
            f"{len(unreadable_pdf_groups)} unique PDF contents could not be language-reviewed"
        )

    if failures:
        print("public documentation audit failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

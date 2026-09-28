#!/usr/bin/env python3
"""Compare coursework notebook/product branches without executing notebooks.

This is a lightweight inventory tool for group practicals where several people
or branches produce related notebooks, FITS, PNG, HTML, and report assets. It
does not judge the science; it makes missing, duplicated, and inconsistent
products visible before building a poster or presentation.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from _internal.path_safety import find_output_input_collisions
from _internal.provenance_utils import public_path, sanitize_payload
from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload


PRODUCT_EXTENSIONS = {
    ".fits",
    ".fit",
    ".fts",
    ".fz",
    ".png",
    ".jpg",
    ".jpeg",
    ".html",
    ".htm",
    ".ipynb",
    ".pdf",
    ".csv",
    ".ecsv",
    ".txt",
    ".dat",
}

DEFAULT_BRANCH_TOKENS = {"a", "c", "e", "m", "l", "edu"}
FILTER_TOKENS = {"u", "b", "v", "r", "i", "g", "z", "y", "j", "h", "k", "ha", "halpha", "hbeta", "oiii", "sii", "nii"}
TECHNIQUE_TOKENS = {
    "astrometry",
    "photometry",
    "fotometria",
    "quicklook",
    "diagnostic",
    "diagnostico",
    "profile",
    "lightcurve",
    "spectrum",
    "spectra",
    "bpt",
    "sfr",
    "metallicity",
    "poster",
    "presentation",
    "presentacion",
}
GENERIC_TOKENS = {
    "output",
    "outputs",
    "result",
    "results",
    "resultante",
    "prellamada",
    "final",
    "copy",
    "copia",
    "version",
    "branch",
    "rama",
    "figure",
    "fig",
    "figura",
    "image",
    "plot",
    "plots",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Root folder containing branch folders or suffixed products.")
    parser.add_argument("--branch-token", action="append", default=[], help="Known branch/suffix token. Repeat as needed.")
    parser.add_argument("--output-dir", help="Optional directory for CSV/Markdown outputs.")
    parser.add_argument("--summary-json", help="Optional JSON output.")
    return parser.parse_args()


def emit_collision_only(args: argparse.Namespace, collisions: list[dict[str, str]]) -> int:
    message = "Refusing branch-comparison outputs that overlap the input product tree."
    payload = build_blocked_payload(
        "notebook_branch_compare",
        message,
        notes=[message, "No inventory, report, or summary was written."],
        artifacts={},
        results={
            "blocked_reason": message,
            "error_type": "output_input_collision",
            "root": args.root,
            "collisions": collisions,
        },
        inputs=[args.root],
    )
    print(json.dumps(sanitize_payload(payload), indent=2, ensure_ascii=True))
    return 2


def preflight_output_safety(args: argparse.Namespace) -> int | None:
    outputs: list[tuple[str, Path | str | None]] = [
        ("--output-dir", args.output_dir),
        ("--summary-json", args.summary_json),
    ]
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
        outputs.extend(
            (f"derived:{name}", output_dir / name)
            for name in (
                "branch_product_inventory.csv",
                "branch_summary.csv",
                "equivalent_products.csv",
                "candidate_figures.md",
            )
        )
    collisions = find_output_input_collisions([("root", args.root)], outputs)
    return emit_collision_only(args, collisions) if collisions else None


def emit_blocked(args: argparse.Namespace, message: str, error_type: str | None = None) -> int:
    payload = build_blocked_payload(
        "notebook_branch_compare",
        message,
        notes=[
            "Lightweight coursework branch comparison; it inventories products and does not execute notebooks or judge scientific correctness.",
            "The comparison did not modify branch products; fix the blocking path or output problem and rerun.",
        ],
        artifacts={"summary_json": args.summary_json, "output_dir": args.output_dir},
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "root": args.root,
            "branch_tokens": args.branch_token,
        },
        inputs=[args.root],
    )
    emit_payload(payload, args.summary_json)
    return 2


def split_tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^A-Za-z0-9]+", text.lower()) if token]


def normalize_key(parts: list[str], branch_tokens: set[str]) -> str:
    tokens: list[str] = []
    for part in parts:
        tokens.extend(split_tokens(part))
    stripped = []
    for idx, token in enumerate(tokens):
        if token in branch_tokens and (idx == len(tokens) - 1 or len(token) <= 3):
            continue
        if token in GENERIC_TOKENS:
            continue
        stripped.append(token)
    return "_".join(stripped) or "unclassified"


def product_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".fits", ".fit", ".fts", ".fz"}:
        return "fits"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "figure"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".ipynb":
        return "notebook"
    if suffix == ".pdf":
        return "pdf"
    return "table_or_text"


def immediate_branch_tokens(root: Path) -> set[str]:
    tokens = set(DEFAULT_BRANCH_TOKENS)
    for item in root.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            tokens.add(item.name.lower())
    return tokens


def infer_branch(path: Path, root: Path, branch_tokens: set[str]) -> tuple[str, Path]:
    rel = path.relative_to(root)
    if len(rel.parts) > 1 and (root / rel.parts[0]).is_dir():
        return rel.parts[0], Path(*rel.parts[1:])
    tokens = split_tokens(path.stem)
    if tokens:
        tail = tokens[-1]
        if tail in branch_tokens:
            return tail, rel
    return "unbranched", rel


def hints_for_key(key: str) -> dict:
    tokens = key.split("_")
    year = next((token for token in tokens if re.fullmatch(r"(19|20)\d{2}", token)), None)
    filt = next((token for token in tokens if token in FILTER_TOKENS), None)
    technique = next((token for token in tokens if token in TECHNIQUE_TOKENS), None)
    object_tokens = [token for token in tokens if token not in FILTER_TOKENS and token not in TECHNIQUE_TOKENS and token != year]
    return {
        "object_hint": "_".join(object_tokens[:4]) or None,
        "filter_hint": filt,
        "year_hint": year,
        "technique_hint": technique,
    }


def discover_products(root: Path, branch_tokens: set[str]) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        if suffix not in PRODUCT_EXTENSIONS:
            continue
        branch, branch_rel = infer_branch(path, root, branch_tokens)
        key = normalize_key(list(branch_rel.parent.parts) + [branch_rel.stem], branch_tokens)
        hints = hints_for_key(key)
        row = {
            "branch": branch,
            "relative_path": str(path.relative_to(root)),
            "normalized_key": key,
            "extension": suffix,
            "product_type": product_type(path),
            "size_bytes": path.stat().st_size,
            "candidate_figure": suffix in {".png", ".jpg", ".jpeg"},
            **hints,
        }
        rows.append(row)
    return rows


def build_equivalence(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    branches = sorted({row["branch"] for row in rows})
    by_key: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_key[row["normalized_key"]].append(row)

    equivalents = []
    candidates = []
    expected_pairs = {(row["normalized_key"], row["product_type"]) for row in rows}
    for key, products in sorted(by_key.items()):
        by_branch: dict[str, list[dict]] = defaultdict(list)
        for product in products:
            by_branch[product["branch"]].append(product)
        missing = [branch for branch in branches if branch not in by_branch]
        expected_product_types = sorted({product["product_type"] for product in products})
        missing_type_notes = []
        for branch in branches:
            branch_product_types = {item["product_type"] for item in by_branch.get(branch, [])}
            missing_product_types = [kind for kind in expected_product_types if kind not in branch_product_types]
            if missing_product_types:
                missing_type_notes.append(f"{branch}:{'/'.join(missing_product_types)}")
        duplicate_branches = []
        for branch, items in by_branch.items():
            type_counts_for_branch = Counter(item["product_type"] for item in items)
            if any(count > 1 for count in type_counts_for_branch.values()):
                duplicate_branches.append(branch)
        type_counts = Counter(product["product_type"] for product in products)
        figure_products = [product for product in products if product["candidate_figure"]]
        equivalents.append(
            {
                "normalized_key": key,
                "branches_present": ",".join(sorted(by_branch)),
                "missing_branches": ",".join(missing),
                "missing_product_types": ";".join(missing_type_notes),
                "duplicate_branches": ",".join(sorted(duplicate_branches)),
                "product_count": len(products),
                "product_types": ",".join(f"{kind}:{count}" for kind, count in sorted(type_counts.items())),
                "candidate_figure_count": len(figure_products),
                **hints_for_key(key),
            }
        )
        for product in figure_products:
            candidates.append(
                {
                    "branch": product["branch"],
                    "normalized_key": key,
                    "relative_path": product["relative_path"],
                    "branch_coverage": len(by_branch),
                    "missing_branch_count": len(missing),
                    "reason": "figure product with equivalent products in other branches" if len(by_branch) > 1 else "figure product with no branch peer",
                }
            )

    branch_rows = []
    total_keys = len(by_key)
    for branch in branches:
        branch_products = [row for row in rows if row["branch"] == branch]
        present_keys = {row["normalized_key"] for row in branch_products}
        branch_pairs = {(row["normalized_key"], row["product_type"]) for row in branch_products}
        duplicate_keys = []
        for key in present_keys:
            type_counts_for_key = Counter(row["product_type"] for row in branch_products if row["normalized_key"] == key)
            if any(count > 1 for count in type_counts_for_key.values()):
                duplicate_keys.append(key)
        type_counts = Counter(row["product_type"] for row in branch_products)
        missing_count = max(0, total_keys - len(present_keys))
        missing_pair_count = max(0, len(expected_pairs) - len(branch_pairs))
        score = len(branch_pairs) - 0.5 * len(duplicate_keys) - 0.25 * missing_pair_count - 0.25 * missing_count
        branch_rows.append(
            {
                "branch": branch,
                "file_count": len(branch_products),
                "key_count": len(present_keys),
                "missing_key_count": missing_count,
                "missing_product_type_count": missing_pair_count,
                "duplicate_key_count": len(duplicate_keys),
                "consistency_score": round(score, 3),
                "product_types": ",".join(f"{kind}:{count}" for kind, count in sorted(type_counts.items())),
            }
        )
    branch_rows.sort(key=lambda row: (-row["consistency_score"], -row["key_count"], row["branch"]))
    candidates.sort(key=lambda row: (-row["branch_coverage"], row["missing_branch_count"], row["relative_path"]))
    return branch_rows, equivalents, candidates


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_candidate_markdown(path: Path, candidates: list[dict], branch_rows: list[dict]) -> None:
    lines = ["# Candidate Scientific Figures", ""]
    if branch_rows:
        best = branch_rows[0]
        lines.append(
            f"Most consistent branch by coverage/duplicates heuristic: `{best['branch']}` "
            f"(score {best['consistency_score']}, {best['key_count']} keys, "
            f"{best['missing_key_count']} missing keys, {best['duplicate_key_count']} duplicate keys)."
        )
        lines.append("")
    if not candidates:
        lines.append("No figure-like products were found.")
    for item in candidates[:30]:
        lines.append(
            f"- `{item['relative_path']}` [{item['branch']}] -> `{item['normalized_key']}`; {item['reason']}."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    collision_status = preflight_output_safety(args)
    if collision_status is not None:
        raise SystemExit(collision_status)
    try:
        root = Path(args.root).expanduser()
        if not root.exists() or not root.is_dir():
            raise SystemExit(f"Root folder not found or not a directory: {root}")
        branch_tokens = immediate_branch_tokens(root) | {token.lower() for token in args.branch_token}
        rows = discover_products(root, branch_tokens)
        branch_rows, equivalents, candidates = build_equivalence(rows)

        output_dir = Path(args.output_dir).expanduser() if args.output_dir else None
        artifacts = {}
        if output_dir:
            inventory_csv = output_dir / "branch_product_inventory.csv"
            branch_csv = output_dir / "branch_summary.csv"
            equivalence_csv = output_dir / "equivalent_products.csv"
            candidates_md = output_dir / "candidate_figures.md"
            write_csv(inventory_csv, rows)
            write_csv(branch_csv, branch_rows)
            write_csv(equivalence_csv, equivalents)
            write_candidate_markdown(candidates_md, candidates, branch_rows)
            artifacts.update(
                {
                    "inventory_csv": inventory_csv,
                    "branch_summary_csv": branch_csv,
                    "equivalent_products_csv": equivalence_csv,
                    "candidate_figures_md": candidates_md,
                }
            )
    except SystemExit as exc:
        if isinstance(exc.code, int):
            raise
        raise SystemExit(emit_blocked(args, str(exc.code), error_type="SystemExit")) from None
    except Exception as exc:
        raise SystemExit(emit_blocked(args, f"{exc.__class__.__name__}: {exc}", error_type=exc.__class__.__name__)) from None

    best_branch = branch_rows[0] if branch_rows else None
    findings = []
    missing_groups = [row for row in equivalents if row["missing_branches"]]
    missing_product_type_groups = [row for row in equivalents if row["missing_product_types"]]
    duplicate_groups = [row for row in equivalents if row["duplicate_branches"]]
    if missing_groups:
        findings.append(f"{len(missing_groups)} product groups are missing in at least one branch.")
    if missing_product_type_groups:
        findings.append(f"{len(missing_product_type_groups)} product groups are missing product types in at least one branch.")
    if duplicate_groups:
        findings.append(f"{len(duplicate_groups)} product groups have branch-local duplicates.")
    if not rows:
        findings.append("No notebook/FITS/PNG/HTML coursework products were found.")

    summary = {
        "root": public_path(root),
        "branch_tokens": sorted(branch_tokens),
        "branch_summary": branch_rows,
        "equivalent_products": equivalents,
        "candidate_figures": candidates[:50],
        "best_branch": best_branch,
        "product_count": len(rows),
        "branch_count": len(branch_rows),
        "equivalence_group_count": len(equivalents),
        "missing_group_count": len(missing_groups),
        "missing_product_type_group_count": len(missing_product_type_groups),
        "duplicate_group_count": len(duplicate_groups),
    }
    status = "warning" if findings else "ok"
    payload = build_tool_payload(
        "notebook_branch_compare",
        status=status,
        notes=[
            "Lightweight coursework branch comparison; it inventories products and does not execute notebooks or judge scientific correctness.",
            "Use the best_branch result as a coverage heuristic, not as an automatic scientific winner.",
        ],
        artifacts={**artifacts, "summary_json": args.summary_json},
        results=summary,
        qa={
            "status": status,
            "findings": findings,
            "metrics": {
                "product_count": len(rows),
                "branch_count": len(branch_rows),
                "equivalence_group_count": len(equivalents),
                "missing_group_count": len(missing_groups),
                "missing_product_type_group_count": len(missing_product_type_groups),
                "duplicate_group_count": len(duplicate_groups),
            },
        },
        legacy=summary,
    )
    emit_payload(payload, args.summary_json)


if __name__ == "__main__":
    main()

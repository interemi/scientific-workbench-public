# Coursework Notebook Branch Comparison

Use this when a group practical has several parallel notebook or product branches and the immediate question is not "execute everything", but "which branch/product set is most coherent enough to feed a poster, talk, or report?".

Typical layouts include folders named by people, branches, or work states, and products with suffixes such as `A`, `C`, `e`, `m`, `l`, or `EDU`. The route must stay general: do not hardcode a university, practice title, object list, or user path.

## First Pass

1. Work on a copy or read-only inventory. Do not edit notebooks or decks during comparison.
2. Inventory `.ipynb`, FITS, PNG/JPG, HTML, PDF, CSV/ECSV, and plain derived tables.
3. Treat immediate subfolders as branch candidates.
4. Treat suffixes such as `_A`, `_C`, `_EDU`, or user-provided `--branch-token` values as branch hints when files live together.
5. Normalize product keys by removing branch tokens and generic words such as `output`, `result`, `figure`, `plot`, `copy`, or `final`.

## Recommended Command

```bash
python scripts/notebook_branch_compare.py /path/to/coursework-products \
  --branch-token A --branch-token C --branch-token EDU \
  --output-dir branch-compare \
  --summary-json branch-compare/summary.json
```

The tool emits:

- `branch_product_inventory.csv`: one row per product.
- `branch_summary.csv`: branch-level coverage, duplicates, and consistency score.
- `equivalent_products.csv`: product groups with present/missing branches.
- `candidate_figures.md`: PNG/JPG candidates for slides, posters, or oral explanation.
- `summary.json`: standard `tool/status/results/qa` payload.

## What To Look For

- **Missing outputs**: a branch has the notebook but not the PNG/HTML/FITS product, or vice versa.
- **Duplicated outputs**: a branch has several products with the same normalized key.
- **Equivalent products**: same object/filter/year/technique appears across branches. Treat this as a candidate equivalence only; for slide-ready figures, confirm the visual intent with `references/coursework-figure-equivalents.md`.
- **Candidate figures**: scientific PNG/JPG outputs with peers in other branches are usually better presentation material than slide screenshots.
- **Most consistent branch**: use the reported branch as a coverage heuristic, not as a scientific verdict.

## Before Rebuilding A Figure

Branch comparison can say that two products look related; it cannot prove that one is the exact visual equivalent of the other.

Before generating a same-figure/different-object output, check:

- source notebook and cell/function, for example `comparar_fits`;
- source FITS, PNG, RGB product, or HTML output;
- whether the figure is detected sources, SDSS calibrators, reduced image, final RGB, diagnostic crop, or another intent;
- visual mode and exceptions: do not assume all products should be viridis;
- crop, scale, `origin`, overlays, and annotations;
- slide destination and position code if the product feeds a deck.

## Acceptance Criteria

A useful comparison report should answer:

- which branches exist;
- which products appear to be equivalent;
- what is missing or duplicated;
- which figures are realistic candidates for poster/talk use;
- which branch looks most complete and what evidence supports that claim.

## What Not To Do

- Do not execute every notebook just to compare branch coverage.
- Do not infer scientific correctness from file completeness.
- Do not collapse everyone else's work into the user's personal scope.
- Do not hardcode practice-specific folder names; use them only as observed labels in the inventory.

# Astro-Born Transferable Patterns

> English publication edition of a preserved private record at `d6583f1`.
> Original source: `skills/scientific-data-astro/.cache/archived_references/references/astro-transferable-patterns.md`.
> Original SHA-256: `1796c6a9ea1e0da30e181bd0d6b389d252f083c8cd5aadd3989a891246fc98ce`.
> Historical states and results are unchanged; this edition does not rerun them.
> Machine-specific paths use `$PRIVATE_WORKSPACE` (the original editable
> workspace) and `$HOME` aliases. Where shown, set `RUNS_DIR` to a fresh output
> root before reproducing a historical command; preserve earlier evidence.
> Original documents remain unchanged privately.

Use this v1.7 note when a capability was born in astronomy, but the user is asking whether its pattern can help with a non-astronomy problem.

The rule is conservative: transfer patterns, not false promises. If the CLI still speaks RA/Dec, FITS, WCS, Systemic, or visual RGB FITS, keep that contract visible.

## Decisions By Capability

| Capability | Strict domain part | Reusable pattern | v1.7 decision |
|---|---|---|---|
| `catalog_workbench.py crossmatch-sky` | RA/Dec-like spherical coordinates, angular radius in arcsec, nearest-neighbour sky semantics. | Tolerance-based coordinate crossmatch with explicit matched/unmatched counts and manifest. | Adapt with limits for lon/lat-like spherical coordinate cases; not a full GIS engine. |
| `fits_rgb_batch.py` | FITS image inventory, `OBJECT`/`FILTER` grouping, WCS/phase alignment, RGB/pseudo-RGB astronomy conventions. | Multichannel image product with channel mapping, alignment QA, run summary, and preserved sources. | Document pattern only unless the non-astro instrument already stores channels in FITS with compatible metadata. |
| `rgb_visual_fits_export.py` | Display-only RGB FITS convention for rendered astronomy products. | Reproducible RGB image container with RGB cube, channel extensions, before/after comparison, and manifest. | Adapt with limits for traceable display archives; never treat as calibrated data. |
| `astrometry_net_workbench.py preflight` | Astrometry.net readiness, celestial WCS hints, solve suitability for sky images. | Preflight before expensive/optional backend execution. | Do not generalize the solver; reuse the preflight idea and let non-imaging inputs warn or block. |
| `radial_velocity_workbench.py validate-manifest` | Systemic/RV report manifest with RV datasets, figures, fit metrics, planets, and conclusions. | Manual-analysis manifest validation before rendering a report. | Document pattern only; do not advertise as a generic manifest validator. |
| `presentation_workbench.py existing-deck-style-audit` | Scientific figure geometry, provenance, visual QA, and handoff constraints. | Visual style audit, editability-risk scan, constraints, and asset manifest for copied decks. | Adapt with limits for professional deck QA/handoff. |

## Pattern: Crossmatch With Tolerance

`catalog_workbench.py crossmatch-sky` can be useful outside astronomy only when the coordinates truly behave like angular coordinates on a sphere:

- longitude-like values in `[0, 360)` degrees
- latitude-like values in `[-90, 90]` degrees
- an angular tolerance that can honestly be expressed in arcseconds

It is not a GIS system. It does not know coordinate reference systems, projected units, polygons, addresses, floor plans, road distance, or nearest route.

## Pattern: Multichannel Image Products

`fits_rgb_batch.py` and `rgb_visual_fits_export.py` are useful as patterns for traceable visual products:

- preserve sources
- write a machine-readable run summary
- record channel mapping
- record alignment method or the absence of alignment
- emit visual QA and manifests
- label display-only outputs as display-only

The boundary matters. If a non-astro project starts from ordinary PNG/JPEG files, use ordinary image tooling. If it starts from FITS-like instrument channels, this route can help as long as the report says the FITS RGB output is a visual product, not calibrated science.

## Pattern: Preflight Before Backend

`astrometry_net_workbench.py preflight` should remain astrometry-specific. The transferable idea is the gate:

- inspect inputs before invoking an external or expensive backend
- infer whether backend execution is plausible
- emit `ok`, `warning`, or `blocked`
- preserve a report/manifest explaining the decision

For non-astro work, copy that behavior in docs or workflow design. Do not send arbitrary images to Astrometry.net just because they are images.

## Pattern: Manifest Before Handoff

`radial_velocity_workbench.py validate-manifest` is useful as a manifest checklist pattern:

- required source references
- required figures
- scalar fit metrics
- conclusions and caveats
- warning list before report generation

But it is still an RV-shaped manifest. For general reports, use it as an example of how to design validation, not as a universal schema.

## Pattern: Visual QA And Style Handoff

`presentation_workbench.py existing-deck-style-audit` can support professional or personal decks because it works on copied deck files and produces:

- slide text
- constraints
- reusable slide templates
- visual/editability warnings
- scientific or technical asset manifests

The output may still use scientific vocabulary because the workbench was born for figure handoff. Keep that visible rather than pretending it is a full presentation design system.

## v1.7 Gate

The maintained phase regression is:

```bash
python3 scripts/audit_v1_7_phase3_astro_transfer_patterns_regression.py \
  --output-dir "${RUNS_DIR:?Set RUNS_DIR to a fresh output root}/v1_7_phase3_astro_transfer_patterns"
```

It covers crossmatch, multichannel FITS rendering, display-only RGB FITS export, astrometry preflight as a negative gate, RV manifest validation as a pattern, and deck-style visual QA.

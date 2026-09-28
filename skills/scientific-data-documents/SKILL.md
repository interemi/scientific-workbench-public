---
name: scientific-data-documents
description: Use when working with scientific or professional documents, reports, PDFs, Office/iWork decks, LaTeX, semantic diffs, handoff bundles, and write-up review. Do not use for raw table, notebook, or astronomy-data analysis unless a document workflow is involved.
---

# Scientific Data Documents

This child skill owns document and reporting workflows for the modular
scientific-data-analysis family.

v2.8 keeps this child as an independent ScientificWorkbench skill root for
document/reporting capabilities. App consumers must resolve its compact
`public_surface_registry.yaml` through `canonical_registry` and execute document
capabilities from this root when ownership points here. Output collision and
self-ingestion guards are current release invariants.

Use it for copied document intake, PDF recovery, DOCX round trips, iWork and
Keynote preflight/export paths, presentation inspection, LaTeX scaffolding or
review, scientific write-up critique, deliverable scaffolds, and semantic diffs.

## Safety

- Work on copies or generated outputs.
- Never edit user originals in-place.
- Keep historical wrapper commands in `scientific-data-analysis/scripts/`
  compatible with the child script argv.
- Treat Keynote, Quick Look, and iWork routes as platform-bound or optional.

## Common Commands

```bash
python scripts/document_intake_workbench.py <copied-folder> --output-dir <run>/document-intake --summary-json <run>/summary.json
python scripts/latex_workbench.py scaffold <run>/latex
python scripts/presentation_workbench.py inspect <copied-deck> --summary-json <run>/summary.json
python scripts/semantic_diff.py <before> <after> --summary-json <run>/summary.json
```

## v2.8 Boundary

The mother remains the broad entrypoint, but this child is the owning root for
document/reporting command execution in app-side multi-root sync.

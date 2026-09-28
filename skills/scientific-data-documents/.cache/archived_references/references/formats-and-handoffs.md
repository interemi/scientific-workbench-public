# Formats and Handoffs

This belongs to the `documents + reporting` block.

## Format Routing Table

| Format family | Preferred approach | Notes |
| --- | --- | --- |
| `.fits`, `.fit`, `.fts`, `.fz` | `astropy.io.fits`, `scripts/inspect_fits.py`, `scripts/fits_quicklook.py` | Use for images, cubes, spectra, or FITS tables. |
| FITS tables, `.ecsv`, VOTable | `astropy.table`, `scripts/profile_table.py`, `scripts/catalog_workbench.py` | Prefer when units and metadata matter. |
| `.csv`, `.tsv`, plain tabular text | `pandas` or `astropy.table`, `scripts/profile_table.py`, `scripts/catalog_workbench.py`, `scripts/duckdb_workbench.py` | Pick `pandas` for general wrangling, `astropy` for astronomy metadata, and DuckDB when SQL over multiple files is the fastest path. |
| `.jsonl`, `.ndjson`, record-style `.json`, `.geojson` | `scripts/profile_table.py`, `scripts/catalog_workbench.py`, `scripts/inspect_data_container.py` | Good for modern data-export pipelines, LLM-generated structured data, and feature collections. Shared tabular readers handle additional record-style variants behind these public tools. |
| `.tbl`, `.dat`, ascii catalogs, APT exports | `scripts/profile_table.py`, `scripts/analyze_series.py`, `scripts/catalog_workbench.py` | `.tbl` may be an APT-style fixed-width export; preserve metadata columns when possible. |
| `.reg`, `.pref`, `.jmars`, `.ini`, `.cfg`, `.log` | `scripts/document_semantics.py` | Useful for DS9 regions, APT settings, JMARS sessions, and workflow configs. |
| `.ipynb` | `scripts/notebook_workbench.py`, `scripts/coursework_notebook_fidelity_check.py`, `scripts/bootstrap_analysis_notebook.py`, or `$CODEX_HOME/skills/jupyter-notebook/SKILL.md` | Use notebooks for exploration, tutorials, and reproducible reports. If a professor-provided notebook is the canonical material, inspect and execute a copy faithfully before adding new automation. |
| TEAREDUCE notebooks or TEAREDUCE-aligned astronomy workflows | `scripts/teareduce_router.py`, `scripts/teareduce_healthcheck.py`, `scripts/teareduce_bridge.py`, `references/teareduce.md` | Use only when the request is explicitly TEAREDUCE-specific or when a TEAREDUCE notebook is the faithful source workflow. |
| `.tex`, `.bib` | `scripts/latex_workbench.py`, `references/latex-overleaf.md` | Inspect, scaffold, and compile in a copied project for Overleaf-friendly work; emit a build manifest when the workflow needs traceability. |
| `.doc`, `.docx`, `.docm`, `.rtf`, `.odt`, `.epub` | `scripts/document_semantics.py`, `scripts/office_roundtrip.py`, plus `$CODEX_HOME/skills/doc/SKILL.md` when editing layout matters | Extract text semantically first, then use copy-based edits or exports when the goal is safe round-trip rather than pixel-perfect layout. For DOCX exported from Pages, `docx-style-inventory` and `docx-styled-replace` can isolate explicitly marked runs such as bold+italic+underline fragments. |
| `.pptx`, `.pptm`, `.key`, `.odp` | `scripts/document_semantics.py`, `scripts/office_roundtrip.py`, `scripts/presentation_workbench.py`, `scripts/keynote_export.py`, plus `$CODEX_HOME/skills/slides/SKILL.md` when layout/editability matters | Keep original decks untouched; use the presentation workbench for copied-deck inspection, slide-text export, handoff notes, and optional PDF export. On macOS Keynote can act as a GUI PDF-export fallback when CLI office tools are unavailable. |
| `.xlsx`, `.xlsm`, `.xls`, `.xlsb`, `.ods`, `.numbers` | `scripts/document_semantics.py`, `scripts/iwork_roundtrip.py`, `scripts/office_roundtrip.py`, plus `$CODEX_HOME/skills/spreadsheet/SKILL.md` when formulas/layout matter | Use semantic inspection before editing legacy workbook formats; `.xlsb` reads most robustly with `calamine` and can be emitted as a copy-oriented delivery format. |
| `.npy`, `.npz`, `.h5`, `.hdf5`, `.mat`, `.sqlite`, `.db`, `.nc`, `.nc4`, `.cdf`, `.netcdf`, `.zarr`, `.tif`, `.tiff` | `scripts/inspect_data_container.py` | Probe container structure before analysis; avoid unsafe pickle-like formats and be ready to summarize partial recovery when a stream is damaged. |
| `.parquet`, `.feather`, `.arrow`, `.ipc` | `scripts/inspect_data_container.py` or `scripts/profile_table.py` | Works when `fastparquet`, `pyarrow`, or related backends are installed; otherwise report the missing dependency cleanly. |
| Code and text (`.py`, `.md`, `.json`, `.yaml`, `.toml`) | Edit natively | Prefer small, runnable files with clear comments. |
| `.docx` | Load `$CODEX_HOME/skills/doc/SKILL.md` if installed | Use when layout fidelity matters. |
| `.pdf` | Load `$CODEX_HOME/skills/pdf/SKILL.md` if installed | Prefer rendering for visual review. If `pdftoppm`/`pdfinfo` are unavailable on macOS, declare the fallback and use `qlmanage`/`quicklook_bridge.py` or PyMuPDF-based rendering for the specific pages being reviewed. |
| `.pptx` | Load `$CODEX_HOME/skills/slides/SKILL.md` if installed | Keep editable output when possible. |
| `.xlsx`, `.ods` | Load `$CODEX_HOME/skills/spreadsheet/SKILL.md` if installed | Use formula-aware workflows. |
| `.pages`, `.numbers`, `.key` | Start with `scripts/document_semantics.py`; for a deeper package pass use `scripts/iwork_workbench.py`; for safe `.numbers` edits or exports use `scripts/iwork_roundtrip.py` | Keep originals, extract preview assets when helpful, recover bundle metadata and structure hints, OCR previews when needed, and save a member manifest for later conversion or audit. `quicklook_bridge.py` now falls back to preview assets when native Quick Look is blocked. |
| Archives (`.zip`, `.tar`, `.tar.gz`, `.gz`, `.bz2`, `.xz`) | Inspect contents before use with `scripts/inspect_data_container.py` | Good for datasets, templates, and portable project bundles. |
| Scanned or weak `.pdf` | `scripts/pdf_recover_extract.py` before deeper summarization | Render pages, OCR them, and try heuristic table recovery when native text extraction is poor. |

## Document Handoff Rules

- If the request is mainly about document layout, formatting, or page-level review, use the dedicated document skill instead of forcing everything through a data-analysis workflow.
- If the document is only a source of scientific content, extract the content needed for the analysis, then keep the analysis in Python, Markdown, notebooks, or tables.
- For `.pages`, `.numbers`, and `.key`, preserve the original file. Export to a more interoperable format when possible before doing substantial edits, but extract previews, bundle metadata, structure hints, OCR text, and a member manifest first when that helps triage the document.
- For `.pages` fragments marked by formatting, do not mutate the original package directly. Export a working copy to `.docx`, inventory styled runs there, perform selective edits in a copied DOCX, and verify readback before carrying the edit back to Pages.
- For `.numbers`, prefer safe copy-based edits plus an exported companion file over direct mutation of the original bundle.
- For `.docx`, `.pptx`, and `.xlsx`, use copy-based round-trip edits when the job is content-centric and layout-perfect authoring is not required.
- For copied presentation decks, prefer `scripts/presentation_workbench.py` when you want a handoff bundle with slide text, notes, manifest, and optional PDF export in one place.
- For copied presentation decks, record which PDF-export backend was used when that matters for reproducibility or visual diffs.
- For scientific decks and posters, also read `references/scientific-presentation-handoff.md`: only scientific figures should be images; titles, captions, arrows, circles, labels, and explanatory text should remain editable when the user still needs to iterate.
- For LaTeX, prefer editing source and compiling in a copied work directory instead of modifying the original project in place.
- For LaTeX builds, keep a manifest of the compiler path, number of passes, and copied work directory when the deliverable is more than trivial.
- For scientific containers, inspect structure first and only then load the specific arrays, tables, or datasets you need.
- For archive-like inputs, inventory members before extracting or loading anything downstream; if a compressed stream is truncated, salvage what you can and report the damage.
- For TEAREDUCE-specific work, keep the package optional: use it when the user wants TEAREDUCE behavior or notebook fidelity, but keep the skill's main flow tool-agnostic.
- Do not auto-load arbitrary pickle-like files (`.pkl`, `.pickle`, joblib caches) unless the user explicitly requests it and the trust model is clear.

## Pages Marked-Fragment Route

Use this when a `.pages` document has visually marked fragments, for example text that is simultaneously bold, italic, and underlined, and the task is to edit only those fragments.

1. Preserve the original `.pages` file.
2. Create a working copy and export it to `.docx` using Pages or another faithful local route.
3. Inventory the marked runs in the DOCX copy:

```bash
python scripts/office_roundtrip.py docx-style-inventory exported_from_pages.docx \
  --require-bold --require-italic --require-underline \
  --output-csv marked_runs.csv \
  --report-md marked_runs.md \
  --summary-json marked_runs.json
```

4. Edit only matching run-local text in a new DOCX copy:

```bash
python scripts/office_roundtrip.py docx-styled-replace exported_from_pages.docx edited.docx \
  --find "old marked text" \
  --replace "new marked text" \
  --require-bold --require-italic --require-underline \
  --summary-json styled_replace.json
```

5. Run `docx-style-inventory` again on `edited.docx` and verify the replacement appears in the same style class.
6. Export or preview the result visually before copying the edit back into Pages.

Acceptance criteria:

- original `.pages` untouched
- DOCX export retained the marked fragment as explicit runs
- inventory table lists the exact fragments to edit
- replacement count and readback count agree
- visual preview confirms the surrounding formatting did not regress

Limits:

- this route detects explicit DOCX run-level formatting; inherited paragraph/theme styling may need manual visual confirmation
- it does not promise faithful direct `.pages` mutation
- text split across multiple DOCX runs may require manual edit or a narrower replacement target

## PDF Rendering Fallback

Use this PDF rendering fallback when Poppler is absent but the task still needs visual evidence from a PDF.

Prefer the dedicated PDF skill or Poppler tools when available, especially `pdfinfo` for page metadata and `pdftoppm` for page images. On macOS, if those binaries are missing:

1. State that Poppler rendering is unavailable.
2. Use `scripts/quicklook_bridge.py` or native `qlmanage` for a visual preview when Quick Look can render the PDF.
3. If the task needs page-specific review and PyMuPDF is available, render only the relevant pages through the PDF route or `pdf_recover_extract.py`.
4. Record the fallback method in the notes or manifest so visual differences are not treated as Poppler-equivalent.

Minimal fallback example:

```bash
python scripts/quicklook_bridge.py final_report.pdf final_report_preview.png \
  --summary-json final_report_preview.json
```

Acceptance criteria:

- the response says whether Poppler, Quick Look, or PyMuPDF produced the preview
- only the pages needed for review are rendered when the PDF is large
- visual QA is not presented as OCR/table extraction unless that actually ran

## Notebook And Script Choice

- Use a notebook when the user wants exploration, teaching, mixed narrative and code, or visible intermediate outputs.
- Use a script when the workflow will be rerun, versioned, or scheduled.
- If the work begins in a notebook but becomes stable, offer or create a companion script.

## Language And Translation Rules

- Work directly in English or Spanish depending on the user's preference.
- Translate incoming material into English or Spanish when requested or when it makes the task materially easier.
- Keep scientific terms, column names, code identifiers, and citations stable unless the user asks for a fully localized version.
- When translating methods or results, preserve numerical values, units, equation symbols, and instrument names exactly.

## File Hygiene

- Never overwrite raw data or source documents.
- Keep derived outputs in clearly named files.
- Save plots, cleaned tables, and reports with stable names so they can be reused downstream.
- When converting between formats, note what metadata or styling may have been lost.
- When producing derived outputs for handoff, attach a simple manifest with hashes, parameters, and generated files when the workflow is more than trivial.
- When the final goal is a deliverable rather than an intermediate analysis artifact, consider `scripts/deliverable_factory.py` to scaffold or package the handoff cleanly.

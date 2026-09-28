# v2.0 Phase 4: Documents, iWork, and GUI Workflows

Phase 4 closes deferred rows P1-34, P1-35, and P1-37 by joining the existing
copy-safe backends to explicit ScientificWorkbench review and confirmation
surfaces.

## Target Matrix

| Target | Exposure | App workflow | Primary artifacts | Original policy |
|---|---|---|---|---|
| `office_roundtrip.py docx-style-inventory` | normal document tool | Select explicit bold/italic/underline requirements and preview matching runs. | `summary_json`, `table_csv`, `report_md` | Copy DOCX into the run before inspection. |
| `office_roundtrip.py docx-styled-replace` | normal document tool with confirmation | Preview exact before/after run-local replacements, confirm, then write an edited copy. | `edited_document`, `app_preview`, `summary_json`, `manifest_json` | Never use the source path as output; stage a fresh copy first. |
| `keynote_export.py` | optional macOS GUI tool | Preflight macOS/AppleScript/Keynote, require confirmation, then export a copied deck. | `preview_pdf`, `summary_json`, `manifest_json` | Open only the staged copy and close it without saving. |

## P1-34 Style Inventory

ScientificWorkbench exposes a style selector for explicit DOCX run formatting:

- bold;
- italic;
- underline;
- any explicitly special run when no flag is selected.

The app previews matching text, document location, style flags, and visible
counts for total matches, bold, italic, underline, body, and table runs. The
backend remains intentionally limited to explicit run-level formatting;
paragraph/theme inheritance still requires visual document review.

The individual P1-34 regression uses a copied DOCX containing plain, bold,
italic, underline, bold+italic, and table bold+underline runs. Its default
inventory finds five explicitly styled runs with counts `bold=3`, `italic=2`,
`underline=2`, `body=4`, and `table=1`. The bold selector finds three runs and
the combined bold+italic selector finds one. No edited document is created.

## P1-35 Reviewed Replacement

The replacement flow is deliberately two-stage:

1. inventory matching styled runs on a copied DOCX;
2. enter exact find/replace text and review the generated before/after diff;
3. explicitly confirm;
4. write `artifacts/edited_copy.docx`;
5. write `previews/style_diff.json`;
6. verify styled-run readback.

`style_diff.json` uses artifact type `app_preview`. The edited DOCX uses
`edited_document`. Both are additive v2.0 artifact types and do not rename the
v1.8/v1.9 vocabulary.

ScientificWorkbench enforces the review boundary before launching the command:
an unconfirmed request or an empty reviewed diff is rejected app-side. Its
confirmed command also passes `--require-confirmation` plus a unique
`--confirmation-id`, so the backend refuses an unconfirmed app-style edit
before creating the output. The identifier is persisted in the replacement
summary, diff preview, and manifest parameters. Direct legacy CLI use remains
compatible unless strict confirmation is explicitly requested.

## P1-37 Keynote GUI Export

The app runs preflight before enabling export:

- platform is macOS;
- `osascript` is available;
- Keynote is discoverable.

The export button remains disabled until preflight is usable and the user
confirms GUI automation. Missing Keynote or automation prerequisites produce
`BLOCKED_CONTROLADO` with structured next actions. Keynote is optional and is
not a core dependency.

The confirmed ScientificWorkbench command passes `--require-confirmation`, a
unique `--confirmation-id`, and a run-local `--log-txt`. The backend checks the
identifier before activating Keynote, records it in the summary and manifest,
captures native stdout/stderr, and removes a newly created partial PDF when the
AppleScript export fails. The app displays a visible in-progress state while
Keynote operates on the copied deck.

## Safety Contract

These workflows emit `contract_version: "2.0"` with:

- `original_modified: false`;
- `safety.input_policy: copied_input_only`;
- `safety.output_policy: separate_run_directory`;
- `safety.requires_confirmation: true` for replacement and Keynote export;
- `job_metadata.recommended_exposure` appropriate to normal or optional use.

ScientificWorkbench fingerprints originals before and after each staged
workflow. A changed original is treated as a hard app-side safety error.

## Validation

`scripts/audit_v2_0_phase4_documents_gui_regression.py` validates:

- synthetic DOCX style inventory;
- reviewed replacement and diff sidecar;
- `edited_document` and `app_preview` typing;
- byte-stable originals;
- real Keynote/AppleScript preflight on a copied synthetic deck;
- controlled Keynote absence/failure behavior through the existing regression;
- ScientificWorkbench models, services, views, command builders, and tests.

The controlled Phase 4 audit completed with:

| Target | State | Evidence |
|---|---|---|
| P1-34 style inventory | `PASS` | Two explicit bold/italic/underlined runs found in paragraph and table content; CSV, Markdown report, and summary emitted. |
| P1-35 reviewed replacement | `PASS` | Two reviewed replacements written to a separate DOCX; an unconfirmed strict run was rejected without output, and the confirmed JSON diff, summary, and manifest record the approval identifier. |
| P1-37 Keynote export | `PASS` | Real preflight and confirmed GUI export produced a visually reviewed one-page PDF plus native log; missing confirmation, absent backend, and native failure all blocked without a misleading PDF. |

Original and staged-input SHA-256 hashes remained identical. Quick Look review
confirmed that the edited DOCX preserved the requested run formatting and that
the exported one-page PDF contained the expected slide text without clipping.

The narrow P2 found during the audit was also closed: Keynote paths are now
passed as AppleScript arguments instead of interpolated into source code, and
the staged document is closed without saving on both success and native error.

Validation gates:

- Python compilation for all touched scripts: `PASS`;
- Phase 4 dual regression: `PASS`;
- historical DOCX inventory and replacement regressions: `PASS`;
- historical Keynote regression, including apostrophe-safe arguments: `PASS`;
- v1.9 artifact-type freeze regression: `PASS`;
- v1.9 error-contract regression: `PASS`;
- v2.0 parser/artifact regression: `PASS`;
- public-surface derived-doc check under `datanalysis`: `PASS`;
- ScientificWorkbench Swift suite: `135/135 PASS`.

P1-34 also has the dedicated regression
`scripts/audit_v2_0_p1_34_docx_style_inventory_visual_regression.py`, which
validates selector counts, preview matches, artifact discovery markers,
byte-stable original/copy hashes, and the absence of edited DOCX products.

P1-35 has the dedicated regression
`scripts/audit_v2_0_p1_35_docx_styled_replace_confirmed_regression.py`. It
validates the inventory/dry-run preview, backend rejection without a
confirmation identifier, exact diff agreement after confirmation,
`edited_document` and `app_preview` typing, style-preserving readback, and
byte-stable original/staged-copy fingerprints.

P1-37 has the dedicated regression
`scripts/audit_v2_0_p1_37_keynote_export_gui_controlled_regression.py`. It
validates real Keynote/AppleScript preflight, a confirmed export from a copied
synthetic deck when the backend is available, `preview_pdf` and `log_txt`
typing, PDF text traceability, confirmation provenance, byte-stable deck
fingerprints, controlled backend absence, and cleanup after a simulated native
failure that created a partial PDF.

Known limit: DOCX inventory deliberately inspects explicit run formatting. A
visual review remains necessary when appearance comes only from inherited
paragraph, theme, or character styles.

No installed skill synchronization is performed in Phase 4.

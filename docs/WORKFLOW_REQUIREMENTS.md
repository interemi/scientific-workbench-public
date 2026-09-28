# Workflow Requirements

This guide maps the Scientific Workbench capability catalog to the environment
and optional tools each workflow class needs. It describes the registry included
in this repository; the app's live **Capabilities** and **Environment** views are
the source of truth for the checkout and machine currently in use.
For every user-facing ID and a first safe input, use the
[55-capability setup matrix](CAPABILITY_SETUP_MATRIX.md).
For external tools and safe first checks, see
[optional backends](OPTIONAL_BACKENDS.md).

## Registry snapshot

The canonical registry contains 61 entries:

| Surface | Count |
| --- | ---: |
| User-facing capabilities | 55 |
| Maintainer-only gates | 6 |

The 55 user-facing entries are distributed as follows:

| Workflow family | Count | Typical inputs and outputs |
| --- | ---: | --- |
| Core and routing | 5 | Environment reports, routing advice, optional-backend preflight |
| Observational astronomy | 24 | FITS, spectra, radial velocity, photometry, catalogs, legacy coursework |
| Documents and reporting | 14 | DOCX, presentations, LaTeX, semantic review, deliverable scaffolds |
| Notebooks and cross-domain data | 12 | CSV/TSV, notebooks, DuckDB, time series, mixed research folders |

Support and platform declarations are registry metadata, not quality grades:

| Registry field | Current distribution | Meaning |
| --- | --- | --- |
| `support_level` | 36 stable, 11 narrow, 6 optional, 2 platform-bound | Stable is the general path; narrow is deliberately scoped; optional requires another backend; platform-bound requires a specific macOS app or service. |
| `platform` | 44 portable, 6 macOS, 5 datanalysis | Portable scripts still need their declared Python packages. `datanalysis` means the dedicated scientific interpreter is required. |
| `requires_datanalysis` | 14 true, 41 false | A false value does not mean dependency-free; it means the dedicated full scientific environment is not a hard registry requirement. |
| `smoke_tier` | 16 core, 10 full, 29 none | Smoke coverage is regression evidence, not exhaustive scientific validation. |

These counts are checked against
`skills/scientific-data-maintainer/.cache/archived_references/public_surface_registry.yaml`.

## Base requirements

Every workflow needs:

- macOS 14 or later for the app;
- the complete five-root skill snapshot from this repository;
- a separate output root that does not overlap any original input;
- enough free space for copied inputs, logs, manifests, previews, and derived
  artifacts; and
- a reviewed plan or guided form before execution.

The portable **core** Python profile is the recommended starting point. The
**full** profile is needed for the workflows that rely on the larger astronomy,
notebook, SQL, OCR, and scientific stack. Follow [INSTALL.md](../INSTALL.md) and
use a new environment; never update or prune an environment that must be
preserved as evidence.

Ollama, OpenAI, Grok/xAI, Gemini, and Codex are planning or assistance routes.
They do not replace the local capability requirements in this document.

## Requirements by workflow class

| Workflow class | Core/full profile | Additional requirement | Safe behavior when unavailable |
| --- | --- | --- | --- |
| Environment and routing | Core | None for `datanalysis_env.status`, `env_doctor`, and routing checks | Report the missing interpreter/backend; do not run a substitute silently. |
| Basic FITS inspection | Core | Readable FITS input | Emit inspection/QA evidence or an explicit parse failure. |
| FITS RGB and Astrometry.net | Full for the declared datanalysis paths | Astrometry.net local/web access is optional and must pass preflight | Keep existing-WCS verification available; block solving honestly when no route is configured. |
| Radial-velocity inspection | Core | Text/CSV/TSV/`.vels` table with reviewed column and unit mapping | Stop before staging if time, velocity, or units are ambiguous. |
| Photometric calibration | Core in a dedicated `datanalysis` environment | At least three valid standards and reviewed magnitude/airmass mapping | Keep suspicious ranges as warnings; block missing required columns or invalid samples. |
| Li 6708 measurement and SB2 fitting | Core in a dedicated `datanalysis` environment | Reviewed spectrum/CCF inputs; optional manual coursework context | Preserve per-order evidence and report weak/ambiguous fits instead of inventing a result. |
| Catalog profiling and sky crossmatch | Core for profiling; datanalysis for reviewed sky crossmatch | Text tables for guided column inspection; binary tables use the expert route | Require explicit RA/Dec mapping and valid angular units before execution. |
| Document intake and semantic review | Core | Supported readable document format | Record unsupported or unreadable files in intake evidence. |
| DOCX style inventory/replacement | Core | DOCX input; replacement requires an exact reviewed diff and confirmation | Create a new DOCX in the run; never overwrite the source. |
| Presentation inspection | Full for the validated presentation stack | Readable deck or exported representation | Preserve a controlled block when rendering support is absent. |
| LaTeX scaffold/review/compile | Full validation expects a TeX engine | `latexmk` or `pdflatex` for compilation (for example, from TeX Live or MacTeX) | Scaffold and review may remain available; compilation must report a missing engine. |
| Table profiling and mixed-data routing | Core | Readable table or mixed folder | Use bounded previews and keep ambiguous routing visible. |
| Notebook execution | Full/datanalysis | A copied notebook; declared inputs for interactive cells | Execute only the run copy and block unresolved interactive input or unsafe inline mutation. |
| DuckDB exploration | Full/datanalysis | DuckDB Python dependency | Use the safe preview route; arbitrary SQL is outside guided defaults. |
| Time-series forecasting and ASCII spectra coursework | Full/datanalysis | Valid numeric columns and workflow-specific sampling assumptions | Surface invalid sampling, missing columns, and fit limitations. |

## Optional external backends

The following tools are never installed implicitly by Scientific Workbench:

| Backend | Related capabilities | Configuration/evidence |
| --- | --- | --- |
| STILTS/TOPCAT and Java | `external_astro_tools_preflight`, `stilts_workbench` | Configure command or JAR paths, run preflight, and retain the exact command/version in the job. Native table and catalog routes remain available. |
| APT | `apt_workbench` | Configure the APT command and saved preferences, then run the dedicated preflight. FITS inspection and noise-budget alternatives remain available. |
| IRAF | `legacy_spectroscopy_envcheck`, `fxcor_iraf_workbench.*` | macOS legacy/coursework route. Work only in the staged ASCII-safe copy created for the run. |
| iSTARMOD | `istarmod_workbench.*` | Inspect the tree first, then prepare an isolated copy. Do not clean or run the original tree. |
| teareduce | `teareduce_router` | Optional external notebook kernel, not a Full-profile requirement. The router does not execute it; see the [separate kernel route](OPTIONAL_BACKENDS.md#teareduce-documents-and-macos-apps). A missing or unverified backend is a controlled block. |
| Keynote and iWork | `iwork_workbench`, `keynote_export` | macOS, the relevant Apple app, and AppleScript access. Export only from the run copy after explicit confirmation. |
| Quick Look | `quicklook_bridge` | macOS Quick Look availability and a supported document. Keep failure diagnostic and non-destructive. |
| TeX engine | `latex_workbench.compile` | Install `latexmk` or `pdflatex` (for example, through TeX Live or MacTeX). Tectonic alone is not an engine supported by this command. The Python environment does not install a TeX engine. |
| Pandoc fallback | `document_intake_workbench` and document-semantic inspection of selected formats | Optional when an earlier built-in or macOS extraction route raises an error; check `pandoc --version` and inspect the reported extraction method. It is not a general document-install prerequisite. |
| Poppler for a user notebook | `notebook_workbench.execute-copy` only if that notebook imports `pdf2image` | Preflight reports the missing import or `pdftoppm`/`pdftocairo`. The Full lock does not include `pdf2image`; document PDF routes use pypdfium2 instead. |

LibreOffice, external OCR resources, and other format-specific helpers may also
be reported by `env_doctor` or a capability preflight. Install only the tool
needed for the reviewed workflow and record its version.

## Readiness sequence

1. Run the distribution snapshot check before trusting the included skill tree.
2. Create and validate a new core or full environment as described in
   [INSTALL.md](../INSTALL.md).
3. In **Settings**, select the mother skill root, the new Python interpreter,
   and a separate output folder.
4. Run `datanalysis_env.status` and `env_doctor`.
5. Run the workflow-specific preflight for any optional or platform-bound tool.
6. Use a synthetic fixture and inspect the inputs and output folder. A direct
   **Run Capability** action starts immediately; for a Chat-generated plan, use
   **Dry Run** to inspect commands before running it.
7. Execute the smallest useful case and review **Jobs**, **Results**, the
   manifest, and the unchanged-input evidence.

An optional backend that is absent should normally produce a controlled block.
Do not relabel it as a pass, weaken the gate, or install unrelated dependencies
until the reported requirement has been reviewed.

For recovery steps and evidence to preserve, see
[Troubleshooting](TROUBLESHOOTING.md).

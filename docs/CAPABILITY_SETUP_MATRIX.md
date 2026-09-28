# Choose and prepare a Scientific Workbench capability

Scientific Workbench contains 55 user-facing capabilities and six maintainer
gates. Read [what the skills and capabilities do](SKILLS_AND_CAPABILITIES.md)
for a plain-language description of each action. This page helps you choose
the Python profile and any additional tool
for one capability. It describes the current registry and app classification;
it is not a claim that every backend or external application was exercised on
your Mac. Follow [INSTALL.md](../INSTALL.md) for a source build and the first
synthetic run, then use the **Capabilities** view to search by the exact ID
below. The app's **Environment** view reports availability on the current
machine. Some legacy and narrow tools have guided argument builders but are
still expert/CLI routes, not ordinary app actions.

The **Start** column recommends `Core` or `Full` as installed by
`script/setup_environment.py`. `Full` includes Core. A row saying `Core` can
still need an optional external backend. The dedicated Python selected in
Settings must be the new `datanalysis/bin/python` environment for rows marked
`requires_datanalysis` in the registry; this name applies to both profiles.
Do not install individual Python packages into an existing research environment
to make a row appear ready. Exact package sets and locks are in
[dependencies and licenses](DEPENDENCIES_AND_LICENSES.md).
The Python installation unit for each row is its stated profile, not an
individually guessed package list: the reviewed Apple Silicon Core lock has 32
runtime packages, and Full has 200 plus three pinned build tools. The lock
files name every direct and transitive Python package. `Full recommended`
identifies the safer documented starting profile, not a proof that every Core
installation will fail. An external tool in a row is an additional requirement,
not something the Python profile installs.
Use [optional backends](OPTIONAL_BACKENDS.md) for acquisition and first checks
of tools outside the Python profiles. The
[additional-backend table](#additional-backends-permissions-and-recovery)
links affected IDs to their permission, cost, and recovery limits.
The dated [capability validation evidence](CAPABILITY_VALIDATION_EVIDENCE.md)
shows which IDs had Core/Full smoke coverage, a narrower diagnostic, or a
controlled block; its results must be refreshed for a final public commit.

Each row's second cell gives the app catalog access mode, the starting Python
profile, and the current app-readiness label. `normal` and `expert` are catalog
modes; `optional` needs a named backend, and `legacy` needs a specialist
workflow. Of the 55 rows, 17 are `app_ready`, 19 `app_ready_partial`, seven
`blocked_optional`, ten `cli_only`, and two `not_applicable_to_app`. These
labels come from the app source and do not assert that a backend is installed:
`app_ready_partial` needs human review, `blocked_optional` needs its backend
preflight, and `cli_only` or `not_applicable_to_app` must use the documented CLI
route. The app automatically enables only a normal-mode `app_ready` step;
expert and optional steps still need explicit review. The
current [M102 record](M102_GUIDED_COVERAGE.en.md) documents guided input
construction for all 55 IDs; it does not prove a backend is available.

The **Registry preflight** column is copied from the canonical registry:
17 `explicit`, eight `inline`, and 30 `none`. `explicit` declares a separate
readiness check or a capability that is itself a preflight; consult that
route's `--help` and the first-safe-input column before running data.
`inline` declares a check inside the workflow; inspect its actual status and
warnings before trusting the output. `none` means the
registry declares no route-specific preflight; it does **not** waive the
environment check, input review, Dry Run when available, or result inspection.
These are contract labels, not evidence that a backend is installed or that a
scientific result is valid. Keep a failed preflight and retry in a new run
directory after correcting its named cause.

No backend capability requires an Ollama model or paid cloud account merely
to execute its local command. Chat/planning can use Ollama or optional cloud
providers separately; downloads, subscriptions, and network/API costs depend
on the service chosen. Astrometry.net web solving and catalog/network lookups
may use network access; review the exact job plan before consenting. Keynote
automation may require macOS Apple Events permission. Keep credentials outside
the repository and use a **new** results directory, never an original-data
folder. An `ok` process result does not validate a scientific conclusion.

## Find the CLI entrypoint for any ID

The tables below include all 55 exact capability IDs. From the repository
root, their CLI entrypoint is `skills/<owning root>/scripts/<script stem>.py`.
The **script stem** is the part of the ID before the first dot. If the ID has
a dot, pass the part after it as the first argument: for example,
`latex_workbench.compile` maps to `latex_workbench.py compile`. The app uses
this same stem/subcommand convention. The owning root is determined by the
app's `SkillRootCatalog`, not by whether a compatibility copy of a script also
exists elsewhere:

| Table below | Owning root under `skills/` | Exception |
| --- | --- | --- |
| Core and routing | `scientific-data-analysis` | `external_astro_tools_preflight` belongs to `scientific-data-astro`. |
| Observational astronomy | `scientific-data-astro` | None. |
| Documents and reporting | `scientific-data-documents` | None. |
| Notebooks and cross-domain data | `scientific-data-notebooks` | `spectra_ascii_coursework_workbench` belongs to `scientific-data-astro`; `catalog_workbench.crossmatch-sky` belongs to `scientific-data-analysis`. |

Use the Python from the **new** Core or Full `datanalysis` environment chosen
in [INSTALL.md](../INSTALL.md). From the repository root, request help for
the selected route before entering research paths; this command does not run
the workflow:

```bash
SW_PY="$HOME/Library/Application Support/Scientific Workbench/environments/core/datanalysis/bin/python"
"$SW_PY" skills/scientific-data-astro/scripts/fxcor_iraf_workbench.py prepare-session --help
```

The source-preparation checkout's 55 mapped `--help` routes all exited zero
on 24 September 2026 using the maintainer's scientific Python. This checks
entrypoint and argument-parser availability, **not** all runtime dependencies
or execution on a new Mac. The `Access` column below and the app's readiness
state still govern whether to use a guided app run, an expert/CLI route, or an
optional-backend preflight. Never paste an example path into a command unless
it points to your own reviewed copy.

For a small, backend-free first CLI run, the included table fixture can be
profiled without changing it. This example uses a unique results directory:

```bash
mkdir -p "$HOME/ScientificWorkbenchRuns"
SW_RUN=$(mktemp -d "$HOME/ScientificWorkbenchRuns/cli-profile-XXXXXX")
"$SW_PY" skills/scientific-data-notebooks/scripts/profile_table.py \
  skills/scientific-data-notebooks/examples/tabular/ops.csv \
  --summary-json "$SW_RUN/summary.json" \
  --manifest-json "$SW_RUN/manifest.json"
```

On the preparation Mac this returned three rows, four columns, `app_status:
PASS`, and two new JSON files. Inspect those files before treating any larger
dataset as ready. The row for each ID below identifies its first synthetic or
copied input and the result or controlled limitation to expect.

## Core and routing (5)

| Capability | Access; Python profile; app readiness | Registry preflight | First safe input or preflight | Expected evidence and limit |
| --- | --- | --- | --- | --- |
| `datanalysis_env.status` | normal; Core; app_ready | `explicit` | Current interpreter selection; no data input | Environment report; checks discovery, not all packages. |
| `datanalysis_healthcheck` | normal; Core; app_ready | `explicit` | New `datanalysis` environment | Dependency/health report; warnings identify missing full components. |
| `env_doctor` | normal; Core; app_ready | `explicit` | Current machine and selected interpreter | Readiness report; optional backends can remain unavailable. |
| `companion_route_check` | normal; Core; app_ready | `none` | A synthetic task description, e.g. reviewing a report | Routing advice only; does not invoke another connector or edit a file. |
| `external_astro_tools_preflight` | optional; Core; blocked_optional | `explicit` | Run without a scientific file; configure Java/STILTS/TOPCAT/APT only if needed | Per-backend status; a missing optional tool is not a core failure. |

## Observational astronomy (24)

| Capability | Access; Python profile; app readiness | Registry preflight | First safe input or preflight | Expected evidence and limit |
| --- | --- | --- | --- | --- |
| `inspect_fits` | expert; Core; app_ready | `none` | A copied small synthetic FITS with an image HDU | HDU/header/WCS summary and preview where possible; no measurement implied. |
| `fits_rgb_batch` | expert; Full recommended; app_ready_partial | `none` | Three copied synthetic FITS images with compatible filters/WCS | Derived RGB and QA manifest in a new run; do not request cleanup on an empty first run. |
| `rgb_visual_fits_export` | expert; Full recommended; app_ready_partial | `none` | A generated RGB PNG, optionally a previous PNG | Display-only FITS plus comparison/manifest; not calibrated science pixels. |
| `stilts_workbench` | optional; Core + Java/STILTS; blocked_optional | `explicit` | `preflight` before any table conversion or match | Controlled block if command/JAR is absent; retain backend version and exact command when used. |
| `astrometry_net_workbench.preflight` | expert; Full; app_ready_partial | `explicit` | Copied synthetic FITS/image; choose local or web solve route explicitly | Plausibility/hints report; no astrometric solution is claimed by preflight. |
| `astrometry_net_workbench.verify-existing-wcs` | expert; Full; app_ready_partial | `explicit` | Copied FITS with known celestial WCS | WCS QA report without contacting a solver; missing WCS must remain visible. |
| `radial_velocity_workbench.inspect` | expert; Core; app_ready_partial | `none` | Synthetic RV table with reviewed time, velocity, uncertainty and units | Inspection/QA; no planet fit or physical interpretation. |
| `radial_velocity_workbench.validate-manifest` | expert; Core; app_ready_partial | `none` | A new manual RV session manifest created by `scaffold-session` | Validation report; does not fit or amend a historic session. |
| `legacy_spectroscopy_envcheck` | legacy CLI; Core; cli_only | `explicit` | Synthetic copied legacy practice tree | IRAF/iSTARMOD readiness; absent legacy tools yield a guarded warning/block. |
| `echelle_multispec_inventory` | expert; Core; app_ready_partial | `none` | Copied synthetic MULTISPE FITS | Per-order inventory; review whether the synthetic layout resembles real data. |
| `fxcor_iraf_workbench.prepare-session` | legacy CLI; Core; cli_only | `explicit` | Synthetic copied coursework tree | ASCII-safe working copy and manifest; IRAF is not installed by Core. |
| `fxcor_iraf_workbench.run-auto` | legacy CLI; Core + IRAF; cli_only | `explicit` | The **new prepared copy** from the preceding route | Fxcor log/tables if IRAF works; block rather than invent CCF/RV results. |
| `legacy_rv_coursework_workbench.analyze` | legacy CLI; Core; cli_only | `none` | Synthetic FXCOR/RV tables with explicit order mapping | Consolidated coursework summary; invalid/missing calibration remains visible. |
| `sb2_double_gaussian_workbench.fit` | expert CLI; Core; cli_only | `none` | Synthetic two-peak CCF CSV | Fit table/plot; inspect peak separation and uncertainty manually. |
| `li6708_equivalent_width_workbench.measure` | expert CLI; Core; not_applicable_to_app | `none` | Synthetic ASCII/FITS spectrum covering 6707.8 Å | Equivalent-width estimate/plot; continuum and units require scientific review. |
| `legacy_external_reference_check` | legacy CLI; Core; not_applicable_to_app | `none` | Synthetic RV summary for a supported fixed reference | Plausibility comparison, not an independent scientific reference search. |
| `istarmod_workbench.inspect-tree` | legacy CLI; Core; cli_only | `explicit` | A synthetic legacy iSTARMOD-like tree with root-level `.sm` | Structure/readiness report; no cleaning of the source tree. The current upstream layout has not been validated for this adapter. |
| `istarmod_workbench.prepare-copy` | legacy CLI; Core; cli_only | `explicit` | That reviewed legacy tree, with a **new** output path | Clean derived copy; the original tree and old outputs remain intact. It does not install upstream iSTARMOD. |
| `legacy_spectroscopy_report_builder.scaffold` | legacy CLI; Core; cli_only | `none` | A **new** report directory | Spanish coursework LaTeX scaffold; this is a runtime output, not public GitHub documentation. |
| `legacy_spectroscopy_report_builder.populate` | legacy CLI; Core; cli_only | `none` | A fresh scaffold; add only explicitly assigned JSON summaries | Derived report sections; an empty synthetic scaffold checks mechanics, not scientific content. |
| `photometric_solution` | expert; Core dedicated environment; app_ready_partial | `none` | Synthetic standards with magnitude, airmass and uncertainties | Coefficients/residuals/QA; inspect fit assumptions and at least three valid standards. |
| `photometry_noise_budget` | normal; Core; app_ready | `none` | Synthetic positive source, sky, read-noise and aperture values | SNR/noise budget with units; review whether assumptions fit the detector. |
| `apt_workbench` | optional; Full + APT; blocked_optional | `explicit` | `preflight`; configure APT command and saved preferences | Controlled block without APT; any real run needs copied inputs and retained logs. |
| `teareduce_router` | optional; Core for routing, Full for the copied-notebook launcher; blocked_optional | `explicit` | Synthetic CCD reduction intent and backend preflight | Routing recommendation only; TEAREDUCE requires a separately installed external notebook kernel and remains unverified. |

## Documents and reporting (14)

| Capability | Access; Python profile; app readiness | Registry preflight | First safe input or preflight | Expected evidence and limit |
| --- | --- | --- | --- | --- |
| `document_intake_workbench` | normal; Core; app_ready | `inline` | New folder of synthetic PDF/DOCX files | Inventory and readability warnings; no source editing. |
| `presentation_workbench.inspect` | normal; Full; app_ready_partial | `inline` | Copied synthetic PPTX | Slide/content/editability report; visual judgment still required. |
| `presentation_workbench.existing-deck-style-audit` | normal; Full; app_ready_partial | `inline` | Copied synthetic deck with figures | Geometry/style/figure provenance review; does not approve scientific figures. |
| `iwork_workbench` | optional; Core, macOS iWork/Quick Look for exports; blocked_optional | `inline` | Synthetic `.pages` or `.key` bundle; inspect before requesting export | Bundle inventory/preview where supported; macOS app and OCR routes are optional. |
| `office_roundtrip.docx-style-inventory` | normal; Core; app_ready_partial | `none` | Generated DOCX with marked styled runs | Style/run inventory; no edit. |
| `office_roundtrip.docx-styled-replace` | normal; Core; app_ready_partial | `none` | Copy of that generated DOCX and exact reviewed style/text selection | New DOCX plus readback; do not replace the original file. |
| `quicklook_bridge` | optional; Full, macOS Quick Look; app_ready_partial | `explicit` | Copied supported document | PNG preview or a clear unsupported-format result; not a semantic review. |
| `keynote_export` | optional; Core + Keynote + Apple Events permission; blocked_optional | `explicit` | Copy of a synthetic deck; review the requested export destination | PDF export from the run copy; block if GUI automation is unavailable. |
| `latex_workbench.scaffold` | normal; Full tested; app_ready_partial | `none` | New report project directory; no TeX engine needed to create source | LaTeX scaffold; no compiled PDF yet. |
| `latex_workbench.review` | normal; Full tested; app_ready_partial | `none` | Newly scaffolded or copied `.tex` tree | Structure/portability findings; not a successful compilation. |
| `latex_workbench.compile` | normal; Full + `latexmk` or `pdflatex` (TeX Live/MacTeX); app_ready_partial | `none` | New/copy `.tex` tree and checked engine version | PDF and build log; failures remain in the run directory. Tectonic alone is not supported by this command. |
| `scientific_writeup_review` | normal; Core; app_ready | `none` | Synthetic methods/results prose | Methodology/claim review; recommendations require author judgment. |
| `deliverable_factory.scaffold` | normal; Core; app_ready | `none` | New status/handoff directory | Reusable files in the new run; no historical report rewrite. |
| `semantic_diff` | normal; Core; app_ready | `none` | Two synthetic versions of a table or document | Change report; semantic interpretation needs review. |

## Notebooks and cross-domain data (12)

| Capability | Access; Python profile; app readiness | Registry preflight | First safe input or preflight | Expected evidence and limit |
| --- | --- | --- | --- | --- |
| `profile_table` | normal; Core; app_ready | `none` | Small synthetic CSV with units noted separately | Column/missingness summary; no cleaning or inferred units. |
| `duckdb_workbench` | optional; Full (DuckDB Python package); blocked_optional | `inline` | Two synthetic tables; start with a bounded read-only query | Preview/table output; a missing DuckDB package blocks this optional lane. |
| `cross_domain_data_workbench` | normal; Core; app_ready | `inline` | New folder of synthetic CSV/TSV files | Inventory/first-pass report; SQL parts depend on available backend. |
| `bootstrap_analysis_notebook` | normal; Core; app_ready | `none` | New output notebook path and chosen domain | Starter `.ipynb`; it is not executed or scientifically validated. |
| `notebook_workbench.execute-copy` | normal; Full; app_ready | `explicit` | Synthetic notebook without interactive input or original-data writes | Executed **copy**, logs and manifest; cell errors stay visible. |
| `coursework_notebook_fidelity_check` | normal; Core; app_ready_partial | `none` | Synthetic received notebook and any declared sidecars | Fidelity/portability findings; not a claim of identical scientific answers. |
| `notebook_branch_compare` | normal; Core; app_ready_partial | `none` | Two synthetic notebook/product branches in a copied folder | Missing/duplicate output comparison; a warning needs review. |
| `spectra_ascii_coursework_workbench` | expert CLI; Full; cli_only | `inline` | Synthetic reduced ASCII spectrum, optional copied notebook | Derived coursework bundle; inspect sampling and line/continuum choices. |
| `timeseries_forecasting_workbench` | normal; Full recommended; app_ready | `inline` | Regular synthetic CSV with date/value columns and held-out horizon | Forecast notebook and report; inspect frequency, leakage and uncertainty. |
| `inspect_data_container` | normal; Core; app_ready | `none` | Synthetic HDF5/NetCDF/Zarr/archive supported by the selected profile | Structure summary; inspect before extracting or converting. |
| `catalog_workbench.crossmatch-sky` | expert; Core dedicated environment; app_ready_partial | `none` | Two synthetic text tables with RA/Dec in **decimal degrees** and explicit radius | Match table; the guided form supports text tables, while binary tables need expert CLI. |
| `physical_qa` | normal; Core; app_ready | `none` | Synthetic FITS, spectrum or CSV | Bounded sanity report; suspicious ranges are warnings, not automatic corrections. |

## Additional backends, permissions, and recovery

The Core/Full profile in each row above is the complete **Python installation
choice** for the supported route; its exact packages are in the linked lock.
The following are extra requirements or optional branches that a profile does
not install. A local capability command needs no Ollama or cloud model by
default. Downloads use disk and network resources; a user-selected web solve
or a user notebook can transmit data or incur service charges. Review those
actions and the provider's current terms before execution. Every route needs
read access to a reviewed input copy and write access to a new output folder.
An ID absent from this table has no additional external backend **declared
here**; inspect its own `--help`, input format, and Environment result rather
than treating that absence as universal compatibility.

| Capability IDs or route | Extra setup, access, or possible cost | First check and recovery |
| --- | --- | --- |
| `external_astro_tools_preflight`, `stilts_workbench` | Java and a user-installed STILTS command/JAR (or supported TOPCAT mode) for the STILTS route; local subprocess and copied tables. | Run the [STILTS preflight](OPTIONAL_BACKENDS.md#java-stiltstopcat-and-apt). If blocked, configure the actual command/JAR and retry in a new run; use the separate native catalog route only after reviewing its method. |
| APT: `apt_workbench` | Separately installed APT, Java, APT command, and saved preferences; copied image and local process access. | Run [APT preflight](OPTIONAL_BACKENDS.md#java-stiltstopcat-and-apt). A missing executable or preferences is a controlled block; do not label it photometry. |
| `astrometry_net_workbench.preflight`, `astrometry_net_workbench.verify-existing-wcs` | The listed checks need a copied FITS/image and reviewed WCS; existing-WCS verification needs no solver. A **separate** local solve needs `solve-field` plus indexes; a separate web solve needs a key, network upload review, and the service's current terms. | Start with [preflight or existing-WCS QA](OPTIONAL_BACKENDS.md#astrometrynet). Neither result is a new solution. If solving is unavailable, keep the block and do not substitute an invented WCS. |
| `legacy_spectroscopy_envcheck`, `fxcor_iraf_workbench.prepare-session`, `fxcor_iraf_workbench.run-auto` | IRAF is external and needed for `run-auto`; the prepare step makes a separate ASCII-safe copy. XQuartz may be needed for IRAF tools. | Check [IRAF discovery](OPTIONAL_BACKENDS.md#legacy-spectroscopy-iraf-and-istarmod) and prepare a new copy. Missing IRAF must block `run-auto`; preserve the failed run and original data. |
| `istarmod_workbench.inspect-tree`, `istarmod_workbench.prepare-copy` | A user-provided tree with rights to use it and the legacy root-level layout; no upstream iSTARMOD tree is bundled. Current upstream compatibility is unproved. | Inspect a **copy** first, then prepare another output copy. Do not point later execution or cleanup at the original tree; retain layout warnings. |
| TEAREDUCE: `teareduce_router` | Core can report a route; Full supplies the copied-notebook launcher, but does not install TEAREDUCE. Actual operations need a separately installed kernel and reviewed user notebook. The GPL interaction remains under review. | Read the [external kernel route](OPTIONAL_BACKENDS.md#teareduce-documents-and-macos-apps). The healthcheck inspects only its launcher Python, not that kernel; a missing or unresolved backend remains blocked. |
| Document fallback: `document_intake_workbench` | Pandoc is an optional fallback for selected unreadable formats, not a Core prerequisite. | Check the extraction method; if the [fallback](OPTIONAL_BACKENDS.md#additional-document-and-notebook-format-helpers) is needed, verify `pandoc --version` and retry on a copy. Keep unreadable-file warnings. |
| `presentation_workbench.inspect`, `presentation_workbench.existing-deck-style-audit` | Full covers the documented Python presentation stack; an external LibreOffice export is a separate optional route with its own file conversion behavior. | Start with a copied PPTX and the report. If an optional renderer is absent, keep the inspection result separate from visual acceptance; do not claim a rendered deck was checked. |
| iWork: `iwork_workbench` | Pages/Keynote and macOS preview/export services are separate from Core; format-specific exports may need the app and local automation permission. | Inventory a synthetic bundle first. If export is unavailable, retain the inventory and the controlled block; do not edit the source. |
| Quick Look: `quicklook_bridge` | macOS Quick Look and a supported copied document; preview generation is visual evidence only. | Run its preflight on a copy. If unsupported, use the reported format limitation; do not claim a semantic review from a preview. |
| Keynote: `keynote_export` | Keynote plus macOS Apple Events permission for GUI export; this is an explicit local automation action. | Check the [Keynote route](OPTIONAL_BACKENDS.md#teareduce-documents-and-macos-apps) and destination. If permission or app discovery fails, keep the block and do not overwrite a deck. |
| TeX: `latex_workbench.compile` | `latexmk` or `pdflatex` from a separate TeX installation; neither is installed by Full. `scaffold` and `review` do not need the engine. | Check [the engine](OPTIONAL_BACKENDS.md#latex) before compiling a copied project. Preserve the log and failed run if a package or engine is missing; do not report a PDF. |
| `duckdb_workbench`, SQL parts of `cross_domain_data_workbench` | The DuckDB Python package is in Full, not Core; bounded read-only SQL is the safe first route. | Run the inline backend check. If absent, use Core inventory/profile functions and leave SQL explicitly unavailable. |
| Notebook execution: `notebook_workbench.execute-copy` | Full supplies the reviewed notebook stack, but the user's cells may require other packages, network access, or paid services. A notebook importing `pdf2image` additionally needs separately reviewed Python dependency and Poppler tools. | Inspect cells and run [notebook preflight](OPTIONAL_BACKENDS.md#additional-document-and-notebook-format-helpers) on a copy. Do not install missing extras into a validated environment or execute an unreviewed notebook. |

## Evidence and recovery

The registry declares 16 `core`, 10 `full`, and 29 `none` smoke tiers. Those
labels describe coverage classes, not the result of running a test on your
machine. The 29 `none` entries have a **maintainer diagnostic** matrix using
synthetic or preflight inputs. Its current source-preparation run on 24 September
2026 recorded 15 PASS, 11 WARNING, and three controlled blocks, with zero FAIL
and zero unmapped probes. That matrix does not execute every external backend
or prove end-to-end operation. Exact-commit publication evidence will be added
after the new source candidate is exported and validated.

For one selected capability, use this sequence:

1. Install Core or Full in a **new** `datanalysis` destination using
   [INSTALL.md](../INSTALL.md); verify the five-skill snapshot.
2. Set the skill root, Python, and a separate output folder in Settings.
3. Search the exact ID in **Capabilities**. Check its access/readiness state
   and use **Environment** plus any named preflight before supplying data.
4. Start with synthetic or copied inputs in a new run directory. A direct
   **Run Capability** action starts immediately, so check its inputs and output
   folder first. For a Chat-generated plan, review **Dry Run** before
   **Run Enabled**.
5. Read the structured status, `summary.json`, manifest, warnings, and outputs
   in **Jobs** and **Results**. Preserve failed runs; retry in a new directory.

If the app does not expose a legacy or CLI-only route, locate its owning skill
under `skills/`, run the script with `--help` using the selected Python, and
follow the printed argument contract. Do not infer that a green app catalog
entry means an optional program is installed. Use
[Workflow Requirements](WORKFLOW_REQUIREMENTS.md) for backend classes and
[Troubleshooting](TROUBLESHOOTING.md) for specific status/recovery steps.

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

The bundled public surface registry declares `registry_schema_version: 1`.
This field versions the registry format. The skill's `release` field versions
the skill distribution, and a tool's `contract_version` versions its result
envelope.

Scientific Workbench and the Python router read older registries with an
omitted schema field as version 1. An explicit version must be an unquoted
positive integer at the top level. A duplicate, malformed, or unsupported
version blocks registry loading and identifies the source file. Keep the
skill roots together as a matched set when updating a bundled registry.
An incompatible format change requires a new schema version and a documented
migration or compatibility alias.

When reproducing a guided command, keep free-text values that begin with a
hyphen in the same argument as their option. For example, use
`--find=-draft` or `'--title=-draft observations'`. Quote the complete argument
when the value contains spaces. The app uses this syntax for replacement text,
notebook and deliverable titles, forecasting fields, routing requests, and
reviewed crossmatch column names.

## Inspecting registered CLI arguments

From the checkout root, set `SW_PY` to the Python interpreter for your
[installed Core profile](../INSTALL.md). The exporter writes JSON to standard
output. Omit `--capability` to inspect all 61 registered commands, including the
six maintainer gates.

```bash
"$SW_PY" script/render_cli_contracts.py --capability catalog_workbench.crossmatch-sky
```

The version 1 export pairs each registry ID and owning script with the parser
reached by its own help command. Each parser record includes its positional
arguments, flags, arity, types, defaults, choices, accumulation behavior and
subcommands. A value under `default_relative_to_checkout` resolves from the
repository root. The portable validation workflow retains the full export as
`cli-contracts.json` with its diagnostic evidence.

Portable validation records commands generated from synthetic inputs by the
Swift app's default builder, dedicated forms and reviewed document replacement.
The exporter passes these arguments to the owning CLI parsers. It records
accepted capability IDs in `validated_guided_invocations` and names the checked
cases in `validated_guided_variants`. The CI check requires this evidence for
all 55 user-facing capabilities. Portable workflow tests separately verify
workflow execution and outputs.

For STILTS and APT the I/O contract lists the arguments and results for each
subcommand. Its top-level fields mirror the guided preflight so clients that
read flat contracts can still show the default route.

Retain an export from before a CLI change and compare it with the export from
the proposed revision. Use the same command selection in both exports.

```bash
"$SW_PY" script/check_cli_contract_compatibility.py baseline.json candidate.json
```

Exit 0 means the declaration comparison found compatible changes. Exit 1 lists
changes that require review, including removed commands or flags, new required
inputs, narrowed choices, changed defaults, unit changes and removed or retyped
result fields. Exit 2 indicates an unreadable or unsupported export. Preserve
the old route or flag as a documented alias where possible. If a change breaks
an established contract, raise its revision and document the migration, including
what existing scripts and result readers need to change. Keep the comparison
report with the release evidence. The comparison covers exported declarations
and complements the run-based checks for actual behavior.

The export describes argument syntax. Consult the
[setup matrix](CAPABILITY_SETUP_MATRIX.md) and the command's emitted summary
and manifest for scientific inputs, produced artifacts and run status.

The capabilities with an I/O contract also show **Inputs and outputs** in the
app and an `io_contract` in the export. Each revision defines the backend,
argument roles, scientific units, written files, and required summary fields
for completed and rejected runs. The known-answer gate checks those fields in
scientific synthetic runs. Portable validation exercises environment reports,
table profiling, container inspection, physical QA, notebook preparation and
review, and document intake, editing and review. Summary fields are under
`results` unless the contract sets `summary.container` to `root`. If
`summary.rejected_container` is set, it locates the fields for rejected runs.
A rejected command may write its diagnostic only to standard output when the
requested path cannot safely be used. Older installed skill snapshots can
still load the capability registry and run their supported routes.

## Run fingerprints

After preparing a command, Scientific Workbench fingerprints attached files
before execution. At finalization it compares those files and fingerprints the
products found inside the run folder. The app writes `run-provenance.json` with
the job outcome, available app and capability identifiers, and numbered file
references such as `input-1` and `output-1`. Tool-specific summaries and
manifests stay in the run folder with their existing formats.

The record includes the macOS version, app bundle version and build when
available, the release declared by the selected skill's registry, and the
tool contract version reported by a matching tool summary. The declared
release is a label from the installed registry. Compare the registry and
script hashes to identify the exact code, including local variations.

The command record retains supported flags, typed numerical values and public
choices for reviewed capability arguments. It refers to attached files and
destinations inside the run folder by numbered references. An output that
matches a destination file carries the same reference. Free text and
unrecognized arguments appear as withheld. The record describes the command
prepared by the app. The job outcome and tool summary report what happened.

Each input or output pass reads at most 64 MiB of regular files. Directory
contents, unreadable files and files beyond the budget have explicit states.
`contentUnchanged` reports equality of two successful SHA-256 observations.
The `limits` field identifies evidence still needed for reproduction. Each
entry in `reproductionRequirements` explains what to check or obtain. For
example, use the before-run hashes to match inputs, recover any withheld
arguments locally, and identify any unrecorded application or backend version.
Earlier records of schema 1 may only contain the `limits` codes.

The bundled tools can also record the Python implementation, version and
architecture at their entry point. The package inventory covers direct Core
and Full requirements whose installed versions the interpreter can report in
a public version format. It specifies what was installed in that Python
environment. Consult the tool's own report for external backends and subprocesses.
Older skill installations may omit this runtime observation, which the app
reports as missing evidence.

The provenance record retains a backend identifier when a reviewed tool
summary reports execution. Supported reports include STILTS, APT, IRAF/FXCOR,
LaTeX compilation, Keynote export, Quick Look, iWork and presentation previews.
Preflight and dry-run results do not establish that a backend ran. The app
also records approvals it applied for the output root, reviewed document
actions, the capability access control and restricted local automation.
An approved action can still fail, as shown by its job and tool outcomes.
Workflow jobs retain the plan's declared source and any matching planning
receipt. The receipt identifies the provider, the requested public model, the
model reported by the provider when available, and whether the app used the
response or fell back to a deterministic plan. It retains the applied approval
scope and data categories for a reviewed cloud planning request. Prompts,
attachment names, service URLs, credentials and private model identifiers are
omitted. A receipt records past approval for that request.

Workflow state schema 3 is the first version with a planning receipt. The app
preserves the original state file before migrating schema 1 or 2. Earlier plans
continue to load and report missing model or approval evidence where relevant.
The portable plan format retains its existing schema.

### Sharing the provenance record

Open the job's Results, find `run-provenance.json` in the artifacts, and use
**Reveal** to locate it in Finder. Copy that file by itself to share the
record. Review its hashes, timestamps and identifiers for suitability. The
recipient will need the inputs separately and may need to recover additional
evidence listed in `reproductionRequirements`. Review the contents of other
run-folder files individually before sharing them.

## Registry coverage

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
   **Run Capability** action starts immediately. For a Chat-generated plan,
   leave **Auto-run** off and review each enabled step's inputs, new output
   folder pattern, path safety, launcher, network caveat, consent, dependencies,
   estimate, and status. Use **Dry Run** to inspect a command preview with
   provisional run-folder paths; it executes no command and creates no run
   folders. **Auto-run** deliberately skips this manual review after planning.
7. Execute the smallest useful case and review **Jobs**, **Results**, the
   manifest, and the unchanged-input evidence. **Jobs** names the current
   app-level stage and last recorded state change; it does not infer an
   internal percentage from an external tool. Open **Results** from the
   selected job to inspect its retained artifacts.

An optional backend that is absent should normally produce a controlled block.
Do not relabel it as a pass, weaken the gate, or install unrelated dependencies
until the reported requirement has been reviewed.

For recovery steps and evidence to preserve, see
[Troubleshooting](TROUBLESHOOTING.md).

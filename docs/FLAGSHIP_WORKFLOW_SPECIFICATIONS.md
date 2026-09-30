# Provisional first workflows for Scientific Workbench

**Date:** 2026-09-30

**Baseline source:** public `main` at `c517c53`; the Dashboard example launcher is
implemented and locally checked on this later development branch

**Status:** design specification for P2.01 and P0.03; neither task is accepted

These choices follow the [user-needs desk research](USER_NEEDS_DESK_RESEARCH.md)
and the current [capability matrix](CAPABILITY_SETUP_MATRIX.md). No potential
user has been interviewed or observed using Scientific Workbench. Code and
registry inspection establish the current paths below; they do not establish
that a newcomer can complete them or that the scientific interpretation is
correct. A successful process or CI job is narrower evidence than either claim.

## Product focus

The provisional first user is an astronomy student or researcher with local
scientific files who wants a traceable first pass before interpreting data. The
first three journeys cover a small table, a FITS file, and a mixed research
folder. The astronomy candidates are **FITS inspection with WCS context** and
**two-catalog sky crossmatching**. We defer photometric calibration and radial
velocity as flagships until their assumptions, units, uncertainties, and
reference baselines can be reviewed at the same level.

The application already has **Capabilities**, **Jobs**, and **Results** views.
**Settings** selects the bundled skill root, Python interpreter, and a separate
output root. In Capabilities, a user chooses **Normal** or **Expert**, searches
for a capability, adds inputs, and starts a guided run. Jobs retains status and
logs; Results links artifacts to the job and can reveal the run folder. These
controls exist. **Dashboard** now prepares new synthetic example copies for the
first three journeys. On 2026-09-30, the maintainer completed these GUI paths
on the development Mac; no independent user has accepted them.

## P0.03: three launch journeys

The table distinguishes a path a developer can attempt today from the
experience required to close P0.03. The generated examples are described in
the [first-run example guide](SYNTHETIC_FIRST_RUN_EXAMPLES.md); paths under
`skills/` are relative to the repository root.
No user input or output should point to the same directory.

| Journey | Small input and profile | Current GUI path and expected evidence | Limit and missing acceptance work |
| --- | --- | --- | --- |
| Table profile | The Dashboard-generated `ops.csv` has three data rows and four columns. **Core**; no optional backend for this profile. The older bundled [`ops.csv`](../skills/scientific-data-notebooks/examples/tabular/ops.csv) remains an independent manual alternative. | Settings: select the Core interpreter, bundled skills, and a separate output root. Dashboard → **Prepare Small table** → Capabilities → **Normal** with `profile_table` and input selected → review expectation → **Run Capability** → select the job in **Jobs** → inspect `summary.json` and `manifest.json` through **Results**. Target check: three rows, four named columns, per-column types and missing counts. | Profiling does not infer measurement units, clean data, or validate an analysis. Direct bundled-backend and maintainer GUI checks passed; an uncoached GUI result remains open. |
| FITS inspection | Dashboard generates a synthetic 8 × 8 primary image with one NaN and a known TAN WCS; **Core**. The older [`mini_template.fits`](../skills/scientific-data-astro/examples/science/legacy_spectroscopy_mini/mini_template.fits) is a separate 1-D sample with no WCS. | Settings as above. Dashboard → **Prepare FITS image** → Capabilities → **Expert** with `inspect_fits` and input selected → confirm expert access → **Run Capability** → Jobs → Results → inspect `summary.json` and `manifest.json`. A direct local backend probe reported 63 finite pixels and the expected WCS keys. | The generic guided command does **not** request a PNG preview, so this is metadata inspection, not the proposed visual WCS journey. Display-only preview, complete WCS/scale presentation, and uncoached GUI trial remain open (P2.02, P0.03). No astrometric solution or calibrated measurement is implied. |
| Mixed folder | Dashboard generates a CSV, Markdown observation note, and readable one-page PDF in one folder. **Core** for intake and table inventory; Full/DuckDB only for an explicitly requested SQL branch. | Settings as above. Dashboard → **Prepare Mixed research folder** → Capabilities → **Normal** with `document_intake_workbench` and folder selected → run → Jobs/Results for intake artifacts; then select `cross_domain_data_workbench`, keep the same input folder, run, and inspect its separate inventory/report. Direct local probes of both backends passed without changing inputs. | The app does not combine both reports into one novice-facing journey. A predictable GUI handoff or linked result and an uncoached trial remain open. Document extraction can report unreadable formats; SQL availability is a separate Full-profile decision. |

On 2026-09-30, a direct script probe on the existing macOS Python 3.11.15
scientific environment ran the bundled `ops.csv` and `mini_template.fits`
without editing either input. Both commands exited 0 and produced a summary
and manifest in fresh run folders outside the repository. The table reported
three rows, four columns, and `original_modified: false`; its input SHA-256
remained `a6d564500a0c38060ddbb76016a00993f794c5a519122cb58796f74527f56e72`.
The FITS reported one primary HDU with 32 finite samples, `wcs: null`, and
`original_modified: false`; its input SHA-256 remained
`39e47f910c47a6af423d4fe1a7e32eab013f76c14d4dda584cea8fa96d058d1b`.
This probe checked backend behavior only, not the GUI or a fresh installation.

For each journey, the target acceptance observation is: a person outside the
project finds the example, starts the run, identifies the correct job, opens the
expected report or artifact, and explains the principal limitation **without
Terminal, code edits, or coaching**. Record the participant, app commit,
machine, selected profile, time, wrong turns, questions, failed steps, and
artifact paths. Do not mark P0.03 complete until this is observed. The
[M104 protocol](M104_ARCHITECTURE_AND_UX.md#external-usability-session-still-required)
provides the broader navigation and recovery observations.

## P2.01: provisional astronomy flagships

These are proposed priorities, not results of evaluating this app with users.
Both use local execution and a new output folder. The technical owner is the
repository maintainer, **interemi**, across the Swift integration and bundled
skill scripts; this names responsibility for the next implementation and
review, not third-party ownership of astronomy methods or external software.

| Candidate | Persona, example, and independent baseline | Method, output, units, and dependencies | Scientific limit and current readiness |
| --- | --- | --- | --- |
| FITS image and WCS inspection | Observational-astronomy student checking whether an image can be used downstream. Dashboard now generates a synthetic 8 × 8 image with a known reference pixel, reference sky coordinate, angular pixel scale, one nonfinite pixel, and declared pixel unit. On 2026-09-30, Astropy independently recovered `(150°, −30°)` at the reference pixel within `1e-9` degree. | `inspect_fits` enumerates HDUs and summarizes the image/header/WCS into `summary.json` plus `manifest.json`. Proposed preview is a **display-only** derived PNG in the run folder. Record `NAXIS`/pixel dimensions, pixel-unit header, celestial frame and coordinate units (degrees), pixel scale (arcsec/pixel), reference values, and any crop/NaN treatment. Core includes the reviewed FITS inspection path; no Astrometry.net solver is required. | Current app readiness is `app_ready` for the inspection command, but its guided default does not create the preview. WCS metadata does not establish calibration accuracy, a source position, or a science-quality image. P2.02 and independent user evaluation remain necessary. |
| Sky crossmatch of two text catalogs | Researcher comparing two small observing catalogs. Proposed fixture: two left rows and two right rows with explicit `ra_deg`/`dec_deg`; one pair separated by roughly 0.36 arcsec and one left source with no match inside a 1 arcsec radius. The baseline should calculate spherical angular separations independently and expect one matched and one unmatched left row, with a declared tolerance. | Capabilities → **Expert** → `catalog_workbench.crossmatch-sky` → **Add Files** for both CSVs → select left/right files, map four coordinate columns, confirm **decimal degrees**, enter a positive radius in **arcseconds**, then **Run Reviewed Crossmatch**. Jobs/Results should show the match CSV, `summary.json`, and `manifest.json` in a fresh run. Core must be the **dedicated scientific Python environment** documented for this route; the backend uses Astropy sky coordinates. No STILTS/TOPCAT is needed for this native path. | Registry readiness is `app_ready_partial`. The guided form covers CSV, TSV, ECSV, and delimited text, not FITS-table/Parquet/spreadsheet review. A nearest-neighbor match inside a radius does not resolve proper motion, epoch, duplicate counterparts, catalog selection effects, or physical association. P2.05 must provide the known-answer fixture and rejection cases; participant evaluation is still missing. |

The generated FITS fixture uses a TAN celestial WCS with `CRPIX1 =
CRPIX2 = 4.5`, `CRVAL1 = 150 deg`, `CRVAL2 = -30 deg`, `CDELT1 = -1/3600
deg/pixel`, `CDELT2 = +1/3600 deg/pixel`, and `BUNIT = adu`. At the reference
pixel, the expected world position is `(150 deg, -30 deg)`; an independent
Astropy check on 2026-09-30 recovered it within `1e-9` degree and measured
one arcsecond per pixel. The deterministic data array includes exactly one
NaN. This is generated synthetic data, not a measured instrument image.

The proposed crossmatch fixture can use these exact decimal-degree rows:

| File | `source_id` | `ra_deg` | `dec_deg` |
| --- | --- | ---: | ---: |
| Left | `L1` | 150 | -30 |
| Left | `L2` | 10 | 0 |
| Right | `R1` | 150 | -29.9999 |
| Right | `R2` | 200 | 0 |

At a 1 arcsec radius, `L1` should match `R1` at approximately 0.36 arcsec;
`L2` should remain unmatched. P2.05 must verify the separation with an
independent spherical calculation and set a numerical tolerance before this
becomes a regression fixture. The example contains no epoch or proper-motion
metadata, so it cannot support claims about real-source association.

### Decision and evidence still required

1. Extend the generated synthetic fixtures where needed, especially for the
   proposed crossmatch. Record generator, hashes, units, expected values,
   tolerances, and rejection cases. Do not copy DOCUS or a researcher's real
   data. The existing FITS and CSV examples remain untouched.
2. Run each proposed case on the exact checkout; compare actual summaries and
   artifacts with the independent baselines. An exit code alone is insufficient.
3. Complete the missing visual WCS and crossmatch GUI steps, then inspect
   their paths on the available Mac. The existing local walkthrough is useful
   engineering evidence, but it is not an independent usability result.
4. If a participant later becomes available, observe the journeys and ask which
   astronomy task matters in their actual work. Until then, keep the two
   priorities provisional and P2.01/P0.03 open.

This specification deliberately makes no claim that all three journeys are
finished, that any result is scientifically validated for real data, or that
the app has been manually tested on another Mac.

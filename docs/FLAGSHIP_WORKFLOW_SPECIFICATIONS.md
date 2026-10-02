# Provisional first workflows for Scientific Workbench

**Date:** 2026-10-01

**Source evidence:** the P0.03 preview and mixed-folder handoff were checked
locally at `5c89a15` and in hosted Core CI at `3d17d4a`

**Status:** P2.01 priority decision is integrated; the P0.03 internal technical
criterion passed locally and in exact-candidate hosted Core CI

These choices follow the [user-needs desk research](USER_NEEDS_DESK_RESEARCH.md)
and the current [capability matrix](CAPABILITY_SETUP_MATRIX.md). The
[research-led acceptance decision](RESEARCH_LED_ACCEPTANCE.md) replaces earlier
outside-participant gates with documented sources, known-answer fixtures, and
internal GUI checks. No potential user has been interviewed or observed using
Scientific Workbench. Code and registry inspection establish the current paths
below; they do not establish newcomer comprehension or scientific correctness.

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
on the development Mac. This is internal technical evidence only.

## P0.03: three launch journeys

The three paths were exercised on the exact local source as recorded in the
[P0.03 internal GUI acceptance record](P0_03_GUI_ACCEPTANCE_2026-10-01.md).
The generated examples are described in the
[first-run example guide](SYNTHETIC_FIRST_RUN_EXAMPLES.md); paths under
`skills/` are relative to the repository root.
No user input or output should point to the same directory.

| Journey | Small input and profile | GUI path and expected evidence | Limit and acceptance scope |
| --- | --- | --- | --- |
| Table profile | The Dashboard-generated `ops.csv` has three data rows and four columns. **Core**; no optional backend for this profile. The older bundled [`ops.csv`](../skills/scientific-data-notebooks/examples/tabular/ops.csv) remains an independent manual alternative. | Settings: select the Core interpreter, bundled skills, and a separate output root; save, reload registry, and refresh environment. Dashboard → **Prepare Small table** → Capabilities → **Normal** with `profile_table` and input selected → review expectation → **Run Capability** → select the job in **Jobs** → inspect `summary.json` and `manifest.json` through **Results**. The bundled-skill GUI run reported three rows, four named columns, and unchanged input. | Profiling does not infer measurement units, clean data, or validate an analysis. |
| FITS inspection | Dashboard generates a synthetic 8 × 8 primary image with one NaN and a known TAN WCS; **Core**. The older [`mini_template.fits`](../skills/scientific-data-astro/examples/science/legacy_spectroscopy_mini/mini_template.fits) is a separate 1-D sample with no WCS. | Settings as above. Dashboard → **Prepare FITS image** → Capabilities → **Expert** with `inspect_fits` and input selected → confirm expert access → **Run Capability** → Jobs → Results → inspect the WCS-projected PNG, `summary.json`, and `manifest.json`. The bundled-skill GUI run reported 63 finite pixels, the expected WCS keys, a visible PNG, and unchanged input. | The PNG is enabled only for the byte-matched generated fixture and is display-only. Real FITS files retain the metadata-only default pending P2.02 bounded-memory preview work. No astrometric solution or calibrated measurement is implied. |
| Mixed folder | Dashboard generates a CSV, Markdown observation note, and readable one-page PDF in one folder. **Core** for intake and table inventory; Full/DuckDB only for an explicitly requested SQL branch. | Settings as above. Dashboard → **Prepare Mixed research folder** → Capabilities → **Normal** with `document_intake_workbench` and folder selected → run → Jobs/Results for intake artifacts → **Inspect folder data** → review the retained folder in `cross_domain_data_workbench` → run → inspect its separate inventory/report and the reciprocal related-job links. Both bundled-skill GUI jobs passed with separate artifacts and unchanged inputs. | The handoff prepares a second job but does not run it or combine scientific findings. Document extraction can report unreadable formats; SQL availability is a separate Full-profile decision. |

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

The [internal GUI record](P0_03_GUI_ACCEPTANCE_2026-10-01.md) states the
initial conditions, actions, job-linked artifacts, unexpected registry reload
step, and post-run hash comparisons required by the
[internal protocol](RESEARCH_LED_ACCEPTANCE.md#evidence-to-retain-for-each-active-task).
The [exact-candidate hosted Core run](https://github.com/interemi/scientific-workbench-public/actions/runs/36996165055)
passed on macOS 15 arm64 and Intel; the optional Full job was skipped. This
author-run walkthrough does not measure discoverability for an unfamiliar person.

## P2.01: provisional astronomy flagships

These are proposed priorities, not results of evaluating this app with users.
Both use local execution and a new output folder. The technical owner is the
repository maintainer, **interemi**, across the Swift integration and bundled
skill scripts; this names responsibility for the next implementation and
review, not third-party ownership of astronomy methods or external software.

| Candidate | Persona, example, and independent baseline | Method, output, units, and dependencies | Scientific limit and current readiness |
| --- | --- | --- | --- |
| FITS image and WCS inspection | Observational-astronomy student checking whether an image can be used downstream. Dashboard now generates a synthetic 8 × 8 image with a known reference pixel, reference sky coordinate, angular pixel scale, one nonfinite pixel, and declared pixel unit. On 2026-09-30, Astropy independently recovered `(150°, −30°)` at the reference pixel within `1e-9` degree. | `inspect_fits` enumerates HDUs and summarizes the image/header/WCS into `summary.json` plus `manifest.json`. The known generated fixture also produces a **display-only** PNG in the run folder with celestial axes. Record `NAXIS`/pixel dimensions, pixel-unit header, celestial frame and coordinate units (degrees), pixel scale (arcsec/pixel), reference values, and any crop/NaN treatment. Core includes the reviewed FITS inspection path; no Astrometry.net solver is required. | Current app readiness is `app_ready` for the inspection command. The automatic preview is limited to the exact generated fixture; general bounded-memory FITS previews remain P2.02 work. WCS metadata does not establish calibration accuracy, a source position, or a science-quality image. The internal GUI and hosted Core checks passed for this candidate. |
| Sky crossmatch of two text catalogs | Researcher comparing two small observing catalogs. Proposed fixture: two left rows and two right rows with explicit `ra_deg`/`dec_deg`; one pair separated by roughly 0.36 arcsec and one left source with no match inside a 1 arcsec radius. The baseline should calculate spherical angular separations independently and expect one matched and one unmatched left row, with a declared tolerance. | Capabilities → **Expert** → `catalog_workbench.crossmatch-sky` → **Add Files** for both CSVs → select left/right files, map four coordinate columns, confirm **decimal degrees**, enter a positive radius in **arcseconds**, then **Run Reviewed Crossmatch**. Jobs/Results should show the match CSV, `summary.json`, and `manifest.json` in a fresh run. Core must be the **dedicated scientific Python environment** documented for this route; the backend uses Astropy sky coordinates. No STILTS/TOPCAT is needed for this native path. | Registry readiness is `app_ready_partial`. The guided form covers CSV, TSV, ECSV, and delimited text, not FITS-table/Parquet/spreadsheet review. A nearest-neighbor match inside a radius does not resolve proper motion, epoch, duplicate counterparts, catalog selection effects, or physical association. P2.05 must provide the known-answer fixture and rejection cases; internal GUI and artifact checks are still missing. |

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
`L2` should remain unmatched. A separate Python standard-library calculation
using the haversine spherical-angle formula returned
`0.359999999999` arcsec for `L1`–`R1` on 2026-09-30. P2.05 must run the
backend against this known-answer case and set a numerical tolerance and
rejection cases before it becomes a regression fixture. The example contains
no epoch or proper-motion metadata, so it cannot support claims about
real-source association.

The [research-led priority decision](RESEARCH_LED_ACCEPTANCE.md#astronomy-priority-decision)
puts FITS/WCS inspection first because its documented task and known-answer
image already have a reviewed local route. Sky crossmatching is second: its
method is documented by TOPCAT and the proposed angular baseline is simple,
but its GUI route is partial. This is a feasibility order, not an observed
preference ranking of Scientific Workbench users.

### Implementation evidence still required

1. Extend the generated synthetic fixtures where needed, especially for the
   proposed crossmatch. Record generator, hashes, units, expected values,
   tolerances, and rejection cases. Do not copy DOCUS or a researcher's real
   data. The existing FITS and CSV examples remain untouched.
2. Run each proposed case on the exact checkout; compare actual summaries and
   artifacts with the independent baselines. An exit code alone is insufficient.
3. Retain the completed synthetic visual WCS GUI evidence and complete the
   crossmatch GUI steps under P2.05 from a recorded initial state. The existing
   walkthrough is useful engineering evidence, but it does not measure
   unfamiliar-user comprehension.
4. Retain the P0.03 acceptance record and its exact-candidate Core CI link.
   P2.01 is a research-backed prioritization decision; its subsequent
   implementation and regression cases belong to P2.02 and P2.05. Retain user
   preference as an unmeasured product hypothesis.

This specification makes no claim that the journeys have been used by an
unfamiliar person, that any result is scientifically validated for real data,
or that the app has been manually tested on another Mac.

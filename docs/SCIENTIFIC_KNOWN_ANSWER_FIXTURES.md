# Scientific known-answer fixtures

This page describes the small, synthetic astronomy cases checked by
[`script/check_scientific_known_answers.py`](../script/check_scientific_known_answers.py).
They test the bundled backend and its artifacts against values calculated
independently of the backend. Use them as regression checks. Scientific
validation of observed data requires separate evidence.

## Reproduce the checks

Prepare the documented Python 3.11 Core environment in [INSTALL.md](../INSTALL.md).
From the repository root, run:

```sh
<path-to-core-python> script/check_scientific_known_answers.py \
  --output-dir <new-directory-outside-the-repository>
```

Replace both angle-bracketed values with real paths; the output directory
must **not exist yet**. The script creates its inputs and results there, never
edits a checked-in example or an original research file, and refuses an output
directory inside the checkout. It retains command logs, summaries, manifests,
artifacts, and `verification.json`, including a source-commit identifier and
whether the working tree was clean. A `PASS` from a dirty tree is local
engineering evidence until the exact committed tree passes hosted CI.
`script/run_portable_core.py` also runs these cases after its environment and
portable smoke checks. GitHub Actions retains the compact verification JSON
and the generated example report.

## Rebuild and compare the example set

The command above generates an `example-report/` directory, with a CSV
comparison and two labeled figures. The verification JSON lists their
relative paths, byte counts and SHA-256 values. The reported deviations
must meet the stated tolerance for each metric. The figures preserve the
PNG bytes emitted by the run, with origin labels in the filenames and
captions. The complete input and output manifests are in the surrounding
known-answer evidence directory.

**Synthetic table with reference columns.** These cases use deterministic,
project-authored inputs. **Reference** identifies fixture constants or
independent calculations. **Observed** is reserved for measurements of real
phenomena. This example set includes only synthetic data.

| Synthetic case | Question and method | Reference and expected outputs |
| --- | --- | --- |
| FITS/WCS | Can the inspector preserve the image structure, finite pixel count and signed WCS axes? Inspect the 8 × 8 generated FITS with Astropy and the bundled tool. | 63 finite pixels, ICRS reference at (150°, −30°), signed axes of −1 and +1 arcsec/pixel. Summary, manifest and a display-only PNG. |
| Sky crossmatch | Which synthetic catalog pairs are inside the 1 arcsec radius? Compare Astropy's result with a standard-library haversine calculation. | One pair, L1–R1, at approximately 0.36 arcsec, with tolerance `1e-6` arcsec. ECSV, summary and manifest. |
| Photometric calibration | Can a weighted fit recover injected magnitude, airmass and color terms? Fit the three standards using their explicit magnitude uncertainties. | Coefficients of 1.2 mag, −0.2 mag per unit airmass and 0.2 mag per mag of color, with tolerance `1e-12` in each unit. Coefficient CSV, summary, manifest and a residual plot. The fit has zero residual degrees of freedom. |
| Li I equivalent width | Does the backend integrate a synthetic absorption line over the intended wavelength interval? Compare with the trapezoid sum over the known samples. | 90 mÅ, with tolerance `1e-7` mÅ. Measurement CSV, summary, manifest and a figure showing the selected windows. |

Use the [capability requirements](WORKFLOW_REQUIREMENTS.md) to review tool
inputs, assumptions and limits before substituting a real dataset.

## FITS image and WCS

The generator writes the exact 5,760-byte FITS fixture produced by the app's
first-run example service. Its SHA-256 is
`c40732799d2792ed9131899c2ad5a3b13317004a96e4d40a0d6aa959afc740de`.
It has one 8 × 8 primary image, 63 finite pixels, one NaN, a declared `adu`
pixel unit, ICRS TAN WCS with degree axes, and a reference sky coordinate
of `(150°, −30°)` at pixel `(4.5, 4.5)` in FITS convention. Its signed axes
are −1 and +1 arcsec/pixel. Astropy reads the generated header and checks
these known values; the bundled `inspect_fits` command must then report the
same structure, signed increments and units and produce a display-only WCS PNG
plus a summary and manifest. The verification checks the path, byte count and
SHA-256 of every declared input and output against its retained file.
The crop check compares preview pixel `(0, 0)` with full-image pixel `(2, 1)`
in zero-based coordinates using the WCS applied to the rendered PNG.
The input hash must remain unchanged. The PNG is a visual orientation aid,
not a calibrated image or an astrometric accuracy measurement.

A second FITS fixture contains a 1,030 × 1,028 scaled integer image and a
binary table. The distributed image sample must preserve the physical value
of 5.5 adu and count the sampled `BLANK` as nonfinite. The automatic quicklook
must record the centered 1,024 × 1,024 region in zero-based coordinates. A
table-only fixture must still expose its column and row counts, with the
summary and provenance preserved when a PNG is unavailable. The checks
verify the input and output hashes in both cases.

The backend CLI requests this mode with `--preview <output.png>
--preview-if-available`. A large image uses the centered region unless an
explicit `--crop x0,y0,width,height` is supplied. The summary labels sampled
statistics and records the preview HDU, region, plane indices, and axes.
A display region does not change the statistics of the source HDU. Tiled
images with a tile larger than the quicklook budget retain their metadata
and report the sampling limit.

In Scientific Workbench, **Results** opens the quicklook when a PNG was
produced. Use **Inspect FITS summary** or select `summary.json` to switch
among HDUs and read dimensions, selected header cards, the sampled
nonfinite count, and WCS metadata. **Raw JSON** exposes the retained
summary. The displayed angular scale is the projection-plane increment
at the reference pixel. The app requests the bounded quicklook when the
configured skill registry advertises it. Earlier registries keep the
metadata-only route for ordinary inputs and the generated sample still
requests its quicklook.

The FITS inspector can render a new crop or look up a pixel in a selected
image HDU when the configured registry advertises that operation. Enter X
and Y as zero-based coordinates in the source image. A cube uses the first
plane along its leading axes. A crop previews up to 1,024 pixels per side.
Each action creates a separate run with its own provenance. Pixel lookup
reports the recorded value and unit, plus world axes calculated using
Astropy and the HDU WCS when available. A nonfinite value is flagged, and a
data-quality mask is available through its own HDU. The synthetic check
confirms that source pixel `(2, 1)` reports 10 adu and the same world
coordinates with or without the display crop.

On 2026-11-24, a local SwiftPM app walkthrough used a synthetic FITS with
an empty primary HDU, the 8 × 8 image in `SCI`, and its nonfinite-pixel
mask in `DQ`. Results showed the three HDUs, one nonfinite SCI pixel,
`adu`, ICRS TAN axes, and a scale of 1 arcsec/pixel on each axis. A DQ
lookup at `(1, 1)` returned `1 flag` with no WCS. A separate SCI crop at
`(1, 1)` produced a 4 × 4 display-only quicklook with WCS. The SCI lookup
at `(2, 1)` returned `10 adu` and ICRS coordinates of approximately
`(150.000481129°, −30.000694444°)`. Manifest hashes matched the preserved
input, summaries, and preview PNGs. The preview and inspector controls
were checked at the minimum supported window width on the maintainer's Mac.

## Two-catalog sky crossmatch

The generated CSVs declare `source_id`, `ra_deg`, and `dec_deg` in decimal
degrees. The left catalog contains `L1` at `(150, −30)` and `L2` at `(10, 0)`;
the right catalog contains `R1` at `(150, −29.9999)` and `R2` at `(200, 0)`.
Their SHA-256 hashes are, respectively,
`4f77826692c8b2006a7c18f02da2d43d03467b8ab75fe6967bfcf56abe2d84c3`
and
`10937a93aee22bb8f8767e864fe193e2262e1a4915f7677106d11e2b866abab1`.
At a 1 arcsec radius, the expected output is one pair, `L1`–`R1`, and one
unmatched left row. A standard-library haversine calculation supplies an
independent baseline of approximately 0.36 arcsec; the output separation
must agree within `1e-6` arcsec. The check reads the ECSV artifact rather
than relying on process status alone, and verifies the input and output
hashes in the manifest.

The same fixture also checks controlled rejection of a zero radius, a
missing declination column, non-finite RA, RA outside the accepted range,
and an output path that collides with an input. No scientific output may be
written for those cases. A 0.1 arcsec radius instead yields a successful
zero-match result with a `WARNING` app status. The original catalog hashes
must remain unchanged throughout.

This exercise does not account for observation epoch, proper motion,
uncertainty, duplicate counterparts, selection effects, or physical
association. A match inside a radius is only a geometric candidate.

## Evidence and limits

On 2026-10-02, the direct known-answer check passed on the maintainer's
macOS 27.0.1 arm64 Mac in a Python 3.11.15 Core environment. The actual
backend separation was `0.3599999999694744` arcsec, versus an independent
baseline of `0.3599999999807416` arcsec. The local integrated Core run
passed 23/23 feature cases and preserved 1,926/1,926 distribution snapshot
entries. These runs preceded the Phase 3 commit; their verification files
correctly mark the working tree as unclean.

On 2026-10-03, the author also ran the two-file guided crossmatch from a
fresh, isolated GUI session using the modified local source in an ad hoc test
bundle. The Expert form accepted both synthetic CSVs, four decimal-degree
coordinate mappings, and a 1 arcsec radius. Jobs reported exit code 0,
`app_status: PASS`, one `L1`–`R1` match, one unmatched left row, and
`original_modified: false`. Results listed the output ECSV, summary, and
manifest; the ECSV contained the expected pair and separation. The input
hashes remained the two values above, and the output ECSV SHA-256 was
`bf4829bc3911512d9a82a85a22712969d6cf9ca3f1a67adc1cb194814a405ff6`.
The manifest's recorded input and output hashes matched the retained files.
This check caught a missing `artifacts/` parent directory on the first GUI
attempt; the store now creates it after output-root safety checks, with a
Swift regression test. That initial GUI build labeled the ECSV artifact
`unknown` and offered no inline preview, so its table content was checked
from the retained file. A later local build recognizes the ECSV as a table
and exposes a bounded text preview; its [separate evidence stages and
maintainer interpretation](EVIDENCE_STAGES.md) are documented independently.

A fresh integrated Core rerun on 2026-10-03 passed 23/23 feature cases,
including the known-answer check, and preserved 1,926/1,926 distribution
snapshot entries. Its verification JSON again records the uncommitted source
state; the output is local evidence rather than hosted exact-commit evidence.

The [Core run at PR head `02393f4`](https://github.com/interemi/scientific-workbench-public/actions/runs/37114235603)
passed on macOS 15 arm64 and Intel; the separate
[Full locked run](https://github.com/interemi/scientific-workbench-public/actions/runs/37114262270)
also passed at that head. After [PR #23](https://github.com/interemi/scientific-workbench-public/pull/23)
merged, the [Core run on `main`](https://github.com/interemi/scientific-workbench-public/actions/runs/37114939541)
passed on both architectures. The GUI evidence above remains an author-run
technical check on one Mac, not a manual test on another Mac, an evaluation
with an unfamiliar user, or scientific validation of real data.

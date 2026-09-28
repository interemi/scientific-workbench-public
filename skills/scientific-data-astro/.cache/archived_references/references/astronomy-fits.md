# Astronomy and FITS Guide

## Use This Reference For

- FITS image or table inspection
- astronomy or astrophysics workflows
- CCD reduction, calibration, photometry, spectroscopy, or catalog work
- DS9-, IRAF-, APT-, or TopCat-like requests that should be reproduced with code

## Recommended Python Stack

- `astropy`: FITS I/O, WCS, tables, units, coordinates, time
- `numpy` and `scipy`: numerical analysis
- `matplotlib`: quicklook plots and publication-oriented figures
- `ccdproc`: bias, dark, flat, reduction pipelines
- `photutils`: source detection, apertures, background estimation, photometry
- `specutils`: spectral analysis
- `astroquery`: archive access
- `regions`: region parsing and overlays
- `reproject`: image reprojection
- `lightkurve`: light curves and time-series astronomy

## FITS Inspection

Start with:

```bash
python3 scripts/inspect_fits.py /path/to/file.fits
python3 scripts/inspect_fits.py /path/to/file.fits --preview quicklook.png
```

Check these header families early when they exist:

- target and acquisition: `OBJECT`, `DATE-OBS`, `MJD-OBS`, `EXPTIME`, `FILTER`
- detector or calibration: `GAIN`, `RDNOISE`, `SATURATE`, `BZERO`, `BSCALE`, `BUNIT`
- WCS: `CTYPE*`, `CRVAL*`, `CRPIX*`, `CD*`, `PC*`, `CDELT*`
- organization: `EXTNAME`, `BUNIT`, telescope and instrument keywords

If the file is a multi-extension FITS, inspect every HDU before assuming where the science data lives.

## Astrometric Calibration With Astrometry.net

If the job is really a web plate solve rather than a local WCS inspection, prefer:

```bash
python3 scripts/astrometry_net_workbench.py preflight image.fits --summary-json astrometry_preflight.json
```

and then, when you have an API key:

```bash
python3 scripts/astrometry_net_workbench.py solve-web image.fits \
  --output-dir astrometry_solve \
  --summary-json astrometry_solve/summary.json
```

The workbench keeps the original image untouched, infers useful hints from the FITS header when possible, and downloads Astrometry.net products such as a WCS file or WCS-bearing FITS into a separate output folder.

## DS9-Like Operations In Code

Translate visual inspection tasks into code artifacts:

- quicklook image with percentile stretch
- cutout around a target
- pixel statistics and masks
- WCS-aware display
- region or aperture overlays
- header sanity checks

Prefer saved PNGs or notebook cells over one-line textual summaries when the user needs visual confirmation.

For v1.7 guidance on which FITS/RGB, crossmatch, preflight, manifest, and visual-QA patterns can be reused outside astronomy without pretending the astro contract is general, see `references/astro-transferable-patterns.md`.

## Batch RGB From FITS Trees

When many FITS files must become RGB or pseudo-RGB visual products, use the narrow batch route instead of writing a project-specific script from scratch:

```bash
python3 scripts/datanalysis_env.py run-tool fits_rgb_batch \
  --input-root /path/to/fits_tree \
  --output-dir /path/to/rgb_products \
  --clean-derived \
  --summary-json /path/to/rgb_products/summary.json
```

Read `references/fits-rgb-workflow.md` before using the outputs in a report or deck. The key rule is to align final filter stacks between bands: use WCS reprojection when valid WCS exists, use phase-correlation fallback only when WCS is absent or broken, and record the method in the manifest/QA report.

## IRAF-Like Reduction Mindset

For detector data, keep the pipeline explicit:

1. bias or overscan correction
2. dark correction when appropriate
3. flat-fielding
4. bad-pixel or cosmic-ray handling
5. alignment or reprojection
6. stacking or combination
7. photometry or extraction

Do not mix calibrated and uncalibrated files without naming that choice clearly.

Useful helper:

```bash
python3 scripts/reduce_ccd_batch.py \
  --master-bias /path/to/master_bias.fits \
  --science /path/to/raw1.fits \
  --science /path/to/raw2.fits \
  --output-dir /tmp/reduced
```

The helper can also build master calibration frames from repeated `--bias`, `--dark`, and `--flat` inputs when precomputed masters are not available.

## Aperture Photometry Pattern

Run the native helper through the scientific environment, for example `python3 scripts/datanalysis_env.py run-tool aperture_photometry image.fits --center X Y`; do not assume the shell's default `python3` includes Astropy.

APT-like requests usually need:

- source position definition
- aperture radius
- background annulus
- local background subtraction
- error estimate
- zero-point or calibration step if magnitudes are required

Useful libraries:

```python
from photutils.aperture import CircularAnnulus, CircularAperture, aperture_photometry
from astropy.stats import sigma_clipped_stats
```

Call out whether fluxes are instrumental or calibrated. If calibrated, record the zero point and any extinction or color terms used.

If the user explicitly needs Aperture Photometry Tool rather than a Python-native photutils route, keep APT optional and preference-driven:

```bash
python scripts/external_astro_tools_preflight.py --require-apt \
  --apt-preferences /path/to/APT.pref \
  --summary-json apt_preflight.json

python scripts/apt_workbench.py run-batch \
  --apt-command /path/to/APT.csh \
  --apt-preferences /path/to/APT.pref \
  --image image.fits \
  --source-list sources.lst \
  --output-table APT.tbl \
  --summary-json apt_run.json \
  --manifest-json apt_run_manifest.json
```

Read `references/external-astronomy-tools.md` first. APT batch results depend on saved GUI preferences such as aperture radius, annulus, and whether source-list coordinates are pixels or sky positions.

For a compact standard-star calibration step after instrumental photometry, use:

```bash
python3 scripts/datanalysis_env.py run-tool photometric_solution standards.ecsv \
  --inst-mag-col inst_mag \
  --std-mag-col std_mag \
  --airmass-col airmass \
  --output-json photometric_solution.json \
  --coefficients-csv photometric_solution_coeffs.csv \
  --residual-csv photometric_solution_residuals.csv \
  --residual-plot photometric_solution.png
```

If a color term matters, add `--color-col ... --include-color-term`. Prefer a modest first-order fit unless the observing setup really justifies more complexity.

## Detector Noise And SNR Planning

Before promising a photometric precision level, estimate whether the regime is:

- source-shot-noise-limited
- background-limited
- read-noise-limited
- or mixed

Useful helper:

```bash
python3 scripts/photometry_noise_budget.py \
  --source 25000 \
  --sky-per-pixel 40 \
  --dark-per-pixel 0.2 \
  --read-noise 4.5 \
  --n-pixels 80 \
  --sky-estimate-pixels 600 \
  --n-frames 3 \
  --units electrons \
  --output-json noise_budget.json \
  --report-md noise_budget.md
```

Treat the result as a planning or QA estimate. It is not a substitute for full instrument characterization.

## Detector Practicalities

Borrow a detector-minded habit before deeper analysis:

- check linearity and saturation risk
- distinguish counts in ADU from electrons
- keep gain and read-noise assumptions explicit
- do not interpret small residual trends as astrophysical if detector or airmass systematics are still plausible

## Spectroscopy Pattern

Check before fitting or measuring lines:

- wavelength unit and reference frame
- flux unit and normalization
- telluric, sky, or continuum treatment
- resolution or line-spread function assumptions
- uncertainty array availability

For line measurements, report:

- continuum choice
- fitting window
- model family
- parameter uncertainties or fitting caveats

## TopCat-Like Table Operations

Use code to reproduce catalog operations:

- filtering and column math
- joins by key
- coordinate cross-match
- sky separation cuts
- scatter plots, density plots, histograms
- export to CSV, ECSV, FITS, or VOTable

Typical coordinate match pattern:

```python
from astropy.coordinates import SkyCoord
import astropy.units as u

c1 = SkyCoord(ra=table1["ra"] * u.deg, dec=table1["dec"] * u.deg)
c2 = SkyCoord(ra=table2["ra"] * u.deg, dec=table2["dec"] * u.deg)
idx, sep2d, _ = c1.match_to_catalog_sky(c2)
mask = sep2d < 1.0 * u.arcsec
```

For large catalog work, VOTable validation, or report-ready TOPCAT/STILTS command provenance, use the optional STILTS wrapper:

```bash
python scripts/external_astro_tools_preflight.py --require-stilts \
  --summary-json stilts_preflight.json

python scripts/stilts_workbench.py crossmatch-sky gaia.csv local.csv matched.csv \
  --left-ra ra --left-dec dec \
  --right-ra ra --right-dec dec \
  --radius-arcsec 1.0 \
  --ofmt csv \
  --summary-json match.json \
  --manifest-json match_manifest.json
```

Keep the TOPCAT GUI as an interactive inspection tool, not an automated backend. Prefer `scripts/catalog_workbench.py` for compact Python-native work and `scripts/stilts_workbench.py` when STILTS reproducibility or table-format breadth is the real value.

Preserve units and column metadata when possible. Converting too early to `pandas` can silently drop astronomy metadata.

## Common Failure Modes

- degrees vs radians confusion
- pixel origin mismatches
- north-east orientation assumptions in images
- `JD` vs `MJD` vs `BJD`
- masked values being treated as real numbers
- metadata loss after converting tables
- WCS keywords present but incomplete
- logarithmic plots without clear labels

When a result looks suspicious, check metadata before changing the science.

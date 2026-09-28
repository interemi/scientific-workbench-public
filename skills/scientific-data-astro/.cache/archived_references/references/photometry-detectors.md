# Photometry And Detector Planning

## Use This Reference For

- standard-star photometric calibration
- zero points, first-order extinction, and optional color terms
- detector-noise and imaging-SNR planning
- practical CCD/imaging sanity checks before deeper reduction

## Why This Exists

This skill now includes two compact utilities that translate common textbook photometry and detector ideas into reproducible outputs:

- `scripts/photometric_solution.py`
- `scripts/photometry_noise_budget.py`

The goal is practical calibration and planning, not a giant observatory pipeline or a full detector simulator.

For the v1.7 non-astronomy transfer matrix covering sensor ROI noise, first-order instrument calibration, light physical QA, and measurement-series intake, see `references/real-world-measurement-patterns.md`.

APT is treated as an optional external backend, not as the default photometry engine. Use it when a coursework, collaborator, or comparison explicitly requires Aperture Photometry Tool output. Otherwise prefer Python/photutils because the aperture, annulus, background, and calibration choices live directly in code.

## Standard-Star Photometric Solution

Use `scripts/photometric_solution.py` when you already have a table of standards with:

- instrumental magnitude
- catalog or standard magnitude
- airmass
- optionally a color index and measurement uncertainty

The fitted model is:

```text
std_mag - inst_mag = zero_point + extinction * airmass (+ color_term * color)
```

Typical command:

```bash
python3 scripts/datanalysis_env.py run-tool photometric_solution standards.csv \
  --inst-mag-col inst_mag \
  --std-mag-col std_mag \
  --airmass-col airmass \
  --color-col b_minus_v \
  --include-color-term \
  --error-col offset_err \
  --output-json solution.json \
  --coefficients-csv coefficients.csv \
  --residual-csv residuals.csv \
  --residual-plot residuals.png \
  --report-md report.md
```

Use it for:

- nightly zero-point estimates
- first-pass extinction checks
- checking whether a color term is warranted
- residual inspection before trusting a calibration

Do not oversell the result if:

- the airmass span is narrow
- the color span is narrow
- you only have a few standards
- one or two stars dominate the residual pattern

## Noise Budget And SNR

Use `scripts/photometry_noise_budget.py` when you want a first-order answer to questions like:

- is this exposure sky-limited or read-noise-limited?
- what SNR should I expect for an aperture measurement?
- how much does my background annulus size matter?

Typical command:

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
  --output-json snr.json \
  --report-md snr.md
```

The utility reports:

- total source, sky, and dark electrons
- source-shot, sky, dark, read, and background-estimation noise terms
- total noise and SNR
- dominant noise contributor
- a simple operating-regime label such as `background-limited` or `read-noise-limited`

## Transferable Sensor/ROI Noise Pattern

Although the entrypoint was born from aperture photometry, its reusable core is broader: first-order signal-to-noise accounting for a measured region of interest when independent noise terms add in quadrature.

For non-astronomy sensor or imaging work, map the terms explicitly:

- `--source`: measured signal above background in the ROI, per frame in input units
- `--sky-per-pixel`: ambient, baseline, bias-subtracted background, or clutter level per ROI pixel
- `--dark-per-pixel`: sensor leakage, thermal dark current, or other exposure-time background per ROI pixel
- `--read-noise`: per-pixel electronics/readout noise in electrons
- `--n-pixels`: ROI footprint used for the measurement
- `--sky-estimate-pixels`: pixels used to estimate the background or baseline level

Example non-astro use: a machine-vision or lab sensor ROI where the question is whether measurement repeatability is limited by the signal itself, background, readout electronics, or baseline estimation.

```bash
python3 scripts/photometry_noise_budget.py \
  --source 4200 \
  --sky-per-pixel 12 \
  --dark-per-pixel 0.3 \
  --read-noise 2.1 \
  --n-pixels 64 \
  --sky-estimate-pixels 800 \
  --n-frames 5 \
  --units electrons \
  --summary-json sensor_roi_noise_summary.json \
  --report-md sensor_roi_noise_report.md \
  --manifest-json sensor_roi_noise_manifest.json
```

Keep the interpretation honest:

- the model is transferable when the measurement can be expressed as signal, background, dark/leakage, read noise, ROI size, and baseline-estimation area
- it is not a full camera, microscopy, medical-imaging, industrial-vision, or laboratory-instrument simulator
- do not use the astronomy labels to hide missing domain assumptions; rename them in the surrounding report if the user-facing deliverable is non-astro

## Detector-Side Sanity Checks

Before trusting any photometric or imaging result, check:

- whether the detector was used in its roughly linear regime
- whether the brightest pixels may be saturating
- whether gain and read-noise values are known or only assumed
- whether the background estimate comes from enough pixels
- whether the reported magnitudes are instrumental or calibrated

## Optional APT Bridge

Use `scripts/apt_workbench.py` only after APT has been configured manually and its preferences have been saved. The saved `APT.pref` must be treated as scientific provenance because it controls aperture radius, annulus, background mode, source-list coordinate interpretation, and other batch behavior.

Minimal route:

```bash
python scripts/apt_workbench.py preflight \
  --apt-preferences /path/to/APT.pref \
  --summary-json apt_ready.json

python scripts/apt_workbench.py prepare-source-list sources.csv sources.lst \
  --x-col x --y-col y --id-col id

python scripts/apt_workbench.py run-batch \
  --apt-command /path/to/APT.csh \
  --apt-preferences /path/to/APT.pref \
  --image image.fits \
  --source-list sources.lst \
  --output-table APT.tbl \
  --summary-json apt_run.json \
  --manifest-json apt_run_manifest.json

python scripts/apt_workbench.py parse-results APT.tbl apt_results.csv
```

If APT is absent or `APT.pref` is missing, the correct state is blocked with an explanation. Do not infer aperture settings silently.

## What Not To Add By Default

These compact tools are deliberate. Avoid forcing in:

- full multi-parameter atmospheric modeling
- second-order color corrections by default
- full exposure-time calculators for every instrument
- detector-physics models that need detailed instrument-specific inputs

If the user truly needs those, treat them as a separate workflow rather than bloating the stable core.

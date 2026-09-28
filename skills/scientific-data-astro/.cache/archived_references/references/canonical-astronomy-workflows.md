# Canonical Astronomy Workflows

Use this reference when the user is asking for one of the astronomy workflows that deserve a higher-quality path than a one-off script:

- exoplanet or transit photometry from a time-series of FITS images
- 2D spectroscopy that should end in extracted, calibrated, and report-ready products

For manual-in-the-loop radial-velocity fitting with `Systemic`, use `references/radial-velocity-systemic.md` instead of this file. That route is intentionally centered on exported figures, validated session manifests, and report-building rather than on a native reduction pipeline.

Treat this as a deeper astronomy reference, not as the main front door of the skill. The normal entry should happen first through the `astronomy observational` routing in `SKILL.md`.

## 1. Exoplanet Time Series

Primary entrypoint:

```bash
python3 scripts/exoplanet_timeseries_workbench.py /path/to/sequence_dir --object TOI-1811 --output-dir out
```

What it does:

- inventories the sequence and compatible bias, dark, and flat frames
- builds masters when possible
- calibrates the science frames in derived products only
- detects candidate stars in the field
- chooses a target and comparison ensemble automatically unless the user pins them
- scans multiple aperture radii and keeps the one with the lowest accepted-frame scatter
- exports a differential light curve, candidate diagnostics, QA, plots, and a markdown report

Useful overrides:

```bash
python3 scripts/exoplanet_timeseries_workbench.py /path/to/sequence_dir --object Qatar-9b --target-center 455 438 --comparison-label S1 --comparison-label S4 --output-dir out
python3 scripts/exoplanet_timeseries_workbench.py /path/to/sequence_dir --object WD1145 --aperture-radii 4 5 6 7 8 --output-dir out
```

Use this workflow when:

- the user wants an actual light curve, not just single-frame aperture photometry
- the sequence is dominated by repeated exposures of one field
- calibration compatibility, target selection, comparison-star choice, and QA all matter

## 2. 2D Spectroscopy Pipeline

Primary entrypoint:

```bash
python3 scripts/spectroscopy_pipeline_workbench.py science_2d.fits --calibration-table lines.ecsv --output-dir out
```

What it does:

- optionally runs CCD calibration with `reduce_ccd_batch.py`
- pushes the resulting science frame(s) into `spectral_workbench.py`
- traces and extracts a 1D spectrum from 2D input
- applies a wavelength calibration when a pixel-to-wavelength table is available
- exports plots, extracted tables, per-frame summaries, and an aggregate markdown report

Useful overrides:

```bash
python3 scripts/spectroscopy_pipeline_workbench.py science_2d.fits --bias b1.fits --bias b2.fits --flat f1.fits --flat f2.fits --calibration-table lines.ecsv --optimal-extraction --order-count 2 --output-dir out
python3 scripts/spectroscopy_pipeline_workbench.py science_2d.fits --calibration-table lines.ecsv --line-window 6563 40 --normalize --output-dir out
```

Use this workflow when:

- the user wants an honest end-to-end native pipeline around 2D spectra
- the task should produce extracted spectra plus calibration metadata and a report
- TEAREDUCE is not explicitly required

## Routing Rule

- Prefer `exoplanet_timeseries_workbench.py` for repeated imaging of the same field over time.
- Prefer `spectroscopy_pipeline_workbench.py` for 2D slit spectra that need trace extraction and optional calibration.
- Prefer `teareduce_router.py` plus the TEAREDUCE backend when the user explicitly wants the TEAREDUCE teaching or cookbook path.

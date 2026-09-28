# Spectra and Pipelines

## Use This Reference For

- 1D spectra in FITS or ASCII-like files
- line measurements, continuum estimation, and quick spectral diagnostics
- 2D spectral images that need traced extraction, local background handling, or a simple wavelength calibration
- multi-order or echelle-like layouts where the user needs a code-first approximation before a heavier pipeline
- TEAREDUCE-aligned spectral notebooks, wavelength-calibration walkthroughs, or cosmic-ray practice workflows
- reusable scientific project layouts and pipeline scaffolds
- workflows that should stay reproducible across astronomy and other scientific domains

## Important Scope Boundary

If the task explicitly asks for `IRAF`, `fxcor`, `MULTISPE`, SB2 coursework, `v sin i` from the CCF, or `iSTARMOD`, prefer the narrow legacy route first:

- `references/legacy-spectroscopy-coursework-macos.md`

Do not route those cases into TEAREDUCE by default.

## Spectrum Workflow

1. Identify the axis.
Prefer a real wavelength, frequency, or energy axis. If the file lacks one, derive it from FITS header keywords only when the metadata is trustworthy.

If the source is a 2D spectral image, recover a 1D trace first with a declared extraction window and a local background estimate instead of treating the image as if it were already calibrated 1D data.

2. Inspect before fitting.
Plot the raw spectrum, note gaps or masks, and check whether the spectrum should be normalized or continuum-subtracted.

3. Keep the continuum explicit.
If you estimate a continuum, save or plot it so the user can see what was assumed.

4. Fit only in a declared window.
Do not fit a line over the whole spectrum when only a local window is relevant.

5. Report caveats.
Mention unresolved blends, uncertain continuum placement, low SNR, clipping, or missing uncertainty arrays.

6. Keep calibration and provenance visible.
If you fit a wavelength solution or derive uncertainties, save the calibration inputs, residual hints, and an output manifest alongside the extracted spectrum.

## Helper Commands

Inspect or fit a 1D spectrum:

```bash
python3 scripts/datanalysis_env.py run-tool spectral_workbench spectrum.fits --plot quicklook.png
python3 scripts/datanalysis_env.py run-tool spectral_workbench spectrum.txt --line-window 6563 40 --normalize --output-table halpha.ecsv --plot halpha.png
python3 scripts/datanalysis_env.py run-tool spectral_workbench spectrum_2d.fits --line-window 6563 40 --normalize --trace-plot trace.png --plot extracted.png
python3 scripts/datanalysis_env.py run-tool spectral_workbench spectrum_2d.fits --line-window 6563 40 --normalize --optimal-extraction --order-count 2 --calibration-table lines.ecsv --trace-plot trace.png --html-report spectrum.html --manifest-json manifest.json
python3 scripts/datanalysis_env.py run-tool spectral_workbench spectrum_2d.fits --line-window 6563 40 --normalize --optimal-extraction --order-count 4 --extract-all-orders-dir orders --calibration-table lines.ecsv --summary-json spectrum.json
```

Route a TEAREDUCE-specific request before committing to that backend:

```bash
python3 scripts/teareduce_router.py --intent "calibracion de longitud de onda de un espectro 2D" P3_05_calibracion_longitud_de_onda.ipynb
python3 scripts/teareduce_healthcheck.py /path/to/PRACTICA\ 2 /path/to/PRACTICA\ 3 --summary-json teareduce_healthcheck.json
python3 scripts/teareduce_bridge.py imshow-fits spectrum_2d.fits --output teareduce_quicklook.png --summary-json teareduce_quicklook.json
```

Create a reproducible project scaffold:

```bash
python3 scripts/pipeline_scaffold.py /tmp/my-pipeline --domain astronomy --language bilingual --profile spectroscopy
```

## General Pipeline Principles

- Keep raw, intermediate, reduced, and report-ready outputs in separate folders.
- Prefer small configuration files plus scripts over giant notebooks with hidden state.
- Record assumptions in code or manifest files rather than only in chat.
- If the pipeline has a dominant data shape, encode that early with a profile such as `imaging`, `spectroscopy`, `time-series`, `catalog`, or `documents`.
- When uncertainties exist, propagate them explicitly through extraction, calibration, and exported tables instead of silently dropping them.
- For echelle-like or multi-order data, export per-order tables and summaries even if the workflow is still exploratory; that keeps the path open for later instrument-specific refinement.
- If the user explicitly wants TEAREDUCE or a TEAREDUCE teaching workflow, let TEAREDUCE stay the domain-specific backend and keep this skill focused on routing, validation, reporting, and reproducibility around it.
- Reuse the same layout across domains when possible:
  - `data/raw`
  - `data/interim`
  - `data/reduced`
  - `notebooks`
  - `scripts`
  - `reports/figures`
  - `config`

## Safe Defaults

- Use ASCII-friendly filenames for generated outputs.
- Avoid unsafe auto-deserialization of pickle-like formats.
- Treat missing dependencies as a recoverable state and report them clearly.

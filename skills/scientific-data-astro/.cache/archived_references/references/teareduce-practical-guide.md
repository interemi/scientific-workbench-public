# TEAREDUCE Practical Guide

Use this note when you want the shortest practical route to TEAREDUCE inside this skill.

This belongs to the `astronomy observational` block. It is meant to be the short TEAREDUCE entry, not the default front page for unrelated astronomy work.

## What TEAREDUCE Is Here

- An optional astronomy-specific backend.
- Best for notebook-faithful reduction, cookbook-style workflows, and classroom-aligned spectroscopy or calibration tasks.
- Not the default path for generic FITS inspection, tables, reports, LaTeX, or mixed document work.

## Quick Decision Rule

1. If the task is a real TEAREDUCE notebook from class and the dataset tree exists locally, run the notebook in copy.
2. If the task is `master bias`, use the canonical bias workflow.
3. If the task is `master flat`, use the canonical flat workflow with official sidecars.
4. If the task is `cr2images` or `wavecalib` and the local `TEA_procesado_INT` tree is missing, use the cookbook fallback notebooks.
5. If the task is small and exploratory, use `teareduce_bridge.py`.
6. If the task is not really TEAREDUCE-specific, prefer the native stack.

## Recommended Order

1. Run `teareduce_smoke_test.py` if you want one short health check over the four canonical routes.
2. Decide whether the notebook has the required local inputs.
3. Use one of the canonical workflows below instead of manually improvising the run.
4. Keep originals untouched and work only on copied outputs.

Quick smoke command:

```bash
python3 scripts/datanalysis_env.py run-tool teareduce_smoke_test --output-dir teareduce_smoke --summary-json teareduce_smoke/summary.json --manifest-json teareduce_smoke/manifest.json
```

## Canonical Paths

### 1. Bias

- Input: `P2_03_correccion_bias.ipynb`
- Best when: you want a fully local, real practice notebook that already runs cleanly.
- Output type: `N1_master_bias.fits`, corrected `zt_*.fits`, summary, report, manifest.

```bash
python3 scripts/datanalysis_env.py run-tool teareduce_master_bias_workflow /path/to/P2_03_correccion_bias.ipynb --output-dir teareduce_master_bias_case --summary-json teareduce_master_bias_case/summary.json --report-md teareduce_master_bias_case/report.md --manifest-json teareduce_master_bias_case/manifest.json
```

### 2. Flat

- Input: `P2_04_correccion_flat.ipynb`
- Best when: you want the real practice notebook and can stage official filter curves.
- Output type: `N1_master_flat_49.fits`, `N1_master_flat_76.fits`, `N1_master_flat_78.fits`, flat-corrected products, summary, report, manifest.

```bash
python3 scripts/datanalysis_env.py run-tool teareduce_flat_workflow /path/to/P2_04_correccion_flat.ipynb --output-dir teareduce_flat_case --fetch-official-sidecars --summary-json teareduce_flat_case/summary.json --report-md teareduce_flat_case/report.md --manifest-json teareduce_flat_case/manifest.json
```

### 3. Cosmic Rays Fallback

- Input: `cr2images.ipynb` from `PAQUETE DE COSAS` or the official cookbook.
- Best when: `PRÁCTICA 3` depends on missing `TEA_procesado_INT`, but you still want a real TEAREDUCE cosmic-ray case.
- Output type: `cftdz_*.fits`, `ccftdz_*.fits`, optional `cccftdz_*.fits`, summary, report, manifest.

```bash
python3 scripts/datanalysis_env.py run-tool teareduce_cookbook_cr2images_workflow --notebook /path/to/cr2images.ipynb --output-dir teareduce_cr2images_case --fetch-official-samples --summary-json teareduce_cr2images_case/summary.json --report-md teareduce_cr2images_case/report.md --manifest-json teareduce_cr2images_case/manifest.json
```

### 4. Wavelength Calibration Fallback

- Input: `wavecalib.ipynb` from `PAQUETE DE COSAS` or the official cookbook.
- Best when: `PRÁCTICA 3` depends on missing `TEA_procesado_INT`, but you still want a real TEAREDUCE wavecal case.
- Output type: `wavecal_ftdz_45324.fits`, `wftdz_45324.fits`, `wwftdz_45324.fits`, plots, summary, report, manifest.

```bash
python3 scripts/datanalysis_env.py run-tool teareduce_cookbook_wavecal_workflow --notebook /path/to/wavecalib.ipynb --output-dir teareduce_wavecal_case --fetch-official-samples --summary-json teareduce_wavecal_case/summary.json --report-md teareduce_wavecal_case/report.md --manifest-json teareduce_wavecal_case/manifest.json
```

## How To Read The Results

- `summary.json`: the structured result to inspect first.
- `report.md`: the human-readable explanation of what happened.
- `manifest.json`: provenance and reproducibility.
- copied notebook: proof that the original notebook ran successfully without modifying the source.

## Practical Interpretation

- If TEAREDUCE and the comparison path agree pixel by pixel, the difference is not the core reduction math but the notebook context and pedagogy.
- In `cr2images`, matching `cftdz_*` and `ccftdz_*` means the manual notebook path and the helper path are equivalent.
- In `wavecalib`, matching `wftdz_*` and `wwftdz_*` means the explicit notebook calibration path and `apply_wavecal_ccddata()` agree.
- Header unit formatting may differ while the calibrated array remains numerically identical.

## Common Failure Modes

- `missing_dataset`: the notebook expects a local processed tree such as `TEA_procesado_INT`.
- If that missing tree belongs to `P3_04` or `P3_05`, the preferred next step is not blind retrying: route to `PAQUETE DE COSAS/cr2images.ipynb` or `PAQUETE DE COSAS/wavecalib.ipynb`.
- `missing_sidecar_files`: the notebook expects extra text or auxiliary files that were not staged.
- `parameterized_template`: the notebook is a recipe that still needs user inputs.
- version skew: the notebook was written against an older TEAREDUCE release; surface that honestly but do not assume it is broken.

## Rule Of Thumb

- For class-faithful astronomy workflows, prefer TEAREDUCE.
- For generic automation, broad analysis, or cross-domain work, prefer the native stack.

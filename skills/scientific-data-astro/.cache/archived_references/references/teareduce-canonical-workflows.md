# TEAREDUCE Canonical Workflows

Use this note only after the practical route is already chosen.

- For the shortest route and the exact runnable commands, start with `references/teareduce-practical-guide.md`.
- Use this file when you want the deeper case-by-case meaning of the canonical TEAREDUCE paths, not when you just need to decide what to run.

## Fast Verification

If you want one short consolidated backend check before a real run:

```bash
python3 scripts/datanalysis_env.py run-tool teareduce_smoke_test --output-dir teareduce_smoke --summary-json teareduce_smoke/summary.json --manifest-json teareduce_smoke/manifest.json
```

That smoke test covers the same four canonical families summarized below.

## Canonical Cases At A Glance

### 1. Master Bias

- Notebook family: `P2_03_correccion_bias.ipynb`
- Best when: you want a faithful class notebook path that already runs locally
- Main outputs: `N1_master_bias.fits`, corrected `zt_*.fits`, summary, report, manifest
- Why it matters: this is the cleanest proof that TEAREDUCE is functioning as a real notebook backend rather than as a theoretical route

### 2. Flat Field

- Notebook family: `P2_04_correccion_flat.ipynb`
- Best when: you want the real notebook context and can stage the official filter sidecars
- Main outputs: `N1_master_flat_49.fits`, `N1_master_flat_76.fits`, `N1_master_flat_78.fits`, corrected products, summary, report, manifest
- Why it matters: this shows where TEAREDUCE adds notebook context and sidecar-aware teaching flow rather than unique reduction math

### 3. Cookbook `cr2images` Fallback

- Notebook family: official or local-copy `cr2images.ipynb`
- Best when: the original local spectroscopy tree is missing but you still need a real TEAREDUCE cosmic-ray example
- Main outputs: `cftdz_*.fits`, `ccftdz_*.fits`, optional `cccftdz_*.fits`, summary, report, manifest
- Why it matters: it keeps the backend honest when the original classroom tree is unavailable

### 4. Cookbook `wavecalib` Fallback

- Notebook family: official or local-copy `wavecalib.ipynb`
- Best when: the original local spectroscopy tree is missing but you still need a real TEAREDUCE wavelength-calibration example
- Main outputs: `wavecal_ftdz_45324.fits`, `wftdz_45324.fits`, `wwftdz_45324.fits`, plots, summary, report, manifest
- Why it matters: it exercises the same calibration family without depending on the missing local practice tree

## Interpretation Notes

### Master Bias

- Prefer TEAREDUCE when the notebook structure and stepwise classroom flow are part of the value.
- Prefer the native stack when the user mainly wants the calibration product and a simpler automation path.

### Flat Field

- Filter `76` should look broader and smoother than the narrow-band cases.
- Filters `49` and `78` should show stronger spatial structure because the narrow-band setup is more field-angle sensitive.
- If TEAREDUCE and the native path match closely, the real difference is workflow context, not reduction math.

### `cr2images`

- Matching `cftdz_*` and `ccftdz_*` means the notebook path and the helper path agree numerically.
- Use this route when you want a real TEAREDUCE cosmic-ray workflow without the original local tree.

### `wavecalib`

- Matching `wftdz_*` and `wwftdz_*` means the explicit notebook calibration and the helper application path agree.
- Minor header-unit differences do not matter if the calibrated wavelength axis is physically equivalent.

## Scope Rule

- These canonical cases are reference anchors, not the whole TEAREDUCE story.
- Use them to keep the backend grounded in real notebook workflows.
- Do not use this file as the first entrypoint; route first with `references/teareduce.md` or `references/teareduce-practical-guide.md`.

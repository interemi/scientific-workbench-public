---
name: scientific-data-astro
description: Use when the task is an astronomy/science workflow involving FITS, WCS, photometry, spectroscopy, radial velocity, external astro backends, or legacy coursework, especially when scientific-data-analysis delegates here.
---

# scientific-data-astro

This is the installed child skill for astronomy observational workflows. The broad entrypoint remains `scientific-data-analysis`; direct use is appropriate for expert astro work, optional backend preflights, and legacy spectroscopy/coursework routes.

v2.8 keeps the public astro script names stable and adds scientific-safety regressions for FITS metadata, astrometric stacking, MULTISPEC dispersion, photometry, and radial-velocity validation. App consumers must treat this child as its own skill root, resolve its compact `public_surface_registry.yaml` through `canonical_registry`, and keep optional/legacy astronomy routes expert-scoped or blocked cleanly when unavailable.

v2.5 keeps the public astro script names stable while storing heavy executable bodies in same-named `fixtures/` files. Dependency shims that forward to documents or notebooks remain shims.

## Routing

- Prefer the mother skill for broad or ambiguous requests.
- Use this child for FITS/WCS, RGB FITS, astrometry, photometry, spectra, RV, STILTS/APT/TEAREDUCE, and legacy IRAF/iSTARMOD/fxcor workflows.
- Optional or legacy backends must return `BLOCKED_CONTROLADO` when unavailable.
- Never modify original science files; operate on copies or explicit output directories.
- Treat `scripts/*.py` as stable thin entrypoints; inspect `fixtures/*.py` only when patching implementation details.

## Datanalysis Execution

Heavy FITS, photometry, and spectroscopy helpers require the dedicated `datanalysis` environment. Use the explicit runner from this skill root instead of assuming the shell's `python3` has Astropy, SciPy, or Matplotlib:

```bash
python3 scripts/datanalysis_env.py run-tool fits_rgb_batch --input-root <fits-tree> --output-dir <derived-output>
python3 scripts/datanalysis_env.py run-tool aperture_photometry <image.fits> --center <x> <y>
python3 scripts/datanalysis_env.py run-tool spectral_workbench <spectrum> --summary-json <summary.json>
```

Some stable entrypoints re-execute themselves inside `datanalysis`, but callers should use `run-tool` whenever the registry sets `requires_datanalysis: true`. A missing scientific runtime must remain a controlled dependency block, never a raw traceback.

## Key References

- `references/astronomy-fits.md`
- `references/photometry-detectors.md`
- `references/spectra-and-pipelines.md`
- `references/radial-velocity-systemic.md`
- `references/external-astronomy-tools.md`
- `references/legacy-spectroscopy-coursework-macos.md`
- `references/v2-3-mother-router-contract.md`
- Mother-level current hardening: `../scientific-data-analysis/references/v2-8-family-integrity-hardening.md`

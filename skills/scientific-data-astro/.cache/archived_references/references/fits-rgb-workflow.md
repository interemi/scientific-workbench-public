# FITS RGB Batch Workflow

Use this route when the task is to turn many astronomy FITS images into derived RGB or pseudo-RGB visual products for review, slides, posters, or coursework handoff.

This is not a full CCD reduction pipeline. Preserve raw FITS files, record whether calibration state is known, and treat the output as a visual product unless upstream bias/dark/flat/reduction evidence is explicit.

## First Pass

Start with inventory, not rendering:

```bash
python scripts/fits_rgb_batch.py \
  --input-root /path/to/fits_tree \
  --output-dir /path/to/rgb_products \
  --clean-derived \
  --summary-json /path/to/rgb_products/summary.json
```

The expected output layout is:

```text
rgb_products/
  fits_inventory.csv
  rgb_group_summary.csv
  run_summary.json
  manifest.json
  rgb_png/
  stacked_fits/
  aligned_stacked_fits/
  reports/
```

Use `--force` only when intentionally writing into an existing derived folder. Prefer `--clean-derived` for reruns so old reports do not mix with new ones.

## Grouping Rule

Group candidate frames by:

- object or target name;
- setup when it can be inferred from filename tokens such as `B2_T3`;
- image shape;
- filter/channel.

Do not group unrelated shapes or setups just because the object name matches. If a dataset has nonstandard naming, inspect `fits_inventory.csv` before trusting the groups.

## Channel Plan

Label outputs honestly:

- `true_rgb`: three broad visual bands such as `R/V/B`, `R/G/B`, or `I/V/B`.
- `ha_rgb`: H-alpha is used or blended into red; do not call this plain broadband RGB.
- `pseudo_bv`: only `B` and `V` exist, so one band is reused.
- `pseudo_ir`: red/IR-only channels such as `R/I` are reused.
- `single_channel`: one usable image is repeated in all channels.

If the user asks for "RGB of everything possible", pseudo-RGB can be useful, but the summary must make that limitation visible.

## Alignment Decision

For multiband RGB, align final filter stacks, not every exposure unless the data really requires it.

Use this order:

1. If source and reference stacks have valid celestial WCS and `reproject` is available, reproject channels to the reference WCS.
2. If WCS is absent or broken, use phase correlation or another simple translation fallback.
3. If no safe alignment is possible, still write the product only with a warning and inspect visually before using it.

The critical rule is: WCS-bearing images with rotations, scale differences, or offsets should not rely on a plain pixel shift when reprojection is available.

## QA Minimum

Every group should leave:

- alignment method per filter;
- shift or reprojection footprint when available;
- common output/crop behavior;
- simple residual or warning for visible color seams;
- PNG for human review;
- JSON report for reproducibility.

If the user reports "offsets", "junta de colores", or separated RGB triplets:

1. Check whether WCS was present but not used.
2. Check `reports/*alignment_qa.json`.
3. Re-run with `--alignment-mode wcs` if WCS is valid.
4. If WCS is unavailable, re-run with `--alignment-mode phase` and inspect residuals.
5. Do not rerun the whole reduction blindly before diagnosing alignment method and reference channel.

## Single-Object RGB Redo From Raw FITS

Use this narrower route when a batch RGB product is mostly successful but one object is visibly bad: chromatic speckles, separated color points, poor visual background, or a channel mismatch that matters for a slide/poster.

Do not turn this into a general CCD reduction. The job is to rebuild one visual RGB product from traceable raw or reduced FITS inputs and document exactly what changed.

Recommended steps:

1. Locate the source frames by object, setup, shape, and filter. Keep the old RGB file as evidence before overwriting anything.
2. Inventory the candidate FITS files: filter, exposure time, image shape, WCS presence, background level, saturated pixels, and obvious cosmic rays or hot pixels.
3. Choose a reference channel with good SNR and usable WCS. Prefer WCS reprojection between filters when celestial WCS is valid.
4. Clean each exposure only as far as needed for a visual product:
   - remove cosmic rays and hot pixels when they dominate the display;
   - estimate sky/background per exposure if no trustworthy calibration products are present;
   - do not claim master-bias, dark, or flat correction unless those calibration frames were actually used.
5. Align channels to the reference WCS with `reproject` when possible. If WCS is absent, use a documented translation fallback and inspect residual color offsets.
6. Stack per filter, then render with common luminance and restrained chrominance. If color is unreliable, lower saturation rather than inventing physical color.
7. Write a manifest next to the output: input FITS, cleaning choices, alignment method, rendering parameters, old file compared, and visual-only calibration warning.

If the user asks to "fix the RGB" or "remove colored speckles", this route is allowed only for visual delivery products. For photometry, color measurements, calibrated fluxes, or quantitative morphology, return to the calibrated reduction path instead.

## Aggressive Visual Cleanup Boundary

Aggressive cleanup is acceptable when all of these are true:

- the output is explicitly for display, slides, posters, visual inspection, or handoff;
- the source frames and old output are preserved;
- the manifest states that the product is not flux calibrated;
- the cleaning mostly removes artifacts such as cosmic rays, hot pixels, chromatic speckles, or isolated color seams;
- the scientific message does not depend on the cleaned pixels.

Useful display-only techniques include cosmic-ray masking, hot-pixel clipping, chroma smoothing, luminance-first rendering, low-saturation color, and small connected-component cleanup of chromatic speckles. Do not use those choices silently. They must appear in the manifest or report.

## Before/After Comparison

When replacing a bad RGB product:

- keep a backup or copied path for the previous PNG;
- generate a side-by-side comparison with clear labels such as `previous` and `new visual RGB`;
- record the previous file path and hash in the manifest;
- record the reason for the redo, for example `chromatic speckles`, `WCS offset`, or `visual background cleanup`;
- keep diagnostics and temporary previews separate from final slide assets.

The comparison is an acceptance artifact, not a scientific measurement. It should make it easy to see whether the visible defect was fixed without hiding that the new file is a display product.

## Visual RGB FITS Export

If the final visual RGB also needs a FITS container, use a display-only convention rather than pretending the RGB image is calibrated flux.

Recommended structure:

- `PRIMARY`: metadata only, with `IMAGETYP=VISUAL_RGB`, `CALIB=DISPLAY_ONLY`, and a comment stating that the file is not flux calibrated.
- `RGB_CUBE`: float32 array with shape `(3, y, x)` in red, green, blue order.
- `RED`, `GREEN`, `BLUE`: float32 2D channel extensions.
- `BUNIT=normalized_display_intensity` on the RGB extensions.

Use `scripts/rgb_visual_fits_export.py` when starting from an already-rendered RGB PNG and needing a reproducible FITS visual product plus optional before/after comparison:

```bash
python scripts/rgb_visual_fits_export.py \
  final_rgb.png \
  final_rgb_visual.fits \
  --previous-png previous_rgb.png \
  --comparison-png before_after.png \
  --manifest-json final_rgb_visual_manifest.json \
  --summary-json final_rgb_visual_summary.json \
  --object-name "NGC 1277" \
  --reason "single-object visual RGB redo after chromatic speckle cleanup"
```

## Notebook Recipe Extraction

When a coursework notebook defines the intended RGB style, inspect the notebook source before inventing a new rendering:

- look for `make_lupton_rgb`, `make_rgb`, `simple_norm`, `ManualInterval`, percentiles, asinh stretches, and H-alpha blending;
- extract channel order, stretch, crop, origin, and overlay rules;
- reproduce the figure in a small script or scratch notebook;
- write a manifest next to the generated product.

This complements `references/coursework-figure-equivalents.md`; use that route when the output must match a slide or notebook figure exactly.

## What Not To Do

- Do not import a one-off project script with hardcoded user paths into the skill.
- Do not treat pseudo-RGB as physically calibrated color.
- Do not claim CCD calibration was verified unless bias/dark/flat/reduction evidence was checked.
- Do not present a visual RGB FITS cube as calibrated science data.
- Do not build a huge filter-specific astronomy renderer until repeated real cases justify it.

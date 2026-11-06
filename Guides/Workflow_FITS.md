# Inspect a FITS image

**Purpose:** inventory HDUs, headers, dimensions, finite pixels, and available
previews. A WCS header or successful run is not calibration.

1. On Dashboard, choose **Open task** for your FITS or **Try example** for a new
   synthetic image. No command runs just by opening or preparing the task.
2. Review `inspect_fits` under **Expert**, confirm the access notice, and inspect
   input/output paths. Use Core with Astropy/NumPy; no model, API key, STILTS, or
   APT is needed for this example.
3. Expect **8 × 8 pixels**, **63 finite pixels**, TAN WCS reference **RA 150° /
   Dec −30°**, one arcsecond per pixel, and an `adu` header unit. Select **Run
   Capability** after review. A Chat plan needs step, scope, permissions, and
   **Dry Run** review before **Run Enabled**.
4. In **Run & Logs**, inspect status, command, errors, and retained evidence.
   Cancel there if needed; keep partial files and logs before another attempt.
5. In **Results**, inspect `summary.json`, `manifest.json`, and any preview.
   Compare counts, coordinates, units, warnings, and input hashes with the
   example's `expected.json`. Automatic checks do not replace scientific review.
   A Chat **Summary** links the Workflow Run ID to steps and jobs; a direct
   capability job has its own Job ID and tool summary.

The guided WCS PNG is restricted to the byte-matched app-generated fixture.
Other inputs retain the metadata-focused guided default; this is not a general
large-image viewer. The PNG uses a display stretch, not a calibrated measurement.
For real data, review frames, projections, epoch, units, masks, and uncertainty.

## CLI equivalent

From the checkout, select the existing Core Python and the generated FITS shown
in the app. This recipe explicitly requests a preview for that small fixture:

```sh
SCIWB_PYTHON="/absolute/path/to/datanalysis/bin/python"
SCIWB_INPUT="/absolute/path/to/the/generated/input/synthetic_wcs_8x8.fits"
SCIWB_RUN="$(mktemp -d /tmp/scientific-workbench-fits.XXXXXX)"
"$SCIWB_PYTHON" skills/scientific-data-astro/scripts/inspect_fits.py \
  "$SCIWB_INPUT" --summary-json "$SCIWB_RUN/summary.json" \
  --manifest-json "$SCIWB_RUN/manifest.json" \
  --preview "$SCIWB_RUN/synthetic_wcs.png" \
  --header-key CUNIT1 --header-key CUNIT2 --header-key RADESYS \
  --header-key CDELT1 --header-key CDELT2
```

Keep the original and compare its hash before and after. See the
[user guide](Scientific_Workbench_User_Guide.md) for setup and recovery.

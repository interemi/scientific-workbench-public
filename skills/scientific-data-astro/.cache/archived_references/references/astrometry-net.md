# Astrometry.net Solve Paths

This belongs to the `astronomy observational` block.

## Use This When

- the user explicitly wants `Astrometry.net` or `nova.astrometry.net`
- a notebook or workflow includes a manual astrometry.net browser step
- a FITS or image file needs an external plate solve and a WCS-bearing output
- you want a non-destructive path that uploads a copy, polls the web solve, and downloads products cleanly
- you have a local `solve-field` installation and want the official local backend as an optional path

## Operational Summary

- `preflight`: inspect the file first and collect scale/center/WCS hints.
- `verify-existing-wcs`: use this when a FITS already carries celestial WCS. It now distinguishes a normal image-backed WCS from a header-only celestial WCS and reports that case cleanly instead of crashing.
- `solve-web-best-effort`: use this when the practical route is still the web service.
- `solve-local-best-effort`: use this as the operational local path once `solve-field` and indexes exist.
- plain `solve-local`: keep this mainly as a stricter diagnostic, especially for compact TOI-like fields.

## Main Entry Point

Use:

```bash
python3 scripts/astrometry_net_workbench.py preflight image.fits --summary-json astrometry_preflight.json
```

This workbench now tries to re-execute itself inside `datanalysis` automatically when it is launched from the wrong interpreter, so a direct call is less fragile than it used to be.

This inspects the local file and tries to infer:

- image size
- approximate center from FITS headers like `RA`/`DEC`, `OBJRA`/`OBJDEC`, `TELRA`/`TELDEC`, or WCS `CRVAL`
- approximate pixel scale from `PIXSCALE`, `SECPIX`, or a pre-existing WCS
- a sensible first set of Astrometry.net hints

It now also estimates field extent when a scale can be inferred, and it emits:

- `suggested_solve_hints` for the web API
- `suggested_local_solve_args` for the official local `solve-field` CLI
- `existing_astrometric_solution` when the FITS already carries a celestial WCS
- `fit_assessment` to distinguish direct imaging, compact fields that benefit from stacking, spectroscopy-like inputs, and already-calibrated images
- `image_quality_proxy` so compact-field retries can be ranked a bit more intelligently
- `instrument_scale_hint` when the FITS matches a known direct-imaging setup such as `CAFOS 2.2`

It now also emits a dependency preflight block so you can see, before solving, whether the route depends on:

- missing Python modules
- missing local binaries such as `solve-field`
- remote services or network access
- optional backends that are not available on the current machine

That preflight is meant to be operational rather than theoretical: it tells you whether you are in an `ok`, `warning`, or `blocked` state before you commit to a solve path.

## Cautious Best-Effort Path

When the classroom workflow is messy or the file type is not obvious, prefer:

```bash
python3 scripts/astrometry_net_workbench.py solve-web-best-effort image.fits \
  --output-dir astrometry_best_effort \
  --summary-json astrometry_best_effort/summary.json \
  --report-md astrometry_best_effort/report.md
```

This mode is intentionally conservative:

- it skips spectroscopy-like or calibration-like inputs instead of blindly uploading them
- it skips images that already expose a celestial WCS and now creates a small verification bundle instead of treating them as a dead end
- for compact direct-imaging fields it can try multiple peer-stack windows before falling back to a direct web solve
- for some known imaging setups, it can inject a cautious instrument-based scale hint when no better scale estimate is present
- it leaves an attempts log so you can see what was tried and why

Downloaded solves now try to leave a visual quicklook too:

- for web solves, the workbench prefers the original input image plus the downloaded `wcs.fits` header so it can still render a QA PNG even when `new_fits_file` is not directly reusable
- for existing-WCS cases, the verification bundle includes an `existing_wcs_quicklook.png`

When a FITS only carries a celestial WCS in headers but does not expose usable image data, `verify-existing-wcs` now returns a controlled `wcs_header_only` result. That is treated as a warning-level verification outcome, not as a traceback.

If a compact field needs extra help, provide a fallback scale:

```bash
python3 scripts/astrometry_net_workbench.py solve-web-best-effort image.fits \
  --output-dir astrometry_best_effort \
  --peer-count 13 \
  --same-object \
  --same-exptime \
  --fallback-scale-est 0.524 \
  --fallback-scale-err 20
```

On `CAFOS 2.2` direct-imaging files, the skill now knows a cautious default imaging scale heuristic of about `0.525 arcsec/pixel`; you can still override it explicitly whenever you know the scale better than the tool does.

To build and inspect a stack explicitly:

```bash
python3 scripts/astrometry_net_workbench.py stack-peers image.fits \
  --output-path derived_stack.fits \
  --peer-count 13 \
  --same-object \
  --same-exptime \
  --peer-strategy forward_window
```

## Solve Through The Web API

Astrometry.net web solving needs an API key. Prefer:

```bash
python3 scripts/astrometry_net_workbench.py auth-check \
  --summary-json astrometry_auth.json \
  --report-md astrometry_auth.md
```

The skill now resolves credentials in this order:

- `--api-key`
- `ASTROMETRY_NET_API_KEY`
- `ASTROMETRY_NET_API_KEY_FILE`
- a private key file at `~/.codex/secrets/astrometry_net_api_key`

That private-file route is the recommended local setup because it keeps the API key out of the publishable skill files and out of normal command history. If you still prefer an environment variable, this also works:

```bash
export ASTROMETRY_NET_API_KEY="your-key"
python3 scripts/astrometry_net_workbench.py solve-web image.fits \
  --output-dir astrometry_solve \
  --summary-json astrometry_solve/summary.json \
  --report-md astrometry_solve/report.md \
  --manifest-json astrometry_solve/manifest.json
```

The workbench:

- uploads the local file without touching the original
- logs in to `nova.astrometry.net`
- submits a file solve with optional scale and sky-position hints
- polls the submission and job status
- downloads useful products like:
  - `new_fits`
  - `wcs`
  - `annotations`
  - `calibration`
  - `info`
  - optional display products such as `annotated_display`

Downloaded FITS-like products are now validated defensively:

- if `wcs.fits` or `new_fits.fits` is clearly invalid, that gets recorded in `download_validation.json`
- if `new_fits.fits` is really an HTML or otherwise broken payload but `wcs.fits` is valid, the workbench reconstructs a usable astrometrized FITS from the original input plus the downloaded WCS header when possible
- the original bad payload is still preserved separately so the recovery remains auditable

## Submit A Remote URL Instead Of A Local File

The official Astrometry.net client also supports `url_upload`. The skill now exposes that directly:

```bash
python3 scripts/astrometry_net_workbench.py solve-web-url "https://example.org/image.fits" \
  --output-dir astrometry_url_solve \
  --summary-json astrometry_url_solve/summary.json
```

This is useful when the image already lives on a stable public URL and you do not want to copy or upload a local file yourself.

## Optional Local `solve-field` Backend

The upstream project is much bigger than the web API: the real local workhorse is `solve-field`. The skill now exposes it as an optional path when that binary is available on the machine:

```bash
python3 scripts/astrometry_net_workbench.py solve-local image.fits \
  --output-dir astrometry_local_solve \
  --index-dir "/path/to/index/files" \
  --cpulimit-sec 60 \
  --wall-timeout-sec 90 \
  --summary-json astrometry_local_solve/summary.json \
  --report-md astrometry_local_solve/report.md
```

This local path now collects the standard Astrometry.net products when they exist, including outputs such as:

- `.wcs`
- `.new`
- `.rdls`
- `.axy`
- `.corr`
- `.match`
- `.solved`

and the common diagnostic plots if `solve-field` creates them.

For local desktop installations, the most useful new knobs are:

- `--index-dir`: point `solve-field` at a custom directory of downloaded Astrometry.net index FITS
- `--index-file`: explicitly provide one or more index files
- `--cpulimit-sec`: pass a solver-side CPU limit to `solve-field`
- `--wall-timeout-sec`: cap the whole subprocess wall time so classroom tests do not hang indefinitely

For a cautious local orchestration that behaves more like the web best-effort path, use:

```bash
python3 scripts/astrometry_net_workbench.py solve-local-best-effort image.fits \
  --output-dir astrometry_local_best_effort \
  --backend-config astrometry_local.cfg \
  --summary-json astrometry_local_best_effort/summary.json
```

This mode now:

- skips spectroscopy-like inputs instead of forcing a blind solve
- verifies existing WCS-bearing FITS instead of re-solving them
- tries a standard direct local solve first
- for compact direct-imaging fields, retries the original single frame once with a more aggressive local source-extraction threshold before giving up on single-frame solving
- only then falls back to peer stacking if the compact-field single-frame attempts still did not succeed
- leaves a light visual-review quicklook for compact-field recoveries so you can sanity-check the rescued geometry quickly

For TOI-like compact sequences, treat `solve-local-best-effort` as the operational path and plain `solve-local` as a stricter diagnostic. The direct path is still useful, but mainly to answer "would the conservative single-frame solve have worked on its own?"

Both local solve paths now also inspect the supplied local index directory when they can infer it from `--index-dir` or `--backend-config`:

- if suspiciously tiny FITS tiles are present, the warning is written into the local `summary.json` and report
- if the directory looks clean, that also gets recorded explicitly so you can tell the difference between an index problem and an honest field-difficulty problem

For a short backend regression check on a real machine, use:

```bash
python3 scripts/astrometry_local_smoke_test.py \
  --output-dir astrometry_local_smoke \
  --backend-config astrometry_local.cfg \
  --direct-fits direct_image.fits \
  --compact-fits compact_field.fits \
  --existing-wcs-fits existing_wcs_image.fits \
  --spectroscopy-fits spectroscopy_like.fits \
  --summary-json astrometry_local_smoke/summary.json
```

That smoke test is intentionally small: it checks one ordinary direct-imaging solve, one compact-field recovery case, one existing-WCS verification case, and one spectroscopy-like skip case.

Its per-case statuses now separate:

- `pass`: the intended path worked
- `expected_skip`: the tool correctly declined a case such as spectroscopy-like input or header-only WCS
- `invalid_fixture`: the supplied file was not even a valid FITS test input
- `tool_failure`: the fixture was valid but the tool path itself failed

That makes it much easier to tell whether a red smoke came from a bad fixture or from an actual regression in the astrometry tooling.

To inspect the local index directory itself before blaming the solver, use:

```bash
python3 scripts/astrometry_index_healthcheck.py "/path/to/index/files" \
  --summary-json astrometry_index_health.json
```

This helper is intentionally simple: it counts series coverage, totals the directory size, and flags suspiciously tiny FITS files that often indicate failed or partial downloads.

It is worth rerunning this check after any future index download, re-download, or directory reorganization. That keeps index hygiene separate from honest field-difficulty failures.

Those options matter a lot on machines where:

- the package manager installed `solve-field` but not a populated default index directory
- you keep the downloaded index FITS in a custom folder such as `~/Desktop/ASTROMETRY/INDEX FILES`
- you want fast diagnostics of whether the current local index coverage is actually enough for your field of view
- you want to check whether the local index directory itself still contains suspiciously tiny or incomplete-looking FITS tiles

This is the most useful thing to borrow from the upstream repository if you later decide to install Astrometry.net locally with indexes.

## Practical Hints

- Supplying approximate scale and sky position usually improves solve speed and robustness.
- If the FITS header already contains plausible `RA`/`DEC`, the preflight step can often provide a good first guess.
- If preflight says the file already has a celestial WCS, reuse or verify that solution before asking for a new blind solve.
- If preflight says the file looks like spectroscopy or an arc/calibration frame, do not force the web solve unless you have a very specific reason.
- For small time-series imaging fields, peer stacking can matter more than adding extra blind-solve retries.
- For Calar Alto `CAFOS 2.2` imaging, a cautious `~0.525 arcsec/pixel` hint is often useful when the header does not expose a plate scale.
- Use `--scale-est` or `--scale-lower/--scale-upper` when you know the approximate plate scale.
- Use `--center-ra`, `--center-dec`, and `--radius-deg` when the field location is roughly known.
- The upstream documentation repeatedly emphasizes that good scale bounds can speed up solving a lot.
- Astrometry.net is deliberately designed to prefer “no answer” over a false positive solve.

## Relationship To The TEAREDUCE Notebooks

- `10a_astrometry_net.ipynb` is best treated as a guided classroom recipe with a manual/browser flavour.
- if the same notebook later appears as `.ipynb.txt` after an export/download hiccup, keep routing it the same way
- The actual solve now belongs in `scripts/astrometry_net_workbench.py`, whether you use the web API or an optional local `solve-field`.
- After solving, feed the downloaded `new_fits` or `wcs` product back into the rest of the skill for WCS-aware inspection, photometry, or reporting.

## Limits

- This path depends on internet access and a valid Astrometry.net API key.
- The web path is not a replacement for a full local Astrometry.net installation with `solve-field` plus index files.
- Some classroom workflows still include manual visual matching around the web solve; keep those as guided steps rather than forcing everything into automation.

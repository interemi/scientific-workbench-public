# External Astronomy Tools

Use this reference when the task explicitly benefits from installed astronomy desktop/software backends such as TOPCAT/STILTS or Aperture Photometry Tool (APT). These tools are optional companions to the skill. They do not replace the Python-native routes.

## Decision Rule

- Use `scripts/catalog_workbench.py` for compact Python crossmatches, joins, and small/medium tables where Astropy is enough.
- Use `scripts/stilts_workbench.py` when STILTS/TOPCAT is installed and the work needs reproducible catalog conversion, VOTable validation, large-table filtering, or command lines suitable for a report.
- Use `scripts/aperture_photometry.py` or photutils when aperture photometry should be fully Python-native and portable.
- Use `scripts/apt_workbench.py` only when the user explicitly wants APT compatibility, APT-generated tables, or a comparison against a GUI-configured APT workflow.

Do not automate the TOPCAT GUI or the APT GUI. Use GUI work only to configure, inspect, or confirm choices, then capture the reproducible command or saved preferences used by the batch wrapper.

## Preflight

Start with the shared external-tool preflight:

```bash
python scripts/external_astro_tools_preflight.py \
  --summary-json external_astro_preflight.json
```

For a strict STILTS or APT route:

```bash
python scripts/external_astro_tools_preflight.py \
  --require-stilts \
  --summary-json stilts_preflight.json

python scripts/external_astro_tools_preflight.py \
  --require-apt \
  --apt-preferences /path/to/APT.pref \
  --summary-json apt_preflight.json
```

If STILTS or APT is absent, the correct result is `blocked`, not a Python traceback and not a fake success.

## Local Installation And Validation Protocol

Keep these backends optional. A normal `scientific-data-analysis` installation is still valid when Java, STILTS, TOPCAT, APT, or `APT.pref` are absent.

Use this protocol only on a machine that explicitly wants real external astronomy backends:

1. Install or expose Java.
   - Use the system/package-manager Java if it already exists.
   - If PATH discovery is not enough, pass `--java-command /path/to/java`.
2. Install or expose STILTS/TOPCAT.
   - Prefer a direct `stilts` command for reproducible CLI work.
   - If the command is not on PATH, pass `--stilts-command /path/to/stilts` or `--stilts-jar /path/to/stilts.jar`.
   - TOPCAT may remain a GUI inspection tool; use `--topcat-command` or `--topcat-jar` only when it exposes STILTS mode.
3. Install or expose APT only when the task specifically needs APT compatibility.
   - Run APT manually once.
   - Configure aperture radius, annulus, coordinate interpretation, background mode, and output-table settings.
   - Save preferences and record the preferences path, normally `~/.AperturePhotometryTool/APT.pref`.
   - Pass `--apt-command /path/to/APT.csh` or equivalent if PATH discovery is not enough.
4. Run preflight first, then a local validation fixture.

The maintainer validation command is:

```bash
python scripts/external_astro_tools_local_validation.py \
  --output-dir external_astro_local_validation \
  --summary-json external_astro_local_validation.json
```

For a strict STILTS machine:

```bash
python scripts/external_astro_tools_local_validation.py \
  --tool stilts \
  --require-stilts \
  --stilts-command /path/to/stilts \
  --summary-json stilts_local_validation.json
```

For an APT machine, start with dry-run validation. This confirms command discovery, source-list preparation, saved preferences, and manifest/log routing without launching a full photometry run:

```bash
python scripts/external_astro_tools_local_validation.py \
  --tool apt \
  --require-apt \
  --apt-command /path/to/APT.csh \
  --apt-preferences /path/to/APT.pref \
  --summary-json apt_local_validation.json
```

Only run a real APT batch fixture when the saved preferences are intentionally ready for a synthetic image/source-list test:

```bash
python scripts/external_astro_tools_local_validation.py \
  --tool apt \
  --require-apt \
  --include-apt-batch \
  --apt-command /path/to/APT.csh \
  --apt-preferences /path/to/APT.pref \
  --summary-json apt_real_batch_validation.json
```

Expected interpretation:

- `ok`: the requested backend path completed the tiny validation fixture.
- `warning`: one or more optional backends are absent, but they were not required.
- `blocked`: a requested required backend is absent or not configured.
- `fail`: the backend was detected but the validation fixture did not complete cleanly.

Do not promote STILTS/APT to core dependencies just because local validation passes on one machine. Treat the validation output as machine-local evidence and keep it with the report or maintenance log.

## STILTS / TOPCAT

Prefer STILTS over TOPCAT GUI for reproducible catalog workflows. TOPCAT is excellent for interactive inspection; STILTS is the command-line backend to cite and rerun.

Useful wrapper commands:

```bash
python scripts/stilts_workbench.py preflight \
  --summary-json stilts_ready.json

python scripts/stilts_workbench.py convert catalog.csv catalog.vot \
  --ofmt votable \
  --summary-json convert.json \
  --manifest-json convert_manifest.json \
  --log-dir stilts_logs

python scripts/stilts_workbench.py filter catalog.vot bright_sources.csv \
  --ifmt votable \
  --ofmt csv \
  --cmd 'select "mag < 17 && quality == 0"' \
  --cmd 'keepcols "source_id ra dec mag"' \
  --summary-json filter.json

python scripts/stilts_workbench.py crossmatch-sky gaia.csv local.csv matched.csv \
  --left-ra ra --left-dec dec \
  --right-ra ra --right-dec dec \
  --radius-arcsec 1.0 \
  --ofmt csv \
  --summary-json match.json \
  --manifest-json match_manifest.json

python scripts/stilts_workbench.py votlint table.vot votlint_report.txt \
  --summary-json votlint.json
```

Manifest expectations:

- input tables and output tables
- exact STILTS command
- explicit RA/Dec columns and match radius
- formats used
- stdout/stderr logs when useful
- whether the command was a dry run

Avoid relying on automatic coordinate inference for final scientific reporting. It may be convenient during exploration, but reports should name the RA/Dec columns and units explicitly.

## APT Batch Mode

APT batch mode is only reproducible after APT has been configured manually and the preferences have been saved. The important file is usually:

```text
~/.AperturePhotometryTool/APT.pref
```

Before batch work:

1. Open APT manually once.
2. Configure aperture radius, annulus, source-list coordinate type, background mode, output table settings, and any calibration choices.
3. Save preferences.
4. Use a copied FITS image or a derived work directory when testing.
5. Record the preferences file path in the manifest.

Typical commands:

```bash
python scripts/apt_workbench.py preflight \
  --apt-preferences /path/to/APT.pref \
  --summary-json apt_ready.json

python scripts/apt_workbench.py prepare-source-list sources.csv sources.lst \
  --x-col x --y-col y --id-col id \
  --summary-json source_list.json \
  --manifest-json source_list_manifest.json

python scripts/apt_workbench.py run-batch \
  --apt-command /path/to/APT.csh \
  --apt-preferences /path/to/APT.pref \
  --image image.fits \
  --source-list sources.lst \
  --output-table APT.tbl \
  --zero-point 25.0 \
  --summary-json apt_run.json \
  --manifest-json apt_run_manifest.json \
  --log-dir apt_logs

python scripts/apt_workbench.py parse-results APT.tbl apt_results.csv \
  --summary-json apt_parse.json
```

Interpret APT results carefully:

- APT source-list meaning is preference-driven: pixel coordinates and sky coordinates are not interchangeable.
- Batch output is only as reliable as the saved aperture/background settings.
- Large images or long source lists can be slow and Java-memory dependent.
- For publication-like reproducibility, compare critical outputs against a Python/photutils route when feasible.

## What Not To Add

- Do not turn TOPCAT GUI sessions into hidden automation.
- Do not treat APT preferences as invisible state; cite or archive `APT.pref`.
- Do not replace existing Python-native crossmatch and photometry tools when the Python route already answers the task.
- Do not make Java, STILTS, TOPCAT, or APT required core dependencies.
- Do not overwrite raw FITS or source catalogs. External-tool runs should write derived outputs, logs, summaries, and manifests into a separate folder.

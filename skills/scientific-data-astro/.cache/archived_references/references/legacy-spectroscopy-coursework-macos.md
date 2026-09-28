# Legacy Spectroscopy Coursework On macOS

This belongs to the `astronomy observational` block. It is a narrow route for coursework that already arrives with reduced echelle `MULTISPE` FITS, expects `IRAF/fxcor`, uses a `FWHM`--`v sin i` calibration, and may require `iSTARMOD`.

## Use This Route For

- macOS practicals that explicitly mention `IRAF`, `fxcor`, `mkiraf`, `xgterm`, or XQuartz
- echelle legacy FITS with `CTYPE=MULTISPE` and `WAT*` headers
- SB2 coursework where the CCF may need one pass per component
- first-pass `v sin i` from CCF width and an external calibration table
- spectral subtraction that must stay compatible with `iSTARMOD`
- final academic memories in Spanish built around this exact route

## Do Not Default To TEAREDUCE Here

If the task is `MULTISPE + IRAF + iSTARMOD`, do **not** route to TEAREDUCE unless the user explicitly asks for it.

This family is legacy-notebook-adjacent, but it is not a TEAREDUCE-first workflow.

## Golden Path

1. `scripts/legacy_spectroscopy_envcheck.py`
2. `scripts/echelle_multispec_inventory.py`
3. `scripts/fxcor_iraf_workbench.py prepare-session`
4. `scripts/fxcor_iraf_workbench.py run-auto`
5. `scripts/fxcor_iraf_workbench.py merge-overrides` when the CCF needs manual intervention
6. `scripts/legacy_rv_coursework_workbench.py analyze`
7. `scripts/li6708_equivalent_width_workbench.py measure` when the script asks for Li I 6707.8 EW
8. `scripts/coursework_requirements_gate.py template` before closing critical blocks from the script
9. `scripts/workspace_inheritance_audit.py` before carrying material from a previous CODEx iteration into a new one
10. `scripts/sb2_double_gaussian_workbench.py fit-orders` when the SB2 case needs a true two-peak lane order-by-order
11. `scripts/istarmod_workbench.py inspect-tree`
12. `scripts/istarmod_workbench.py prepare-copy`
13. `scripts/istarmod_workbench.py run-sm`
14. `scripts/legacy_external_reference_check.py check` as fixed-reference QA, not as a replacement for the script
15. `scripts/legacy_spectroscopy_report_builder.py scaffold`
16. `scripts/legacy_spectroscopy_report_builder.py populate`
17. `scripts/scientific_writeup_review.py` as advisory scientific write-up QA
18. `scripts/latex_workbench.py compile`

## Operating Rules

- Never touch the original practice tree.
- Prefer a derived ASCII-safe workspace when the original path has spaces or accents.
- Keep IRAF and `iSTARMOD` as the science backends when the course script requires them.
- Use the native skill stack around them for routing, copying, parsing, reporting, and QA.
- Treat the automatic `fxcor` pass as a reproducible baseline, not as a replacement for visual judgement on tricky CCFs.
- If the script literally asks for a double-Gaussian SB2 treatment, do not let plain automatic `fxcor` close that block by itself.
- Treat `v sin i` from the CCF width as a first pass unless the task explicitly asks for a stronger treatment; compare against literature and/or `iSTARMOD` when they disagree.
- Distinguish explicitly between `measured`, `adopted`, and `physically robust`; do not collapse them into one label in the final memory.
- For SB2 cases, surface order-selection and peak-choice flags instead of hiding them in a single averaged velocity.
- For Li I 6707.8 EW, use the narrow helper as a reproducible baseline and still review the continuum/integration windows manually.
- Use fixed external references only where the practice explicitly asks for comparison: PW And from Lopez-Santiago et al. 2003 and GZ Leo/2REJ1101+223 from Galvez et al. 2009 plus Jeffries et al. 1995.
- For GZ Leo/2REJ1101+223, compare RV against the published orbit at the FITS epoch; do not compare the SB2 components against a single static number.
- Before every rerun of `iSTARMOD`, inspect or isolate `rvvalues.dat`; never assume the program is stateless.

## Fast Start

### 1. Preflight

```bash
python3 scripts/legacy_spectroscopy_envcheck.py /path/to/PRACTICA\ 1 \
  --summary-json /tmp/legacy_envcheck.json
```

### 2. Inventory the MULTISPE FITS

```bash
python3 scripts/echelle_multispec_inventory.py /path/to/PRACTICA\ 1/fits_p1 \
  --output-dir /tmp/multispec_inventory \
  --report-md
```

### 3. Prepare and run the IRAF lane

```bash
python3 scripts/fxcor_iraf_workbench.py prepare-session /path/to/PRACTICA\ 1 \
  --output-dir /tmp/p1_iraf_safe

python3 scripts/fxcor_iraf_workbench.py run-auto /tmp/p1_iraf_safe \
  --summary-json /tmp/p1_iraf_safe/run_auto.json
```

If one CCF needs manual correction, edit `manual_overrides.csv` and then run:

```bash
python3 scripts/fxcor_iraf_workbench.py merge-overrides /tmp/p1_iraf_safe \
  --summary-json /tmp/p1_iraf_safe/merge.json
```

### 4. Analyze RV and `v sin i`

```bash
python3 scripts/legacy_rv_coursework_workbench.py analyze \
  /tmp/p1_iraf_safe/parsed/pwand_rv_auto.csv \
  /tmp/p1_iraf_safe/parsed/rej_compA_rv_auto.csv \
  /tmp/p1_iraf_safe/parsed/rej_compB_rv_auto.csv \
  --fits-root /path/to/PRACTICA\ 1/fits_p1 \
  --calibration-csv /path/to/PRACTICA\ 1/FWHM_vsini_datafit.csv \
  --output-dir /tmp/p1_analysis
```

If the SB2 case still looks diagnostic, switch to the explicit two-peak lane:

```bash
python3 scripts/sb2_double_gaussian_workbench.py fit-orders \
  /tmp/p1_sb2_ccf/order_*.csv \
  --fxcor-csv /tmp/p1_iraf_safe/parsed/rej_compA_rv_auto.csv \
  --fxcor-csv /tmp/p1_iraf_safe/parsed/rej_compB_rv_auto.csv \
  --output-dir /tmp/p1_sb2_double_gaussian
```

### 5. Measure Li I 6707.8 EW when requested

```bash
python3 scripts/li6708_equivalent_width_workbench.py measure \
  /path/to/PRACTICA\ 1/fits_p1/npwand_n3.fits \
  --order 33 \
  --output-dir /tmp/p1_analysis \
  --literature-ew-ma 273
```

If the spectrum has already been exported as a simple two-column ASCII table (`wavelength flux`), the same tool can do a first-pass local measurement without pretending there is MULTISPE order metadata:

```bash
python3 scripts/li6708_equivalent_width_workbench.py measure \
  /tmp/p1_ascii/pwand_order33_li.dat \
  --continuum-window 6705.3 6706.0 \
  --continuum-window 6707.8 6708.6 \
  --integration-window 6706.05 6707.85 \
  --output-dir /tmp/p1_analysis
```

### 6. Run `iSTARMOD` in copy

```bash
python3 scripts/istarmod_workbench.py prepare-copy /path/to/PRACTICA\ 1/iSTARMOD \
  --output-dir /tmp/p1_istarmod_copy

python3 scripts/istarmod_workbench.py run-sm /tmp/p1_istarmod_copy \
  --sm-file pwand_n3_ha.sm \
  --cache-policy archive \
  --kinematics-mode auto
```

### 7. Build the report scaffold

Before populating the final discussion, run the narrow external-reference QA:

```bash
python3 scripts/legacy_external_reference_check.py check \
  --rv-summary /tmp/p1_analysis/summary.json \
  --li-summary /tmp/p1_analysis/li6708_summary.json \
  --istarmod-summary /tmp/p1_istarmod_copy/run_sm_summary.json \
  --gzleo-fits /path/to/PRACTICA\ 1/fits_p1/nrej1101_foces02_n2.fits \
  --output-dir /tmp/p1_reference_check
```

```bash
python3 scripts/legacy_spectroscopy_report_builder.py scaffold /tmp/p1_report \
  --title "Practica 1 de espectroscopia"

python3 scripts/legacy_spectroscopy_report_builder.py populate /tmp/p1_report \
  --envcheck /tmp/legacy_envcheck.json \
  --inventory-summary /tmp/multispec_inventory/summary.json \
  --fxcor-summary /tmp/p1_iraf_safe/run_auto.json \
  --rv-summary /tmp/p1_analysis/summary.json \
  --li-summary /tmp/p1_analysis/li6708_summary.json \
  --external-reference-summary /tmp/p1_reference_check/external_reference_check.json

python3 scripts/scientific_writeup_review.py /tmp/p1_report/main.tex \
  --report-md /tmp/p1_report/scientific_writeup_review.md \
  --summary-json /tmp/p1_report/scientific_writeup_review.json
```

If the practice is iterative, audit inheritance before copying any previous outputs:

```bash
python3 scripts/workspace_inheritance_audit.py /tmp/old_codex \
  --output-csv /tmp/p1_audit/inheritance.csv \
  --report-md /tmp/p1_audit/inheritance.md
```

If the script has literal non-negotiable deliverables, gate them explicitly:

```bash
python3 scripts/coursework_requirements_gate.py template \
  --output-csv /tmp/p1_requirements.csv
```

## Caveats

- The route is narrow on purpose. It is designed for this style of university practice, not as a generic IRAF framework.
- `fxcor_iraf_workbench.py prepare-session` expects the known coursework-style filenames under `fits_p1`; it is not a generic IRAF project discovery tool.
- `fxcor_iraf_workbench.py run-auto` should stay blocked rather than pretend success when IRAF, `login.cl`, `txtonly`, or the expected copied workspace is missing.
- The external-reference check is deliberately fixed-reference. Do not turn it into broad ADS/SIMBAD scraping for this route.
- The write-up review is advisory: it should flag overstrong `fxcor`, SB2, `v sin i`, or literature-comparison claims, not decide the final scientific interpretation.
- If the user wants a modern re-reduction from raw frames, route elsewhere.
- If the user explicitly asks for TEAREDUCE, only then consider TEAREDUCE.

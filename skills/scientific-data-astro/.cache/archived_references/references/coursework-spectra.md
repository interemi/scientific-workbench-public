# Coursework Spectra Workflow

This belongs to the `astronomy observational` block, but it is a narrower coursework route rather than a general front door.

## Important Scope Boundary

If the coursework is built around `IRAF`, `fxcor`, `MULTISPE`, SB2 handling, `v sin i`, or `iSTARMOD` on macOS, do **not** use this ASCII-first route as the main entry.

In that case, prefer:

- `references/legacy-spectroscopy-coursework-macos.md`

## Use This Reference For

- reduced 1D spectra stored as simple ASCII files
- coursework or master-level practicals built around spectral comparison or classification
- existing notebooks that need to be copied, lightly augmented, and optionally executed
- final memory/report workflows that should stay reproducible

## Golden Path

For this specific style of task, prefer these pieces in this order:

1. `scripts/ascii_spectrum_workbench.py`
2. `scripts/notebook_workbench.py`
3. `scripts/latex_workbench.py`

If you want one top-level wrapper that ties the first two together, use:

4. `scripts/spectra_ascii_coursework_workbench.py`

That wrapper now also scaffolds an editable `report_project/` by default, so the jump into the final memory is less manual.

## Why This Path Exists

This route is intentionally narrower than the rest of the skill. It exists because a very common academic scenario is:

- a folder of already reduced ASCII spectra
- an existing notebook supplied by the student or course
- a final report or memory to write

That case should not require hand-assembling a workflow from half a dozen unrelated scripts.

## Fast Start

### Inspect and compare the spectra

```bash
python3 scripts/ascii_spectrum_workbench.py spec1.txt spec2.txt spec3.txt \
  --output-dir /tmp/spectra_check \
  --line-window Halpha 6555 6570 \
  --summary-json /tmp/spectra_check/summary.json
```

This gives you:

- inventory CSV
- raw overlay plot
- normalized overlay plot
- QA-style markdown summary
- per-spectrum flags for monotonicity, spacing, and spike-like outliers

### Copy and execute a notebook safely

```bash
python3 scripts/notebook_workbench.py preflight-execution practical.ipynb \
  --summary-json /tmp/notebook_copy/preflight.json
```

That preflight now tells you, before running anything, whether the notebook appears to need:

- notebook-local relative data
- a project-level `cwd`
- optional binaries or backends that are missing
- network access or remote services
- small patch-style intervention for placeholder paths or fragile imports

If the preflight recommends notebook-local data execution, use:

```bash
python3 scripts/notebook_workbench.py execute-copy practical.ipynb \
  --output-dir /tmp/notebook_copy \
  --run-from-source-dir \
  --summary-json /tmp/notebook_copy/summary.json
```

For self-contained notebooks, the default workspace-copy mode still works:

```bash
python3 scripts/notebook_workbench.py execute-copy practical.ipynb \
  --output-dir /tmp/notebook_copy \
  --append-markdown "Copied execution for coursework QA." \
  --append-code "print('Notebook copy executed successfully')" \
  --summary-json /tmp/notebook_copy/summary.json
```

Use `--cell-range 1:12` if only part of a notebook should be executed.

Use `--replace-text FIND REPLACE` for very small execution patches, such as a fallback import or a local path tweak, instead of writing an ad hoc runner for a one-line fix.

### Run the coursework wrapper

```bash
python3 scripts/spectra_ascii_coursework_workbench.py spec1.txt spec2.txt \
  --output-dir /tmp/coursework_bundle \
  --notebook practical.ipynb \
  --execute-notebook \
  --line-window Halpha 6555 6570 \
  --summary-json /tmp/coursework_bundle/summary.json
```

This creates:

- the spectrum analysis bundle
- an optional copied executed notebook
- a top-level coursework bundle report
- a `report_project/` with:
  - `main.tex`
  - generated sections
  - copied figures/tables
  - an advisory LaTeX review summary
  - optional rendered preview pages if the report is compiled

If you also want to try a local compile of that scaffold:

```bash
python3 scripts/spectra_ascii_coursework_workbench.py spec1.txt spec2.txt \
  --output-dir /tmp/coursework_bundle \
  --compile-report \
  --summary-json /tmp/coursework_bundle/summary.json
```

## What This Path Is Good At

- fast QA on simple coursework spectra
- side-by-side comparison before writing interpretations
- keeping notebooks non-destructive
- building a cleaner bridge between data, notebook, and final report
- leaving a real report scaffold ready to edit instead of only a QA bundle

## What It Is Not

- not an observatory pipeline
- not automatic astrophysical classification
- not a replacement for physical judgement or course context

It is a strong preparation layer for the report, not the scientific conclusion itself.

## Important Caution

- Requested line windows are summarized as feature proxies, not as secure line identifications.
- The wrapper is designed to reduce glue work, not to replace scientific judgement.
- Generated report text should be treated as a structured starting point and rewritten with course-specific interpretation before submission.

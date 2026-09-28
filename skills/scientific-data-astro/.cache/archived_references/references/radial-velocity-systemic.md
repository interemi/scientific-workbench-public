# Radial Velocity With Systemic

This belongs to the `astronomy observational` block.

Use this reference when the task is mainly about radial-velocity orbital fitting, period searches, phased radial-velocity plots, or writing up a manual analysis done in `Systemic Live` or the local `Systemic` app.

## What This Route Is For

- manual-in-the-loop radial-velocity fitting
- coursework or small investigations based on `Systemic`
- packaging figures, metrics, notes, and conclusions into a reproducible report path
- inspecting local `Systemic` files such as `.sys` and `.vels`

This route is **not** an automation layer for GUI clicks or browser fitting. In v1, the user still performs the actual fit manually in `Systemic`.

## Start Here

- If you have a `.sys`, a `.vels`, or a local Systemic data folder:
  - `python3 scripts/radial_velocity_workbench.py inspect /path/to/input --summary-json rv_summary.json`
- If you already know the target system and want to prepare a manual analysis bundle:
  - `python3 scripts/radial_velocity_workbench.py scaffold-session out/session /path/to/system.sys --planet-count 3`
- If you want to validate the manifest before rendering the report:
  - `python3 scripts/radial_velocity_workbench.py validate-manifest out/session/session_manifest.json --summary-json out/session/validation.json`
- If you already exported the figures and filled the manifest:
  - `python3 scripts/radial_velocity_workbench.py build-report out/session/session_manifest.json`
- If you want one final handoff zip:
  - `python3 scripts/radial_velocity_workbench.py package out/session --output-zip out/session_bundle.zip`

## When To Use `Systemic Live`

- when the actual fit is easiest in the browser
- when the practice or course material already points to `Systemic Live`
- when you mainly need the skill to organize and document the work around the fit

## When To Use Local `Systemic`

- when you want to inspect bundled `.sys` and `.vels` files
- when you want local context about datasets, observatories, or sample counts
- when you want to reuse local sample systems as validation inputs

Do not rely on the local `systemic_cli` as the core path for this skill route. Treat it as out of scope unless it later proves stable enough to support a real automated workflow.

## What `.sys` And `.vels` Are

- `.sys`
  - a small system-definition file with star metadata and one or more `RV[]` references to RV datasets
- `.vels`
  - a text table of radial-velocity observations
  - usually starts with comment metadata such as telescope, instrument, observatory, reference, and units
  - usually stores:
    - JD
    - radial velocity
    - radial-velocity uncertainty

## Recommended Workflow

1. Inspect the `.sys` or `.vels` inputs with `inspect`.
2. Create an editable session bundle with `scaffold-session`.
   - If you already know the planet count, use `--planet-count N` so the manifest starts with the expected phased-RV slots.
3. Do the actual fitting manually in `Systemic Live` or the local app.
4. Export the key figures into the session `figures/` folder.
5. Fill `session_manifest.json` with:
   - dominant periods
   - FAP values
   - chi2 and RMS before/after
   - planet count
   - phased RV figures
   - dynamical notes
   - conclusions and caveats
6. Run `validate-manifest` to review missing figures, missing metrics, and obvious consistency gaps before rendering.
7. Run `build-report` to create:
   - `rv_analysis_report.md`
   - `rv_analysis_report.tex`
   - `summary.json`
   - optional PDF
8. Run `package` when you want a final handoff bundle.

## What This Route Does Not Automate

- browser clicks in `Systemic Live`
- GUI automation in the local `Systemic` app
- OCR of figures
- extraction of chi2 or RMS from screenshots
- blind inference of orbital parameters from exported images alone
- the scientific judgement of whether a candidate period or multiplanet fit is actually convincing

## Practical Rule

Treat this as a **general radial-velocity workflow with a Systemic backend**, not as a wrapper around one practice. The same route should work for:

- one-planet systems
- multiplanet systems
- coursework reports
- comparison of “no planets” versus “with planets”
- sessions where only figures plus manual notes survive

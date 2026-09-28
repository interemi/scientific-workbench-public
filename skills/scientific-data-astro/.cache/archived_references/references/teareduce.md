# TEAREDUCE

## What This Is

- TEAREDUCE is an optional astronomy-specific backend inside this skill, not the core path.
- Use it when the task is genuinely TEAREDUCE-shaped:
  - reproducing course notebooks
  - wavelength calibration
  - spectral slicing
  - calibration-frame generation
  - TEAREDUCE-style cosmic-ray cleaning
- Keep the native skill stack for everything else: FITS inspection, reporting, deliverables, catalogs, documents, LaTeX, and general scientific analysis.

## Start Here

- If you have a TEAREDUCE notebook pack:
  - start with `python scripts/teareduce_healthcheck.py "/path/to/notebook-pack" --max-notebooks 40 --summary-json teareduce_pack.json`
  - add `--concise` when you want a short terminal decision view instead of the full audit payload
- If you need to decide whether TEAREDUCE is the right backend at all:
  - run `python scripts/teareduce_router.py ...`
- If you want to execute a real notebook without touching the original:
  - use `python scripts/teareduce_notebook_runner.py ...`
- If you only need a fast sanity check that the optional backend is still healthy:
  - use `python scripts/teareduce_smoke_test.py --output-dir teareduce-smoke --summary-json teareduce-smoke/summary.json`

Prefer running TEAREDUCE-facing helpers through `scripts/datanalysis_env.py` when possible. The heavy TEAREDUCE entrypoints also try to re-execute themselves inside `datanalysis` automatically when they are launched from the wrong Python, so direct calls are less brittle than they used to be.

## Use TEAREDUCE When

- The user explicitly names `TEAREDUCE`.
- The user wants to reproduce or inspect real TEAREDUCE practice notebooks.
- The closest faithful path is a TEAREDUCE cookbook or classroom route.
- The task is mostly about:
  - `TeaWaveCalibration`
  - `SliceRegion1D` or `SliceRegion2D`
  - `tea.imshow`
  - `master bias`
  - `master flat`
  - `cr2images`
  - `correct_pincushion_distortion`

## Do Not Default To TEAREDUCE When

- The task is mainly general FITS inspection, catalog work, tabular wrangling, SQL, document analysis, LaTeX, deliverables, or generic reporting.
- The user only wants the outcome that TEAREDUCE happens to support, but not TEAREDUCE itself.
- The workflow needs to stay broad and field-agnostic.

## Operational Routes

### 1. Inventory First

Use `scripts/teareduce_healthcheck.py` to answer:

- is TEAREDUCE importable here?
- what version is installed?
- does the notebook pack look like real notebooks, helper notebooks, or parameterized templates?
- what sidecars and manual steps are visible?

That is the right first move for packs such as `NOTEBOOKS 24:25` or `NOTEBOOKS JUPYTER CLASE`.

### 2. Decide the Backend

Use `scripts/teareduce_router.py` when the boundary is unclear and you need an honest recommendation between TEAREDUCE and the native stack.

### 3. Execute in Copy

Use `scripts/teareduce_notebook_runner.py` for real notebooks:

- it executes copied notebook outputs without modifying the originals
- it preserves each notebook's intended working directory
- it accepts both normal `.ipynb` files and misnamed `.ipynb.txt` notebook copies when the contents are valid notebook JSON
- it classifies runs as `ready`, `missing_dataset`, `missing_sidecar_files`, `parameterized_template`, or generic execution failure

When a coursework notebook is almost runnable but still needs local retargeting, patch the copied execution rather than hand-editing the source notebook first:

- `--replace OLD=NEW` for literal path or token rewrites
- `--set NAME=PYTHON_EXPR` for top-level variable overrides such as `night`, maps, exclusions, or selectors
- `--patch-config patch.json` for the same overrides from a reusable JSON file

Those patch operations are recorded in the copied-run summary so notebook retargeting stays reviewable.

### 4. Prefer Canonical Fallbacks When Local Trees Are Missing

The current consolidated practical routes are:

- canonical master bias
- canonical flat with official filter sidecars
- cookbook `cr2images` fallback when `TEA_procesado_INT` is missing
- cookbook `wavecalib` fallback when `TEA_procesado_INT` is missing

If a classroom notebook fails because the expected dataset tree is absent, do not keep retrying blindly. Route to the matching canonical workflow or cookbook fallback instead.

## Current Local State

- The dedicated environment is `datanalysis`.
- The installed TEAREDUCE version observed locally is `0.7.6`.
- `tea-cleanest` is available in that environment.
- PyCosmic is available through the module name `PyCosmic`, not `pycosmic`.
- Real practice notebooks seen during integration referenced TEAREDUCE versions `0.4.1`, `0.6.8`, `0.7.2`, and `0.7.4`, so version skew is real and should always be surfaced.

Course-pack interpretation observed locally:

- `NOTEBOOKS 24:25` should be treated as a real TEAREDUCE recipe library, not as a pile of unrelated notebooks.
- It may appear either as normal `.ipynb` notebooks or as `.ipynb.txt` copies after a download or export issue.
- `NOTEBOOKS JUPYTER CLASE` is better treated as supporting examples and class material than as the first automated execution target.

## Real Validation Outcomes

- `P2_03_correccion_bias.ipynb` executes successfully in a copied workspace through `teareduce_notebook_runner.py`.
- `P2_04_correccion_flat.ipynb` executes successfully through the canonical flat workflow when the official filter sidecars are staged.
- `P3_04_eliminacion_rayos_cosmicos.ipynb` remains blocked if the expected local processed dataset tree (`TEA_procesado_INT` / `N1/ftdz_45243.fits`) is absent.
- The local `cr2images.ipynb` from `PAQUETE DE COSAS` executes successfully in copy with the official TEAREDUCE cookbook sample FITS.
- The local `wavecalib.ipynb` from `PAQUETE DE COSAS` executes successfully in copy with the official TEAREDUCE cookbook sample FITS.
- `01a_exec_generate_master_bias.ipynb` from `NOTEBOOKS 24:25` parses and executes as a notebook copy, but it is a parameterized template and stops honestly with `Undefined parameter: night`.

Interpretation:

- successful notebooks run in copies
- unsuccessful notebooks fail for missing inputs or parameters rather than because the TEAREDUCE backend itself is broken

## Helper Scripts

- `scripts/teareduce_healthcheck.py`
  - import and version check
  - API and extras inspection
  - notebook-pack scan
  - stage/helper/manual-step profiling
  - `--concise` short mode
- `scripts/teareduce_notebook_runner.py`
  - copied execution
  - working-directory preservation
  - patching support through `--replace`, `--set`, and `--patch-config`
- `scripts/teareduce_router.py`
  - backend recommendation between TEAREDUCE and the native stack
- `scripts/teareduce_smoke_test.py`
  - short consolidated health check
- `scripts/teareduce_master_bias_workflow.py`
  - canonical bias route
- `scripts/teareduce_flat_workflow.py`
  - canonical flat route
- `scripts/teareduce_cookbook_cr2images_workflow.py`
  - cookbook cosmic-ray fallback
- `scripts/teareduce_cookbook_wavecal_workflow.py`
  - cookbook wavelength-calibration fallback
- `scripts/teareduce_bridge.py`
  - small safe wrapper actions such as `statsummary`, `imshow-fits`, and notebook scans

## Practical Rule For Real Notebooks

- If a real dataset tree exists locally, execute notebook copies through `teareduce_notebook_runner.py`.
- If the notebook is almost runnable but still needs local retargeting, patch the copied execution first.
- If the notebook's expected dataset is absent, use `teareduce_healthcheck.py` plus `teareduce_router.py` to validate API fit and route honestly.
- Keep `10a_astrometry_net` as the classroom recipe, but route the actual astrometric solve through `scripts/astrometry_net_workbench.py`.

## What To Read Next

- `references/teareduce-practical-guide.md` for the shortest decision rule
- `references/teareduce-canonical-workflows.md` for deeper case-specific notes once the practical route is already chosen
- `references/architecture.md` if you need the high-level split between public entrypoints and internal helpers

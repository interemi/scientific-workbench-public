# Legacy Spectral Subtraction With iSTARMOD

This belongs to the `astronomy observational` block and is a second-line reference for the legacy coursework route.

## Use This Reference For

- `iSTARMOD` trees shipped with a practice or coursework bundle
- `.sm` files that define one concrete subtraction experiment
- safe copied execution with `MPLBACKEND=Agg`
- technical validation of the legacy environment before writing the memory

## Golden Path

1. `scripts/istarmod_workbench.py inspect-tree`
2. `scripts/istarmod_workbench.py prepare-copy`
3. Edit the chosen `.sm` only in the copy if needed
4. `scripts/istarmod_workbench.py run-sm`
5. Use the outputs as technical evidence in the report, not as an excuse to overclaim scientific precision

## What To Check First

- whether the tree includes `iStarmod.py`
- whether a `.sm` file already exists for the desired line
- whether `lambdas.dat` is present
- whether the tree already contains stale outputs in `logs/` or `p_est_frias/RES/`
- whether there is an embedded Python that the copied runner may want to reuse
- whether the embedded `venv` is broken or non-portable; if so, keep it out of the copied working tree and prefer a known-good external interpreter

## Non-Destructive Rules

- never run inside the original tree
- never edit the original `.sm`
- never patch the original `iStarmod.py`
- prefer a derived runner that only calls `starmod("<file>.sm")` inside the copied tree

## About `unittestreadFITS.py`

If the supplied material mentions `unittestreadFITS.py`, treat it as a diagnostic helper for confirming that the copied `.sm` and FITS paths still make sense.

Do not confuse that diagnostic with the final subtraction run itself.

## Interpreting Outputs

- keep the generated log
- keep any output FITS or residual spectra
- record the line identifier used in the `.sm`
- record the aperture/order used
- keep equivalent-width measurements clearly tied to that copied run

## Caveats

- `iSTARMOD` is legacy software; technical success does not by itself guarantee scientific correctness
- original coursework trees often mix code, old outputs, caches, and sometimes stale virtual environments; the safe route is a clean derived copy with generated logs
- if the copied run fails, keep the log and report the failure precisely instead of improvising a replacement method
- do not silently replace `iSTARMOD` with a modern Python workflow unless the user explicitly changes the method

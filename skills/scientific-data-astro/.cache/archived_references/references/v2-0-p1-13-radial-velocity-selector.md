# v2.0 P1-13: Radial-Velocity Column And Unit Review

This closes the deferred `radial_velocity_workbench.py inspect` app wrapper.
The capability remains an expert astronomy/spectroscopy route. It is not a
general-purpose time-series inspector.

## Boundary

- ScientificWorkbench owns interactive column and unit selection.
- `radial_velocity_workbench.py inspect` keeps its existing `.sys` / `.vels`
  CLI contract.
- The app never edits the selected source table.
- The app stages a normalized `.vels` copy inside the new run directory, then
  invokes the existing backend through `datanalysis_env.py run-tool`.
- The staged copy records source filename, selected columns, time standard,
  input velocity unit, normalized output unit, and
  `Original Modified = false`.

## Review Fields

The app maps candidate columns for:

| Role | Typical names |
|---|---|
| Time | `JD`, `BJD`, `HJD`, `MJD`, `time`, `epoch` |
| Radial velocity | `RV`, `radial_velocity`, `velocity`, `vrad` |
| Uncertainty | `error`, `err`, `sigma`, `uncertainty`, `rv_error` |

The user confirms:

- time column;
- time standard: JD, BJD, HJD, or MJD;
- radial-velocity column;
- velocity input unit: km/s or m/s;
- optional uncertainty column.

MJD is converted to JD by adding `2400000.5`. Velocities and uncertainties in
m/s are converted to km/s. BJD and HJD values are preserved numerically and
identified in the staged metadata.

## App-Facing States

| Input | State | Behavior |
|---|---|---|
| Unique time, RV, uncertainty, and unit candidates | `PASS` | Selections are prefilled and may be reviewed before running. |
| Ambiguous candidate names, missing uncertainty, unknown units, or positional columns | `WARNING` | The selector stays editable and exposes concrete next actions. |
| Fewer than two numeric columns, missing file, directory input, or no usable rows | `BLOCKED_CONTROLADO` | No backend command is run; the app explains the required correction. |
| Backend rejects the staged `.vels` | `FAIL` or `BLOCKED_CONTROLADO` from the existing envelope | ScientificWorkbench shows the backend envelope without reinterpreting the science. |

## Next Actions

When mapping is incomplete, the app emits human-readable actions such as:

- select the time column and confirm its time standard;
- select the radial-velocity column;
- select an uncertainty column or continue explicitly without one;
- confirm whether velocities are expressed in km/s or m/s;
- choose a table containing at least two numeric columns.

## Safety And Exposure

- Exposure: `expert_science`.
- Original files are read-only.
- Generated `.vels` and mapping JSON live in the run folder.
- No claim of applicability outside radial-velocity spectroscopy is made.
- Scientific judgement and orbital fitting remain manual/Systemic-oriented.

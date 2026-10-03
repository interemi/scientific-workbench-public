# Run evidence and scientific review

Scientific Workbench shows five separate evidence stages in Jobs and Results.
They are derived from the retained job, `summary.json`, `manifest.json`, and
declared output files when the view opens. This does not change the persisted
job format or write a scientific approval into the run.

| Stage | What a PASS establishes | What it cannot establish |
| --- | --- | --- |
| Process | The recorded process exit code is zero. | The tool contract, files, and scientific result may still fail. |
| Tool outcome | A recognized success status was retained, with failure, controlled block, and warning taking precedence over success. | The reported result has not been independently checked. |
| Artifact contract | The summary and manifest are readable; every declared output is a regular file within the run folder and matches its recorded size and SHA-256. | The content is scientifically meaningful or correct. |
| Automatic QA | The tool explicitly reports successful QA without findings. | The QA covers every scientific assumption or systematic error. |
| Human scientific review | No automatic PASS is assigned. | An expert's interpretation cannot be inferred from process or QA status. |

`WARNING`, `BLOCKED`, `FAIL`, `INCOMPLETE`, and `PENDING` remain distinct. A
missing or unrecognized status is incomplete, not success. A missing output or
hash mismatch fails the artifact contract. Unsafe paths and missing contract
fields leave it incomplete. The on-demand verifier reads each JSON sidecar
with a 1 MB limit and verifies at most 64 MiB of declared outputs; larger runs
require separate inspection of their retained evidence. A current PASS is a
check of the files at the time of inspection, not a guarantee that they can
never change.

The [small table and FITS image](SYNTHETIC_FIRST_RUN_EXAMPLES.md) and
[crossmatch](SCIENTIFIC_KNOWN_ANSWER_FIXTURES.md) examples have different
method limits. Table profiling counts rows and columns; it
does not infer measurement units, clean values, or assess an analysis. FITS
inspection checks image and header structure, finite-pixel counts, and WCS
metadata for the synthetic case; its PNG is display-only and does not measure
astrometric calibration. The sky crossmatch checks nearest-neighbour angular
separation against a radius, not physical association. Automatic QA is shown
as `INCOMPLETE` when a tool retains no explicit `qa.status` and findings array;
the process and tool stages remain separately visible. A researcher must
review the assumptions that apply to their own data in all three cases.

## Recorded interpretation of a synthetic astronomy case

On 2026-10-03, the maintainer used a fresh, isolated GUI session on macOS
27.0.1 arm64 with the synthetic two-catalog fixture described in
[Scientific known-answer fixtures](SCIENTIFIC_KNOWN_ANSWER_FIXTURES.md).
The guided crossmatch used decimal-degree RA and Dec columns and a 1 arcsec
radius. The retained run folder was named
`20261003_022839_catalog_workbench_crossmatch-sky_c0fb316f-6617-473c-9c07-1348e133343c`.
Jobs displayed `PASS` for process, tool outcome, artifact contract, and
automatic QA; human scientific review remained `INCOMPLETE`. Results showed
the ECSV output as a table preview.

The ECSV contained one `L1`–`R1` pair and no match for `L2`. The tool reported
`0.3599999999694744` arcsec for that pair. An independent haversine calculation
from the fixture coordinates gave `0.3599999999807416` arcsec, an absolute
difference of about `1.13e-11` arcsec, within the predeclared `1e-6` arcsec
tolerance. The manifest's sizes and SHA-256 hashes matched both input CSVs,
the ECSV output, and the summary; `original_modified` was false.

**Maintainer interpretation:** this synthetic output is consistent with the
specified nearest-neighbour geometry and the recorded one-arcsecond cut. It
does not establish physical association, astrometric calibration, epoch or
proper-motion handling, uncertainty propagation, duplicate-match policy, or
correctness on research data. The interpretation is recorded here for this
case only; the app does not record a per-job human approval. The session was
author-run on one Mac, and exact-commit hosted validation of this change is
still pending.

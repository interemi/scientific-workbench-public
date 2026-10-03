# Scientific known-answer fixtures

This page describes the small, synthetic astronomy cases checked by
[`script/check_scientific_known_answers.py`](../script/check_scientific_known_answers.py).
They test the bundled backend and its artifacts against values calculated
independently of the backend. They are regression checks, not calibrated
reference observations or evidence that a scientific result is correct for
real data.

## Reproduce the checks

Prepare the documented Python 3.11 Core environment in [INSTALL.md](../INSTALL.md).
From the repository root, run:

```sh
<path-to-core-python> script/check_scientific_known_answers.py \
  --output-dir <new-directory-outside-the-repository>
```

Replace both angle-bracketed values with real paths; the output directory
must **not exist yet**. The script creates its inputs and results there, never
edits a checked-in example or an original research file, and refuses an output
directory inside the checkout. It retains command logs, summaries, manifests,
artifacts, and `verification.json`, including a source-commit identifier and
whether the working tree was clean. A `PASS` from a dirty tree is local
engineering evidence until the exact committed tree passes hosted CI.
`script/run_portable_core.py` also runs these cases after its environment and
portable smoke checks; GitHub Actions retains the compact verification JSON.

## FITS image and WCS

The generator writes the exact 5,760-byte FITS fixture produced by the app's
first-run example service. Its SHA-256 is
`c40732799d2792ed9131899c2ad5a3b13317004a96e4d40a0d6aa959afc740de`.
It has one 8 × 8 primary image, 63 finite pixels, one NaN, a declared `adu`
pixel unit, ICRS TAN WCS with degree axes, and a reference sky coordinate
of `(150°, −30°)` at pixel `(4.5, 4.5)` in FITS convention. Its signed axes
are −1 and +1 arcsec/pixel. Astropy reads the generated header and checks
these known values; the bundled `inspect_fits` command must then report the
same structure and produce a display-only WCS PNG plus a summary and manifest.
The input hash must remain unchanged. The PNG is a visual orientation aid,
not a calibrated image or an astrometric accuracy measurement.

## Two-catalog sky crossmatch

The generated CSVs declare `source_id`, `ra_deg`, and `dec_deg` in decimal
degrees. The left catalog contains `L1` at `(150, −30)` and `L2` at `(10, 0)`;
the right catalog contains `R1` at `(150, −29.9999)` and `R2` at `(200, 0)`.
Their SHA-256 hashes are, respectively,
`4f77826692c8b2006a7c18f02da2d43d03467b8ab75fe6967bfcf56abe2d84c3`
and
`10937a93aee22bb8f8767e864fe193e2262e1a4915f7677106d11e2b866abab1`.
At a 1 arcsec radius, the expected output is one pair, `L1`–`R1`, and one
unmatched left row. A standard-library haversine calculation supplies an
independent baseline of approximately 0.36 arcsec; the output separation
must agree within `1e-6` arcsec. The check reads the ECSV artifact rather
than relying on process status alone, and verifies the input and output
hashes in the manifest.

The same fixture also checks controlled rejection of a zero radius, a
missing declination column, non-finite RA, RA outside the accepted range,
and an output path that collides with an input. No scientific output may be
written for those cases. A 0.1 arcsec radius instead yields a successful
zero-match result with a `WARNING` app status. The original catalog hashes
must remain unchanged throughout.

This exercise does not account for observation epoch, proper motion,
uncertainty, duplicate counterparts, selection effects, or physical
association. A match inside a radius is only a geometric candidate.

## Current evidence and remaining check

On 2026-10-02, the direct known-answer check passed on the maintainer's
macOS 27.0.1 arm64 Mac in a Python 3.11.15 Core environment. The actual
backend separation was `0.3599999999694744` arcsec, versus an independent
baseline of `0.3599999999807416` arcsec. The local integrated Core run
passed 23/23 feature cases and preserved 1,926/1,926 distribution snapshot
entries. These runs preceded the Phase 3 commit; their verification files
correctly mark the working tree as unclean.

On 2026-10-03, the author also ran the two-file guided crossmatch from a
fresh, isolated GUI session using the modified local source in an ad hoc test
bundle. The Expert form accepted both synthetic CSVs, four decimal-degree
coordinate mappings, and a 1 arcsec radius. Jobs reported exit code 0,
`app_status: PASS`, one `L1`–`R1` match, one unmatched left row, and
`original_modified: false`. Results listed the output ECSV, summary, and
manifest; the ECSV contained the expected pair and separation. The input
hashes remained the two values above, and the output ECSV SHA-256 was
`bf4829bc3911512d9a82a85a22712969d6cf9ca3f1a67adc1cb194814a405ff6`.
The manifest's recorded input and output hashes matched the retained files.
This check caught a missing `artifacts/` parent directory on the first GUI
attempt; the store now creates it after output-root safety checks, with a
Swift regression test. That initial GUI build labeled the ECSV artifact
`unknown` and offered no inline preview, so its table content was checked
from the retained file. A later local build recognizes the ECSV as a table
and exposes a bounded text preview; its [separate evidence stages and
maintainer interpretation](EVIDENCE_STAGES.md) are documented independently.

A fresh integrated Core rerun on 2026-10-03 passed 23/23 feature cases,
including the known-answer check, and preserved 1,926/1,926 distribution
snapshot entries. Its verification JSON again records the uncommitted source
state; the output is local evidence rather than hosted exact-commit evidence.

Check the exact source commit's
[Portable validation runs](https://github.com/interemi/scientific-workbench-public/actions/workflows/portable-validation.yml)
for hosted coverage. The evidence above is an author-run technical check on
one Mac, not a manual test on another Mac, an evaluation with an unfamiliar
user, or scientific validation of real data.

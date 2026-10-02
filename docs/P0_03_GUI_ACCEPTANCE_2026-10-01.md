# P0.03 internal GUI acceptance: three first workflows

**Date:** 2026-10-01

**Application source:** `5c89a1546028d8a593fa8d0fba8002890667fcec`

**Machine:** MacBookPro18,3, macOS 27.0.1, arm64, Swift 6.4

**Backend:** existing Python 3.11.15 scientific environment, not a newly installed Core environment

This record covers an author-run technical walkthrough. It does not measure
whether an unfamiliar person can install or use Scientific Workbench without
help, whether the workflows are scientifically valid for real observations, or
whether the app works interactively on another Mac.

## Declared initial state

The app bundle was built from an isolated clone of the source commit and
launched with `--agent-isolated-session`. In **Settings**, the mother skill root
was set to this checkout's bundled `skills/scientific-data-analysis`, Python
to the existing 3.11.15 interpreter, and the output root to a new folder
outside the checkout and example library. **Save Settings**, **Reload Registry**,
and **Refresh Environment** were used before the accepted runs.
The setup checklist reported the scientific environment, 55 capabilities,
and output folder ready. No cloud account, Ollama action, or optional external
backend was used.

The first table attempt was made before **Reload Registry** and used the
previously installed skill family. It passed, but is excluded from the
exact-source acceptance below. This exposed a missing instruction in the
installation tutorial, which now names the reload step. The accepted table
run and the other three runs used scripts under the bundled skill roots.

## GUI actions and observed results

| Journey | Actions performed in the app | Job-linked result |
| --- | --- | --- |
| Small table | Dashboard → **Prepare Small table** → review `profile_table` under **Normal** → **Run Capability** → Jobs → Results. After the registry reload, the prepared synthetic input was run again against bundled skills. | `profile_table` succeeded with `app_status: PASS`, `original_modified: false`, three rows, four columns (`team`, `tasks_open`, `tasks_closed`, `owner`), and readable `summary.json` and `manifest.json` in its run folder. |
| FITS image | Dashboard → **Prepare FITS image** → review `inspect_fits` under **Expert** → acknowledge the domain/safety checkbox → **Run Capability** → Jobs → Results. | `inspect_fits` succeeded with `app_status: PASS`, `original_modified: false`, one 8 × 8 primary HDU, 63 finite pixels and one nonfinite pixel. The summary retained TAN WCS at `(150°, −30°)`, `ICRS`, degree axes, ±1 arcsec/pixel, and `BUNIT = adu`. Results displayed the generated WCS PNG, `summary.json`, and `manifest.json`, with a display-only/uncalibrated warning. |
| Mixed research folder | Dashboard → **Prepare Mixed research folder** → run `document_intake_workbench` under **Normal** → inspect its Results → **Inspect folder data** → review the retained folder in `cross_domain_data_workbench` → run it → inspect both Results views and their related-run links. | The intake job succeeded and inventoried one Markdown note and one PDF. The separate data job succeeded and inventoried one CSV with three rows; SQL was not requested or executed. Both jobs reported `app_status: PASS` and `original_modified: false`, retained separate summary/manifest/report artifacts, and linked to each other by their shared input folder. |

All four accepted jobs used separate run directories. Their run-folder names,
in the same order, were:

```text
20261001_222319_profile_table_d2aeec78-93fd-416f-b2bc-13c4e3dba84a
20261001_222454_inspect_fits_247a86c6-c29c-4bd4-86f8-ff811025b3f4
20261001_222605_document_intake_workbench_76feee9f-76d4-4c4c-a1a5-afd60b76c0f5
20261001_222640_cross_domain_data_workbench_176df38d-0582-4f8b-a196-b4ead76db133
```

The run folders and generated input copies remain outside Git. The app's
Results view exposed the linked artifacts; a read-only post-run check compared
every generated input with its `expected.json` SHA-256 and checked the four
summary/manifest pairs. All five hashes matched:

| Synthetic input | SHA-256 after the GUI runs |
| --- | --- |
| `ops.csv` | `a6d564500a0c38060ddbb76016a00993f794c5a519122cb58796f74527f56e72` |
| `synthetic_wcs_8x8.fits` | `c40732799d2792ed9131899c2ad5a3b13317004a96e4d40a0d6aa959afc740de` |
| `measurements.csv` | `0801bbdf8ee590c0ec6138ece0f22502f7987a8b20928aa524eff8129da59876` |
| `notes.md` | `7458b9e16eaf119f6bc4f259f10187e5988c49c53cd5e9c40394ffe51daec98d` |
| `observing_note.pdf` | `a80cc3e7d5df9c5e9819774a1ac273f16064570ccc1743a0b332357daa42f126` |

The local source also passed 312/312 Swift tests, release-readiness checks,
and the full quality gate without the optional DOCUS benchmark. The original
DOCUS directory was not used.

The [portable validation run for PR #14](https://github.com/interemi/scientific-workbench-public/actions/runs/36996165055)
passed on the exact candidate head `3d17d4aee9dbdbae0cb54263b606ce72407a1bf7`:
Core on hosted macOS 15 arm64 with the reviewed lock, and Core on hosted
macOS 15 Intel in unlocked compatibility mode. Both jobs built the app,
ran Swift tests, installed Core in a new isolated environment, and checked
synthetic workflows and snapshot integrity. The optional Full job was skipped.
Together with the local GUI walkthrough, this meets the internal P0.03
technical criterion. It does not establish interactive use on another Mac.

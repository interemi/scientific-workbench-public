# Local Core and Full installation cost baseline

- **Measured:** 2026-10-03, 09:19–09:29 UTC
- **Source commit:** `a47da3fd32b1c3a72874802d669a7dfb5028cf94`
- **Scope:** one available Apple-silicon Mac and its existing network connection

This PERF.16 baseline times fresh, locked Python installations and a fresh
SwiftPM build, then separates environment discovery, the first synthetic task,
and broader validation. The measurements are local technical evidence, not a
promise about install time on another Mac or network.

## Environment and method

| Item | Recorded state |
| --- | --- |
| Machine | `MacBookPro18,3`, `arm64`, 16 GiB RAM; macOS 27.0.1 (`26A434`) |
| Swift | Apple Swift 6.4, Command Line Tools with the already-installed macOS 26.5 SDK |
| Bootstrap Python | Existing native Conda Python 3.11.15, pip 26.0.1; it was not updated |
| Core lock | 32 reviewed runtime requirements; SHA-256 `6daddc98d97e3afa89827580888ffac643a7b3e63ff8385ab7eb520d6d186e98` |
| Full locks | 200 runtime requirements, SHA-256 `65cf8885dbbf847f3c413abc19dc8c46d970eab23f1f3127f54f0ad02040a55f`; three build tools, SHA-256 `019579e45416357c53ac3cce8b8f092c58c0bda356cc6def7f7b07cb8ff2b541` |
| Installed tools | Core pip 24.0; Full pip 26.2.1, setuptools 79.0.1, wheel 0.45.1 |
| Network | The Mac's normal internet connection and the installer's default public package index; no proxy or pip-index environment override was set. Throughput and latency were not measured. |
| Synthetic input | Tracked `skills/scientific-data-notebooks/examples/tabular/ops.csv`, 85 bytes, three rows × four columns; SHA-256 `a6d564500a0c38060ddbb76016a00993f794c5a519122cb58796f74527f56e72` |

The operator first ran the Core and Full installer in plan-only mode; both
plans exited successfully without creating an environment. Each subsequent
`--install` used a different, previously absent external destination ending in
`datanalysis`. The installer verified the distribution snapshot and lock,
created a new virtual environment, installed hash-pinned dependencies, ran
`pip check`, checked profile readiness, and preserved its package inventory.
No existing environment was updated. The Full runtime install used its
reviewed `--no-cache-dir` path; the Core install and Full build-tools step may
have used existing pip caches. Neither the OS caches nor network conditions
were controlled.

A local measurement wrapper recorded UTC start/end timestamps and
`time.perf_counter_ns()` elapsed time around each whole command, including
process startup and its checks. Complete stdout/stderr logs and the 22-event
JSONL trace remain in external maintainer scratch space, not Git. Its SHA-256
is `15ad8f937d774321cb75c71d7c499289089db60bf61bb1e6d17072b0945a0688`.
The Core and Full install logs have SHA-256 values
`f1c02152f767e65099010a12ab76a07e04596cb486ed52653ad9249187668fab`
and `38b0da87c11c94aaaabdcf3bfe2facf5e84b02d7581d45da65d917fd198c5fc5`.
Local paths and environment details in those logs are intentionally not
published. All 22 measured commands returned exit code 0.

The build used `swift build --build-system native --scratch-path <fresh external
directory>` with the already-installed SDK 26.5 selected through `SDKROOT`.
The path did not exist before the run. It built sources and linked the app
executable without bundling, signing, or publishing a release. Three later
builds reused that scratch directory and changed no source files.

For discovery, each new interpreter ran `datanalysis_env.py status` three times
with `DATAANALYSIS_PYTHON` pointing explicitly at that interpreter. For first
synthetic use, each interpreter ran `profile_table.py` against the same tracked
85-byte CSV with `--prefer pandas` and a fresh external summary/manifest
destination per attempt. These are backend CLI runs, not a GUI first-use
measurement; the GUI baseline is [separate](LOCAL_PERFORMANCE_BASELINE_2026-10-03.md).
Finally, `script/run_portable_core.py` ran once per new environment with the
corresponding Core or Full profile. It includes strict diagnostics, synthetic
capabilities, scientific known-answer checks, and before/after snapshot checks.

## Timed results

The listed UTC boundaries are the wrapper's start and end for each entire
command. Single-run stages have **no measured variance**.

| Stage | UTC start → end | Elapsed | Result |
| --- | --- | ---: | --- |
| Fresh locked Core setup | 09:19:24.755 → 09:19:43.017 | 18.262 s | Exit 0; `pip check` clear, `core_ready: true` |
| Fresh locked Full setup | 09:19:53.539 → 09:20:49.028 | 55.489 s | Exit 0; `pip check` clear, `core_ready: true`, `full_ready: true` |
| Fresh external SwiftPM build | 09:21:29.898 → 09:22:16.081 | 46.183 s | Exit 0; app sources compiled and linked |
| First Core table profile | 09:24:52.442 → 09:24:56.198 | 3.756 s | Exit 0; summary and manifest written |
| First Full table profile | 09:24:56.286 → 09:25:06.971 | 10.685 s | Exit 0; summary and manifest written |
| Core synthetic validation | 09:26:25.316 → 09:27:31.856 | 66.540 s | 23/23 features and known-answer checks passed |
| Full synthetic validation | 09:27:44.134 → 09:29:33.666 | 109.532 s | 38/38 features and known-answer checks passed |

Repeated observations show how much the *first* command differs from later
commands in these newly installed environments. Values below are seconds and
include process startup. “SD” is the sample standard deviation of all three
shown observations; it is descriptive, not an uncertainty estimate for other
machines.

| Repeated command | Three elapsed values | Median | Sample SD |
| --- | --- | ---: | ---: |
| Core environment discovery | 0.118, 0.072, 0.073 | 0.073 | 0.027 |
| Full environment discovery | 0.095, 0.073, 0.073 | 0.073 | 0.013 |
| Core table profile | 3.756, 0.541, 0.538 | 0.541 | 1.857 |
| Full table profile | 10.685, 1.178, 1.182 | 1.182 | 5.488 |
| Incremental SwiftPM build | 0.689, 0.605, 0.605 | 0.605 | 0.049 |

The installed environments occupied approximately 455 MiB (Core) and 1.43 GiB
(Full) according to `du` after setup. These are filesystem-use observations,
not download-byte totals. All six table profiles reported `status: ok`,
`qa.status: ok`, three rows, four columns, and `original_modified: false`.
Their manifests' input hashes matched the tracked CSV before and after the
runs, and each declared output's size and SHA-256 matched its file.

Both portable verification files reported `PASS`: Core 23 features and Full
38 features, with the 1,926-entry distribution snapshot unchanged before and
after each run. Their retained verification-file SHA-256 values are
`a03edd4e5492ca3235698423240751dd4707d726c0a48d7f78e2add5df0f9455`
(Core) and `7a7a8d162e0898c3ae1144e641cc51f18f21608fbce15daa5d29de38cc428528`
(Full). The Full smoke used the Mac's already-installed TeX tools where needed;
installing those external tools is not part of the timed Full lock setup.

## Discovery discrepancy and limits

Explicit `DATAANALYSIS_PYTHON` made all six `datanalysis_env.py status` runs
select the corresponding new interpreter without warnings. The installer's
Core `env_doctor.json` nevertheless recorded a `WARNING`: its separate
“named datanalysis environment” search found the Mac's pre-existing Conda
environment and marked the new virtual environment's active interpreter as
different. The Full diagnostic also recorded the Conda environment in its
`dedicated_environment` field with `active: false`, though it emitted no
warning and reported `full_ready: true`. This is a discovery/diagnostic
ambiguity on this Mac. The successful direct runs and explicit selection do
not erase it; users should select the new Python path in Settings and inspect
the reported interpreter. The diagnostic behavior merits a separate review.

Fresh-install and smoke durations each have `n=1`; repeating an installation
would require another new environment and possibly different cache/network
conditions. The large first-to-subsequent table-profile difference is
observed, but this test does not isolate Python imports, filesystem caching,
package initialization, or OS effects. It does not justify an optimization
claim. The timings exclude obtaining Python, Apple developer tools, TeX,
Ollama, external astronomy software, or a model download. No new Mac, Intel
machine, different network, public runner, signed installer, or manual
newcomer test was used. No DOCUS or original research data was used.

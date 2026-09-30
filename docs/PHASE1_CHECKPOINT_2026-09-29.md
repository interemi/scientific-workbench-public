# Phase 1 public-repository checkpoint — 2026-09-29

This is a dated **local, pre-PR** checkpoint for the existing public source
repository. It records evidence and open limits; it does not certify a binary
release, scientific correctness, or interactive use on another Mac. The work
started from public `main` commit `f7e8a9636ffe43b2fbf85ea3385b3f45772ff827`.
The review PR must identify its final head commit and exact GitHub Actions runs.

| ID | Checkpoint status | Evidence and remaining work |
| --- | --- | --- |
| P0.10 | Locally addressed | Private vulnerability reporting is enabled in the existing GitHub repository and its **Report a vulnerability** control was observed. `SECURITY.md` now names the supported source branch; bug and feature templates direct sensitive reports away from public issues. No test vulnerability was submitted. |
| P0.02 | Locally addressed | The source, setup matrix, README, and current roadmap agree on all 55 route labels: 17 `app_ready`, 19 `app_ready_partial`, 7 `blocked_optional`, 10 `cli_only`, and 2 `not_applicable_to_app`. `script/check_workflow_requirements.py` checks every ID and the three summaries. These labels do not prove backend availability. |
| P0.12 | Locally addressed | The 66 unique task IDs in the planning PDF were mapped into the current eight-phase roadmap. `ROADMAP.md` and `POST_100_BACKLOG.md` are marked as historical records, while `docs/PUBLIC_READINESS.md` remains a dated validation snapshot. GitHub Issues should link each active task to its eventual closure evidence. |
| P0.07 | In progress | The PR template requires reviewed paths, exclusions, provenance, hashes, and checks. The exact staged snapshot and final head SHA remain to be recorded in the PR before merging. |
| P0.08 | Addressed for this batch | This batch adds documentation, GitHub templates, and a standard-library Python consistency check. It adds no dependency, skill payload, fixture, model, or binary asset. The desk-research references are citations, not bundled third-party code. Review provenance again for each later batch. |
| P0.09 | Automated portion passed | The strict English, link, and portability audit passed locally. An installation tutorial performed without coaching by another person has not been observed; retain that limit rather than inventing acceptance evidence. |
| P0.05 | Local checks passed; installation scope limited | On a MacBookPro18,3, macOS 26.6.2 arm64, Swift 6.3.3, and Python 3.11.15, the quality gate passed 306/306 Swift tests and its other enabled gates. Core synthetic smoke passed 23/23; Full passed 38/38. Both smokes used **existing** isolated environments and preserved the 1,926-entry bundled-skill snapshot. Core and Full lock SHA-256 values were `6daddc98d97e3afa89827580888ffac643a7b3e63ff8385ab7eb520d6d186e98` and `65cf8885dbbf847f3c413abc19dc8c46d970eab23f1f3127f54f0ad02040a55f`. A fresh local installation of the current Full lock was **not** part of this checkpoint. DOCUS was skipped. |
| P0.06 | Locally addressed | Installation and readiness guidance distinguishes this Mac's checks, hosted Core/Full checks at their own commits, source builds, and the unverified experience of a person using another Mac. There is no signed or notarized installer. |

The local Core and Full smoke outputs, including `verification.json` and child
logs, were written to new directories **outside** the source checkout. They
must not be committed or attached publicly without a separate privacy review.
Original DOCUS inputs were not used or changed by this checkpoint.

Phase 1 remains **open** until the reviewed branch is published, exact-commit
CI results are inspected, and the PR records its included and excluded paths.
Independent installation usability remains unverified. A coherent interim PR
is appropriate because this batch contains more than four related improvements;
the default-branch sync should follow review and passing checks.

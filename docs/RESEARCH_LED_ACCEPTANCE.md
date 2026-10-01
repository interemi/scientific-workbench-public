# Research-led product decisions and internal acceptance

**Decision date:** 2026-09-30
**Scope:** the existing Scientific Workbench source repository and local macOS app

Scientific Workbench will not depend on recruiting outside participants or
borrowing another Mac to complete its current roadmap. We will study published
research and the documented workflows of comparable scientific tools, then
verify our own implementation with synthetic inputs, predeclared expected
results, a scripted GUI walkthrough on the available Mac, and exact-commit
GitHub Actions. This replaces earlier *prospective* acceptance criteria that
required another person to use the app. Dated reports of work already done
remain historical records.

This choice limits what we may claim. A published study describes its own
population; official tool documentation shows supported workflows; an author
walkthrough verifies a path on one machine. None measures Scientific Workbench
user satisfaction, independent discoverability, adoption, or manual behavior on
another Mac. We will state those properties as unmeasured, not as failed gates
that silently block every phase.

## Sources and the product inference

| Primary source | Direct evidence | Inference and limit for this app |
| --- | --- | --- |
| [Momcheva and Tollerud (2015)](https://arxiv.org/abs/1507.03989), informal survey of 1,142 astronomers | Software and self-written code were common among respondents, while extensive software-development training was uncommon. | A task-based entry point with transparent commands may help this audience. The self-selected, older survey cannot establish demand for a macOS GUI. |
| [Bordiu et al. (2020)](https://arxiv.org/abs/2012.07686), survey of 329 astrophysics professionals | The authors reported gaps concerning reproducibility and availability of visual analytics. | Provenance and inspectable outputs deserve priority. The survey does not rank our three journeys or prove our interface usable. |
| [Bobra et al. (2020)](https://arxiv.org/abs/2003.14186), solar-physics software survey | Respondents used varied tools and hardware; some worked exclusively on a laptop or desktop. | Local execution is a plausible scenario, not a claim about all astronomers or Apple hardware. Solar physics is a specific population. |
| [Huang et al. (2025)](https://arxiv.org/abs/2503.12309), observation of 20 scientists using their own Jupyter tasks | Participants valued different quality attributes, including reuse and managing state and dependencies. | Explicit environment state and reproducible runs are worth testing. These participants did not use Scientific Workbench. |
| [Astropy WCS tutorial](https://learn.astropy.org/tutorials/wcs-celestial-coordinates.html) | A documented astronomy path opens FITS image data and headers, reads a WCS, and plots sky coordinates and scale. | FITS inspection plus a display-only WCS view is a coherent candidate workflow. Documentation is evidence of a supported task, not its popularity. |
| [TOPCAT match criteria](https://www.star.bris.ac.uk/mbt/topcat/sun253/matchCriteria.html) and [pair-match guide](https://www.star.bris.ac.uk/mbt/topcat/sun253/pairMatch.html) | A sky match requires explicit coordinate columns, angular threshold, and a decision about unmatched or multiple rows. | Our proposed crossmatch must expose units, radius, match policy, and unmatched results. It need not imitate TOPCAT or claim equivalent scientific coverage. |

The [initial desk review](USER_NEEDS_DESK_RESEARCH.md) records the original
P0.01 question and its population limits. This decision extends it to
acceptance criteria; it does not turn external studies into interviews with our
users.

## Astronomy priority decision

The two astronomy flagships are ordered by documented task coherence and
current implementation readiness, not by measured popularity:

| Order | Candidate | Source-backed task and current evidence | Remaining work |
| --- | --- | --- | --- |
| 1 | FITS image and WCS inspection | The Astropy tutorial demonstrates image/header inspection and sky-coordinate display. Scientific Workbench already routes `inspect_fits`; its synthetic 8 × 8 TAN-WCS file has a separately checked reference position and scale. | Add a bounded display-only preview and show the WCS/scale and nonfinite-pixel limits clearly. |
| 2 | Two-catalog sky crossmatch | TOPCAT documents explicit coordinate columns, match radius, and output-row policy. Scientific Workbench has a partial guided `crossmatch-sky` route; the proposed two-by-two fixture has one expected pair at 0.36 arcsec inside a 1 arcsec threshold. | Check known-answer/rejection cases and the complete GUI path, including units and unmatched rows. |

Photometric calibration and radial velocity remain later candidates because
their current first-use paths need stronger calibration, uncertainty, and
reference baselines before they can be presented as a complete workflow. A
table profile and mixed-folder report are product-breadth examples, not a claim
that astronomy surveys ranked those tasks. This prioritization is an
engineering and research inference; user preference is unmeasured.

## Evidence to retain for each active task

1. **Need and scope:** cite the relevant study or comparable-tool workflow,
   distinguish its observed finding from our inference, and name what remains
   unmeasured.
2. **Known answer:** define a synthetic or licensed input, expected artifacts,
   values, units, tolerances, rejection cases, and unchanged-input hashes before
   running the implementation.
3. **Implementation:** record the commit, exact app and skill versions,
   environment, profile, optional dependencies, and complete GUI/CLI path.
4. **Independent calculation:** where a scientific value is checked, compare it
   with a separately expressed method or reference implementation. Do not
   equate a successful process exit with a scientifically valid result.
5. **Internal walkthrough:** follow a written scenario from the initial screen,
   record every action, accessible control, status, failure, and artifact. The
   maintainer or documented UI automation may perform it on the available Mac;
   label the operator and method.
6. **Hosted check:** retain exact-commit Actions status and logs. CI tests
   technical portability of the checked paths, not interactive use on another
   person's computer.

Keep original scientific files and DOCUS untouched. Use a fresh output
directory for each run; retain failed runs and do not edit historical evidence.

## Revised prospective criteria

| Roadmap item | Criterion we can verify here | Claim that remains unavailable |
| --- | --- | --- |
| P0.09 installation guidance | Strict English/link/portability audit; scripted walkthrough of the current `INSTALL.md` commands in a reviewed source copy or hosted clean runner; record exact steps that were not performed locally. | No “uncoached newcomer” or clean consumer-Mac acceptance. |
| P2.01 astronomy priorities | Compare cited astronomy tasks with current capability coverage; document ordered candidate methods, inputs, units, dependencies, planned baselines, limits, and owner. Check fixture feasibility with an independent calculation. Implementation regression fixtures belong to P2.05. | No measured preference ranking among Scientific Workbench users. |
| P0.03 first-use journeys | On the available Mac, start from the documented initial app state and run table, FITS, and mixed-folder examples through the GUI; inspect job-linked artifacts against predeclared values and unchanged-input hashes; record gaps as failures or narrower coverage. | No independent discoverability or satisfaction claim. |
| P0.04 M104 usability protocol | Run a scripted internal navigation, empty/error/recovery, cancellation, and artifact walkthrough with synthetic data, plus accessibility checks. | No observation of a novice's understanding. |
| P1.05 task navigation | Check that common task names and format/profile/readiness filters lead to the intended capabilities from a fresh state; use accessibility identifiers and recorded paths. | No “5/5 users chose correctly” metric. |
| Phase 4 exit | Demonstrate the three end-to-end journeys from selection to result/recovery and keep their artifacts, logs, and CI checks. | No “4/5 users succeeded without coaching” metric. |
| P2.06 and report review | Separate process, artifact contract, automatic scientific QA, and an explicitly recorded maintainer interpretation of the synthetic case. | No general scientific endorsement by independent domain experts. |
| Demand-driven P3 tasks | Require a cited use case, concrete local problem or public issue, permission boundary, and a testable contract before implementation. Defer when evidence or test infrastructure is absent. | No invented user demand, market validation, or unsupported platform claim. |

An item closes only when its *revised* technical and research evidence is
recorded at an exact commit. Existing historical reports may still say a user
study was required under the earlier plan; the current roadmap and active
issues must point to this dated decision. If outside users become available in
the future, their feedback can improve the product, but it is not a prerequisite
for this roadmap.

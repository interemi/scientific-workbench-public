# Scientific Workbench user-needs desk research

**Date:** 2026-09-29

**Status:** documentary research and product hypotheses; no Scientific
Workbench users were interviewed or observed for this report.

The [2026-09-30 research-led acceptance decision](RESEARCH_LED_ACCEPTANCE.md)
supersedes this report's prospective requirement for outside participants.
The cited observations and their limits remain historical research evidence.

## Question and method

If 5–8 potential users could be interviewed, which tasks and product assumptions
would be most important to investigate? We reviewed published studies of
astronomy software and scientific notebooks, one Astropy community report, the
current [capability matrix](CAPABILITY_SETUP_MATRIX.md), and public guidance on
task-based user research. The sources concern other populations and tools. They
cannot establish that people want this app, that its workflows are usable, or
that a specific Mac configuration is common among researchers.

| Source and population | Relevant observation | Limit for Scientific Workbench |
| --- | --- | --- |
| [Momcheva and Tollerud (2015)](https://arxiv.org/abs/1507.03989), informal survey of 1,142 astronomers | Software and Python were common; most respondents wrote some code, while substantial software-development training was uncommon. | Old, self-selected responses; no evidence of demand for a macOS app or these workflows. |
| [Bordiu et al. (2020)](https://arxiv.org/abs/2012.07686), survey of 329 astrophysics professionals | The authors identified gaps in result reproducibility and visual-analytics availability. | A field-level survey does not rank this app's three proposed tasks or establish a usability baseline. |
| [Huang et al. (2025)](https://arxiv.org/html/2503.12309), observation of 20 scientists using their own Jupyter tasks | Participants valued clarity, explorability, reusability, reproducibility, correctness, performance, debuggability, and collaboration. Managing state and dependencies was a design opportunity. | The participants were not recruited to assess Scientific Workbench; the study itself notes institutional and notebook-user sampling limits. |
| [Astropy community engagement report (2024)](https://zenodo.org/records/10603049) | GitHub, documentation, educational material, and practical software use appeared among community engagement routes. | Community engagement is not a test of this app or its installation instructions. |

The [GOV.UK guidance on interviews](https://www.gov.uk/service-manual/user-research/using-in-depth-interviews)
and [contextual observation](https://www.gov.uk/service-manual/user-research/contextual-research-and-observation)
supports asking about recent real tasks and watching work in context, rather
than asking only whether someone likes proposed features. Its
[participant guidance](https://www.gov.uk/service-manual/user-research/find-user-research-participants)
describes 4–8 people as a typical small round. We use that guidance to identify
questions, not to imply that a round occurred here.

## What a small interview round would need to resolve

These are **open questions**, not reported participant answers:

1. Which recent task involved a table, FITS file, spectrum, notebook, or mixed
   scientific folder? What input did the researcher actually receive, and what
   final artifact did they have to produce?
2. Which tools and commands did they use? Where did they switch applications,
   manually copy values, lose units, or recreate an environment?
3. What does a trustworthy result require in that field: calibration, units,
   uncertainty, provenance, a peer check, or a particular output format?
4. Which data cannot leave the machine? Would an optional model help at all,
   and what would need explicit consent?
5. Which installation, permissions, optional backends, and hardware constraints
   would stop use on their own Mac?
6. Could they find, run, and inspect a small synthetic example without coaching?
   A successful command is not enough: can they explain what was checked and
   what still needs scientific review?

If interviews become feasible later, a reasonable **sampling hypothesis** would
include observational-astronomy students/researchers, another astronomy
specialty, and researchers who routinely deliver tables or reports. It is not
a quota that has been met. Use consent, synthetic demonstrations, and redacted
notes; do not collect original research data into the public repository.

## Provisional product decision

Start design work for a researcher or student who already handles scientific
files locally and needs a traceable result more than a broad agent platform.
The first examples should remain a table profile, a FITS inspection, and a
mixed-folder report. This is a **hypothesis**, inferred from the project's
current strengths and the broader studies above, not a validated audience or
a promise of three finished workflows.

The available evidence favors making input/output boundaries, environment
requirements, units, and artifact inspection explicit before expanding the
catalog. It also supports measuring first-use friction with synthetic fixtures.
It does **not** justify claims such as “most astronomers need a Mac GUI,” “a
new user finishes in 15 minutes,” or “4 of 5 users succeed.” Those remain
unmeasured. [P0.03](PRODUCT_IMPROVEMENT_ROADMAP.md#phase-2--choose-a-focused-first-audience-and-tasks)
must still specify the three workflows, and later usability acceptance remains
open until there are actual participants or a clearly limited local walkthrough.

## Acceptance for revised P0.01

This desk-research task is complete when the cited evidence, its population and
limits, the open questions, and a provisional audience decision are published
and reviewed. It does **not** close any separate task whose criterion requires
observing a user or validating the interface independently.

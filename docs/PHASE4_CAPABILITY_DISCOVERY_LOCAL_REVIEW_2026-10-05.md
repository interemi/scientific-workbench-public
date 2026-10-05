# P1.05 capability discovery: local technical review

- **Date:** 2026-10-05
- **Source commit:** `53aa13a3f348be18038a51baadacf68513fd1bb8` on
  `codex/phase4-dashboard-journey`
- **Scope:** local catalog navigation, reviewed metadata, and source guidance;
  public integration pending

Capabilities now opens with all 55 user-facing routes, grouped by the work a
person wants to do. A reviewed index gives each route a plain-language task
name, input-format facets, and a starting Core/Full profile. Unknown future
registry IDs remain visible under **Other tasks** with an undocumented profile
instead of silently receiving an invented classification. The index was
compared against all 55 rows of the [setup matrix](CAPABILITY_SETUP_MATRIX.md):
no ID or Core/Full discrepancy was found.

Search accepts a common task phrase or exact ID. Six visible filters narrow
the task, format, Python profile, catalog readiness, owning skill, and workflow
level; **Clear filters** restores the full catalog. The row and detail panel
retain Normal, Expert, Optional, and Legacy distinctions. CLI-classified routes
show their level and a documentation notice. Generic CLI controls say
**Run CLI Route**; a specialist route with its own guided form keeps its own
button text and the same visible classification. Review confirmation and the
existing input checks still gate execution. The Core/Full and readiness facets
are catalog guidance, not live checks for packages, external programs, suitable
inputs, or scientific validity. **Maintenance** remains a separate six-gate
section with an independent search field.

## Verification on the available Mac

| Check | Observed result |
| --- | --- |
| Machine and build | Apple silicon, macOS 27.0.1 (26A434), Swift 6.4. The source compiled with the already installed macOS 26.5 SDK and SwiftPM native build setting. The normal local SwiftPM build-system path still has the previously recorded property-list parser problem. |
| Swift tests | 327/327 passed in three suites. Three new tests cover 55 reviewed IDs, unique task names, common searches, combined facets, Core/Full special cases, and CLI/readiness classifications. |
| Documentation and repository checks | `check_release_readiness.sh`, `check_repo_hygiene.sh`, `git diff --check`, and `audit_public_documentation.py` passed. The documentation audit found zero broken links, likely Spanish documents, portable-path findings, and unsafe active guidance findings. |
| Fresh test-app navigation | A private test bundle with executable SHA-256 `ea8470320a4e1e31fed6d5786befc56892b6b11203987cb559ab755dce3f4d60` opened with 55/55 routes and the six filter controls exposed through accessibility IDs `catalog.filter.*`. The default selected route was **Check selected Python**. |
| Common task names and safeguards | The accessibility walkthrough located **Profile a CSV table** and **Inspect a FITS image** from their documented phrases. Searching **match sky catalogs** returned 1/55 and showed the Expert review checkbox, required catalog inputs, and a disabled run action. A CLI route retained its distinct label and documentation notice. No scientific job was started for these navigation checks. |
| Empty and separate sections | A nonsensical search returned 0/55 with an explicit empty state. Switching to Maintenance still showed all six gates; returning to Capabilities preserved its query, and **Clear filters** restored 55/55. This caught and resolved an initial shared-search-state error. |

The GUI walkthrough verified the presence and accessibility identifiers of all
six filter controls; it did not manually select every menu option. Their
matching rules were exercised through the unit tests. The test app used bundled
skills, `/usr/bin/python3`, and a private output root, so its Setup Checklist
correctly did not claim Core readiness. The test bundles and logs stay outside
Git. No original scientific data or DOCUS file was touched, and no workflow
was executed in this P1.05 walkthrough.

Hosted checks on the exact integrated commit, an unfamiliar-user study, a
second Mac, and the Phase 4 end-to-end quality gate remain unperformed. P1.05
is locally verified but not yet publicly integrated or closed under the
[research-led acceptance protocol](RESEARCH_LED_ACCEPTANCE.md).

# License decision

## Selected terms

Scientific Workbench uses **PolyForm Noncommercial License 1.0.0** for
project-authored source code, documentation, the app icon, and synthetic fixtures.
The attribution is **interemi**, with the required notice in [NOTICE](../NOTICE).
[LICENSE](../LICENSE) preserves the unmodified
[official license text](https://polyformproject.org/licenses/noncommercial/1.0.0.txt).

This implements the owner's 2026-09-22 requirement that third parties should not
commercially exploit the project-authored work. The owner confirmed that the
material was created with AI assistance and separately selected the public
attribution name. That statement does not independently determine the copyright
status of every file or third-party component.

The earlier Apache-2.0 proposal did not match the clarified requirement and was
not committed or pushed by this task. Its local draft was preserved outside the
checkout. Do not describe the current project as Apache-licensed.

## What recipients may do

The selected license permits noncommercial use, changes, and distribution under
its terms. Recipients must receive the license or its URL and the required
notices. It does not grant general commercial-use permission.

The exact permitted-purpose clauses matter. The license expressly permits
personal research, experiment, testing, and study without anticipated commercial
application. It also permits use by the listed charitable, educational, public
research, public safety/health, environmental, and government institutions
regardless of their funding or resulting obligations.

Do not summarize this as a ban on every economic benefit, every paid researcher,
or every funded institution. The complete license governs; a specific proposed
use may require individual review.

The owner can consider a separate commercial license for rights the owner
controls. This repository grants no such additional permission. Contributors
retain their own rights; their contributions cannot automatically be relicensed
on different terms.

## Public source availability

These restrictions mean the project is **source-available**, not open source
under the [Open Source Definition](https://opensource.org/osd). That definition
requires commercial use and redistribution freedoms that this project does
not grant generally.

Repository visibility is separate from licensing. GitHub explains that public
repositories can be viewed and forked on its platform under its terms even
without a broad source license. A restrictive license does not prevent technical
copying or guarantee compliance. See
[GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

The owner decides when to make the repository public after reviewing the source
scope, third-party obligations, and validation evidence. Public visibility does
not change these license terms or establish scientific fitness.

## Third-party scope and remaining review

The official **No Liability** section supplies the warranty disclaimer and
limitation of liability, expressly limited by applicable law. README, INSTALL,
and the user guide make these terms and actual scientific-use limits visible.
They do not add an absolute waiver, alter the standard license, or promise
immunity from claims. Enforceability depends on applicable law and the actual
circumstances; any stronger distribution-specific terms require legal review.

The project terms do not relicense Python dependencies, model weights, Apple
frameworks, external tools, or scientific inputs. Preserved third-party terms
and required notices continue to apply.

A noncommercial project license does not settle compatibility with GPL/AGPL,
LGPL, MPL, or other component obligations. Before redistributing a combined work,
review the exact copied code, imports/linking, subprocess relationships,
modifications, and distribution form. In particular, do not assume that the
project can impose noncommercial restrictions on third-party copyleft code.

The [source distribution boundary](SOURCE_DISTRIBUTION_BOUNDARY.md) excludes
dependency archives, models, and application/runtime bundles from Git. That
reduces the distributed payload but does not replace a review of any incorporated
third-party source or a future self-contained package.

See [ownership confirmation](OWNERSHIP_CONFIRMATION.md),
[dependencies and licenses](DEPENDENCIES_AND_LICENSES.md), and
[public readiness](PUBLIC_READINESS.md) for the remaining evidence.

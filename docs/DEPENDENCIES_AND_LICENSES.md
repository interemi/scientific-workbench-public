# Dependencies, provenance, and distribution limits

The app descends from M101 commit
`f686c3bd556d4fab684ee051a04cf248d50fdf64`, whose history is preserved in this
private checkout. The current backend snapshot contains 1,446 regular files and 480
internal relative symlinks. The complete inventory is in
[distribution/skill-manifest.json](../distribution/skill-manifest.json).

| Component | Current distribution | Remaining review |
| --- | --- | --- |
| Project-authored Swift/SwiftUI code | Source/resources under PolyForm Noncommercial 1.0.0; Apple supplies its frameworks | Platform and distribution acceptance |
| Five scientific-data skills | Project-authored source, fixtures, and documentation under PolyForm Noncommercial 1.0.0 | Incorporated third-party material, license compatibility, and release review |
| Python core | 13 direct requirements; arm64/Python 3.11 lock for 32 runtime packages tested in a new environment | Other platform locks and exact license terms |
| Python full | arm64/Python 3.11/macOS 15+ lock: 200 runtime packages and three build tools, hashes, and inventory | Fresh installation of the current lock, other platforms, and exact license terms |
| Ollama and models | External installation/download | Resource requirements and each model's license |
| LaTeX, LibreOffice, iWork, OCR, astronomy backends | Optional external components | Workflow-specific setup and use/distribution terms |

The owner's noncommercial-use requirement on 2026-09-22 is implemented by
PolyForm Noncommercial 1.0.0, with attribution to interemi. See
[LICENSE](../LICENSE), [NOTICE](../NOTICE), and the
[owner confirmation](OWNERSHIP_CONFIRMATION.md). This does not relicense
third-party components. Keeping the repository private does not itself resolve
third-party obligations.

## Ownership and attribution map

| Material | Rights and where to check them |
| --- | --- |
| Project-authored app and skill code, documentation, icon, and synthetic fixtures | PolyForm Noncommercial 1.0.0, with `interemi` identified in [NOTICE](../NOTICE). This claim applies only to material whose provenance is confirmed. |
| Python packages installed for Core or Full | Each package retains its authors' rights and its own license. The [Core inventory](../distribution/core-wheel-inventory.json) and [Full inventory](../distribution/full-package-inventory.json) identify the exact reviewed versions, archives, metadata, and available notice files; they are dependency records, not a license grant from Scientific Workbench. |
| Optional applications, astronomy tools, AI services, and model weights | Their respective publishers and authors retain their rights. [Optional backends](OPTIONAL_BACKENDS.md) links to each upstream installation or project page and describes when a user would need it. Check that upstream source for current terms before downloading or using it. |
| TEAREDUCE and iSTARMOD | [TEAREDUCE's package metadata](https://github.com/nicocardiel/teareduce/blob/ac508421ef6c1b1af03b221a2a686a7ffe3960f2/pyproject.toml) names Nicolás Cardiel as author and GPL-3.0-or-later as its license; source notices also credit Universidad Complutense de Madrid. [iSTARMOD's upstream project](https://github.com/flabarga/iSTARMOD) requests citation of Labarga and Montes and publishes GPL-3.0 terms. Neither upstream source tree is bundled here; the compatibility and behavior of our optional routes remain under review below. |
| User-supplied observations, notebooks, documents, and other inputs | Rights remain with their respective owners. The project's license does not apply to a user's scientific data merely because the app processes a copy. |

Attribution and links make provenance visible; they do not grant permission to
relicense, bundle, or combine third-party code contrary to its own terms. A
future app package that includes a runtime, dependency, or model needs a new
inventory and the relevant notices. See the [source distribution boundary](SOURCE_DISTRIBUTION_BOUNDARY.md).

The snapshot retains small examples described as synthetic and historical
project guides. It excludes DOCUS, environments, transient outputs, local
validation runs, and five legacy x86_64 OCR binaries. Those binaries were not
evidence of portable OCR; their Swift sources remain available for review.

General requirements remain unpinned, while `--locked` selects core's arm64
versions and wheel hashes. A new environment passed `pip check`, strict
diagnostics, and 23/23 core smoke cases on the development Mac. Setup retains
lock hashes and `installed-packages.txt`.

The [dated full-lock record](PUBLIC_FULL_LOCK_2026-09-15.en.md) describes the
earlier 215-package installation. A subsequent 214-package lock replaced
PyMuPDF with pypdfium2; the 38/38 local Full smoke used an existing maintainer
environment and that earlier tree. The current Full lock contains 200 runtime
packages, including verified PIMS 0.7 source, and pins pip/setuptools/wheel
for its build. It excludes automatic TEAREDUCE and oletools/pcodedmp installation
and retains `olefile` for legacy Office metadata. Static checks and the archive
audit below passed. On 27 September 2026, this source worktree passed a 38/38
synthetic Full smoke in the maintainer's existing Python 3.11 environment,
with its 1,926-entry backend snapshot intact. That environment is not an
installation of the 200-package lock; fresh locked installation remains open.
Intel remains pending. Python and initial `venv` bootstrap remain outside the
lock; after bootstrap, full installs and uses verified pip 26.2.1.

The [core wheel inventory](../distribution/core-wheel-inventory.json) contains
metadata from downloaded packages, rather than licenses inferred from names.
Three packages—charset-normalizer, fonttools, and lxml—do not declare
License-Expression or license classifiers in those wheels. This does not mean
they are unlicensed. Their legacy fields reported MIT, MIT, and BSD-3-Clause
respectively, which were recorded in the inventory.

The wheels contain license texts; fonttools and lxml also include notices for
incorporated components. Header inspection does not complete that review.
Material incorporated into skills, exact full-package terms, models, and
external backends need their own review. The project-material license does not
implicitly authorize redistribution of all third-party material.

The [full inventory](../distribution/full-package-inventory.json) records
metadata for exact distributions whose archives were checked by hash.
Declarations needing specific review include enum-tools and pyxlsb (LGPL),
and certifi and fqdn
(MPL). These are reported metadata, not a determination of which obligations
apply to the app, subprocesses, or a future bundle. The inventory alone does
not authorize redistributing those packages.

The [dated technical notice/use review](PUBLIC_DEPENDENCY_REVIEW_2026-09-15.en.md)
indexes 426 license/notice members across the **previous** 218 verified
distributions. A later 25 September 2026 audit covered 217 archives and 425
named notice members in the former 214-package lock; its inventory SHA-256 was
`960cb0091315cefaa5d9fcdb9a0850a179461f81ad88ffe22ec15d62e09b595d`.
On 27 September 2026, the current **203 exact archives** (200 runtime and three
build tools) were rechecked from the retained audit-only downloads outside Git:
203/203 SHA-256 matches and **402 named notice members**, without installation
or package execution. The inventory SHA-256 is
`e514d77f5b3836c729803e8acfb7ea19bf4010475255e79126110703181be049`.
The private run report is retained outside Git. Both audits found no named
notice member in the `flatbuffers==25.12.19`, `pyxlsbwriter==0.1.0`, or
`rapidocr-onnxruntime==1.4.4` wheel. `script/audit_dependency_licenses.py`
checks archives and indexes named notices; its report says
`license_review_complete=false`. This is not legal clearance or permission to
bundle packages. The RapidOCR ONNX weights and their provenance remain covered
by [the distribution boundary](SOURCE_DISTRIBUTION_BOUNDARY.md). A changed
inventory requires a new archive audit.

Follow-up inspection of those **exact wheels** found different evidence for
each missing notice. The `flatbuffers` metadata declares Apache 2.0, and its
[upstream repository](https://github.com/google/flatbuffers/blob/master/LICENSE)
publishes that license, but the locked wheel contains no named notice file.
The `pyxlsbwriter` metadata has an MIT classifier without a license value or
notice; its separately checked [0.1.0 source archive](https://pypi.org/project/pyxlsbwriter/0.1.0/)
also has no named notice. The `rapidocr-onnxruntime` metadata declares
Apache-2.0, but its locked wheel contains three ONNX models and no named
notice. The model hashes match RapidOCR's
[versioned model catalog](https://github.com/RapidAI/RapidOCR/blob/64b1c680be9992b7500aecd89a484d161443612a/python/rapidocr/default_models.yaml);
the [upstream v1.4.4 source](https://github.com/RapidAI/RapidOCR/tree/86ae3f5079df3422c1829cd84baf19bc8a7a9453)
attributes the original model copyright to Baidu. Exact model-specific
attribution and any future redistribution notice still require review. These
metadata and provenance findings do not turn the three missing wheel notices
into a completed license review. The checked archive hashes, model hashes,
and source-only boundary are recorded in
[source distribution boundary](SOURCE_DISTRIBUTION_BOUNDARY.md).

A targeted historical check on 25 September 2026 downloaded four exact wheels
from the former 214-package Full inventory into an audit-only directory outside Git. Their
SHA-256 values matched the inventory; the archives were inspected without
installation or code execution:

| Exact wheel | Named notice members |
| --- | ---: |
| `teareduce==0.7.9` | 1 (GPL-3.0 text) |
| `oletools==0.60.2` | 7 (package and bundled third-party notices) |
| `pcodedmp==1.2.6` | 1 (GPL-3.0 text) |
| `pypdfium2==5.13.0` arm64 | 19 (including PDFium build dependencies) |

These 28 members were a subset of the former 425-member archive index; only
`pypdfium2` remains in the current lock. Named files alone do not establish
license compatibility or complete attribution. The three wheels without named
notices, incorporated material, external GPL routes, and any future bundled-app
review remain open.

## Copyleft integration decision before public opening

Current PDF workflows use pypdfium2 for rendering, embedded-image extraction,
Quick Look fallback, presentation previews, and the compiled-report preview in
the spectroscopy coursework workflow. The maintainer contract regression now
creates its synthetic PDF with matplotlib. Two archived internal OCR helper
copies and a historical v1.9 documentation regression still contain `fitz`
calls. No active capability route invokes those historical files; launching
the v1.9 regression separately would require PyMuPDF, which is absent from the
current Full lock. These historical files are retained for traceability, not
as supported PDF workflows. The current tree and Full lock have these optional
integration touchpoints, with different execution and installation boundaries:

| Package and observed terms | Project integration found in this tree | Decision needed |
| --- | --- | --- |
| External teareduce, GPL-3.0-or-later in the former inventory | `teareduce_healthcheck.py` discovers metadata in its launcher Python without importing the package; the legacy-named `teareduce_bridge.py` computes native NumPy/Matplotlib summaries and quicklooks. User-provided notebooks may import TEAREDUCE in a separately installed kernel while the project runner executes a copy. | Full no longer installs TEAREDUCE. Kernel availability and scientific/API compatibility have not been demonstrated on the current tree; keep the external interaction and its license terms under review. |
| External iSTARMOD, GPL-3.0 declared by its upstream repository | `istarmod_workbench.py` operates on a user-provided legacy tree through subprocesses; no upstream tree is bundled | Review rights and version/layout compatibility before promising execution; its current upstream layout is not shown to satisfy the legacy adapter. |
| Historical oletools / pcodedmp chain, GPL declaration for formerly pinned pcodedmp | `document_semantics.py` no longer imports oletools. Legacy `.xls` reports `vba_assessment=not_assessed`; neither package is in the current Full lock. | Preserve the disclosed loss of `.xls` macro assessment. No real `.xls` positive/negative comparison has been made on this tree. |

The [TEAREDUCE 0.7.9 project metadata](https://github.com/nicocardiel/teareduce/blob/ac508421ef6c1b1af03b221a2a686a7ffe3960f2/pyproject.toml)
declares GPL-3.0-or-later. Its [package initializer](https://github.com/nicocardiel/teareduce/blob/ac508421ef6c1b1af03b221a2a686a7ffe3960f2/src/teareduce/__init__.py)
and the `statsummary` and `imshow` modules previously used by our bridge carry Universidad
Complutense de Madrid copyright notices. The separately maintained
[TEAREDUCE cookbook](https://github.com/nicocardiel/teareduce-cookbook/tree/ba360766c98579d9a177223750507774ad2fc038)
also includes a GPL v3 license. These facts do not identify every person or
institution authorized to grant an additional license for the exact
integration; no such permission has been obtained.

The [GNU license FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#IfLibraryIsGPL)
describes its interpretation of programs that link to GPL libraries, including
modules reached through interpreted-language bindings. The
[PyMuPDF licensing documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
explains the former backend's AGPL/commercial terms; the
[pypdfium2 licensing record](https://github.com/pypdfium2-team/pypdfium2#licensing)
lists Apache-2.0/BSD-3-Clause and bundled PDFium dependency notices. The
remaining GPL combination questions are material, but these sources do not
settle how each Scientific Workbench route would be treated in every
jurisdiction or distribution scenario. The technical
finding is **open**; absence of wheels and model weights from Git does not by
itself clear it. Do not represent the full profile or a downloadable bundle as
license-cleared until the applicable terms and integration are reviewed. A
source-only publication decision needs an explicit resolution or a documented
scope change that preserves the private original and its evidence.

## Concrete resolution work

The full-profile installer names `pypdfium2` and `olefile` as direct
requirements. It no longer names TEAREDUCE or oletools; the current lock also
excludes their orphaned dependencies. The Core profile is a smaller separate
set. No wheels are committed to Git. An optional TEAREDUCE notebook uses a
separately installed kernel chosen by the user; the package is not included in
the Full installation or in this source tree. This technical separation is not
a legal conclusion about every user-created combination.
The alternative Conda recipe, `skills/scientific-data-analysis/environment.yml`,
also names pypdfium2 in place of PyMuPDF; it is not covered by the pip lock or
the fresh-install evidence for that lock.

| Integration | Preferred technical route if rights are not cleared | Verification before changing public instructions |
| --- | --- | --- |
| PDF recovery, OCR, Quick Look, presentation preview, and spectroscopy compiled-report preview | Current capability paths use pypdfium2, and PyMuPDF is absent from the revised Full lock. | The local 38/38 Full smoke and focused PDF rendering/image-extraction test passed with installed pypdfium2 5.6.0, while the lock pins 5.13.0. On 28 September 2026, a focused synthetic test rendered the astronomy and notebooks helpers and verified unchanged input; the maintainer regression's matplotlib PDF yielded extractable text. A fresh locked install, current wheel notices, and exact exported-candidate review remain necessary. |
| TEAREDUCE external notebooks | Healthcheck and bridge no longer import TEAREDUCE; bridge numerical and image results are native and must not be described as TEAREDUCE-equivalent. Full no longer installs the package. Copied user notebooks remain an external route with explicit code trust and a selected kernel. | Verify selected-kernel operation on a safe external notebook and protected inputs; do not infer kernel availability from a healthcheck of the launcher. Review the applicable license interaction before claiming the route is cleared. |
| oletools/pcodedmp | The `.xls` inspection preserves stream and metadata extraction through direct `olefile`, but deliberately does not claim macro detection. The previous `has_vba` value is no longer produced for `.xls`; no substitute parser is claimed. The chain is absent from the current lock. | Retain the limitation in user docs and test actual `.xls` samples only when safe fixtures are available. |
| External iSTARMOD | Keep the user-provided tree outside Git and establish which upstream version/layout the legacy adapter supports. Seek permission or redesign if a future bundle would include its GPL code. | Demonstrate `inspect-tree`, `prepare-copy`, and a real run on a safe copy of a known compatible tree; retain version, source, and license evidence. |

The former narrow oletools finding came from the checked `0.60.2` installed
source and an earlier version of this project's `document_semantics.py`; it did
**not** clear the full dependency graph. The [upstream oletools license](https://github.com/decalage2/oletools/blob/master/LICENSE.md)
and [teareduce package record](https://pypi.org/project/teareduce/) are source
references for that review. Publishing the full integration without a decision,
or telling users to assemble an incompatible combination themselves, is not a
validated workaround. The owner wants all 55 capability routes documented, so
any exclusion or substantial redesign must be recorded as a scope decision
rather than silently reducing the catalog.

For `.xls`, `document_semantics.py` uses `olefile` to inspect streams and
metadata, but now always reports `vba_assessment=not_assessed` and omits
`has_vba`. A VBA-looking stream name is not proof that macros are present or
absent. This is a disclosed reduction from the earlier optional oletools
assessment, not a validated replacement. The checked oletools implementation
also inspected orphan streams; [its documentation](https://github.com/decalage2/oletools/wiki/olevba)
warns that detection can have false positives. No `.xls`, `.xlsm`, `.docm`, or
`.pptm` fixture is tracked in this checkout, so the new result must not be
presented as a macro-safety verdict. The OOXML member inventory's separate
`has_vba` flag remains a structural presence hint, not a security scan.
The former GPL dependency chain is absent from the current Full lock; the
remaining external-tool and notice questions still need their own decisions.

The [source distribution boundary](SOURCE_DISTRIBUTION_BOUNDARY.md) records
what is actually in Git and blocks accidental wheels, models, and app bundles.
It also records upstream OCR-model evidence and the missing pyxlsbwriter notice,
and identifies the additional decisions needed for a self-contained app.

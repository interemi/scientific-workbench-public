# Dependencies and third-party notices — September 15, 2026

English publication edition of `docs/PUBLIC_DEPENDENCY_REVIEW_2026-09-15.md`
at private commit `7bb7d0f`. Original SHA-256:
`21cb17141203c3b2dc536405a70722b8602ee18efc5d650f904951323f58b485`.
The Spanish original remains unchanged privately. Results and pending decisions
describe the source date; translation is not a new dependency or legal review.
Current decisions are tracked in [DEPENDENCIES_AND_LICENSES.md](DEPENDENCIES_AND_LICENSES.md).

Reviewed base: `6d95ae0d3606249bdcd5a232427be890e307c187`, branch
`codex/public-readiness-foundation`. This review supplies technical evidence for
the publication decision. It neither grants Scientific Workbench a license nor
declares redistribution conditions resolved.

## Verified coverage

The new `script/audit_dependency_licenses.py` verifies downloaded archive hashes
against the core/full inventories and reads license/notice members in memory,
without extraction or code execution. Files under license directories are
included even when named `terms.txt` or after an incorporated library. It rejects
mismatched hashes, unsafe member paths, linked notices, excessive sizes, and
existing output files.

Result: 218 exact distributions verified, 426 notice/license members indexed,
zero technical errors. Core shares its distributions with full in these
inventories, so they are not counted twice. All 50 distribution tests pass,
including seven auditor tests.

Each member is identified by archive, size, and SHA-256. The report retains
`license_review_complete: false`: indexing files does not prove interpretation
of every text or coverage of every incorporated component. Name selection is
heuristic and may miss notices in code comments, images, or differently named files.

## Dependencies requiring explicit decisions

| Pinned package | Observed declaration | Verified use in Scientific Workbench | Pending work |
| --- | --- | --- | --- |
| PyMuPDF 1.28.2 | AGPL 3.0 or commercial license | `fitz` in PDF recovery, OCR, Quick Look, presentation previews | Review applicable terms for these uses and the chosen distribution format |
| teareduce 0.7.9 | GPL-3.0-or-later; LICENSE.txt contains GPLv3 | Direct import in `teareduce_bridge.py` for statistics/visualization, plus notebook workflows | Review project licensing and combined-work conditions before publication |
| pcodedmp 1.2.6 | GPLv3 | oletools dependency; `document_semantics.py` uses its VBA analyzer | Review dependency chain and required notices |
| enum-tools 0.13.0 | LGPL-3.0-or-later | numbers-parser dependency for Numbers documents | Review terms and distribution format |
| pyxlsb 1.0.10 | LGPLv3+ | XLSB reading in tabular_io, document_semantics, semantic_diff | Review terms; retain license notice and supplementary text |
| certifi 2026.7.22 and fqdn 1.5.1 | MPL 2.0 | Environment network/validation dependencies | Review notices for the distributed versions |

Declarations come from metadata and files in verified wheels. Running a
component in a separate process is not assumed to resolve its license conditions.

In the PyMuPDF wheel, `COPYING` contains only a dual-license statement, not the
complete AGPL text. This limits what the index proves. The
[official documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
also states both routes; obtain and review the applicable full terms instead
of treating that short file as a completed review.

## Three wheels without an identifiable notice file

| Distribution | Additional evidence | Status |
| --- | --- | --- |
| flatbuffers 25.12.19 | Apache 2.0 metadata; LICENSE exists in upstream tag v25.12.19 | Upstream text located; review inclusion after redistribution scope is defined |
| pyxlsbwriter 0.1.0 | MIT classifier; PyPI wheel/sdist lack identifiable license files and project URLs in metadata | Locate exact license text and rights-holder attribution before completing review |
| rapidocr-onnxruntime 1.4.4 | Apache-2.0 metadata; LICENSE and README available in tag v1.4.4 | Review code and OCR weights separately |

Failure to identify a file by name does not prove absence of a license. A
classifier is also insufficient to reconstruct a rights-holder attribution or
invent a third party's LICENSE file.

Commit-pinned upstream references:

- [FlatBuffers LICENSE](https://github.com/google/flatbuffers/blob/7e163021e59cca4f8e1e35a7c828b5c6b7915953/LICENSE), tag v25.12.19.
- [RapidOCR LICENSE](https://github.com/RapidAI/RapidOCR/blob/86ae3f5079df3422c1829cd84baf19bc8a7a9453/LICENSE)
  and [README](https://github.com/RapidAI/RapidOCR/blob/86ae3f5079df3422c1829cd84baf19bc8a7a9453/README.md), tag v1.4.4.
- [pyxlsbwriter 0.1.0 on PyPI](https://pypi.org/project/pyxlsbwriter/0.1.0/).

## OCR weights included in a dependency

The RapidOCR wheel includes three models. Installing full downloads them as
part of the package even when no Ollama model is downloaded:

| Member under `rapidocr_onnxruntime/models/` | Bytes | SHA-256 |
| --- | --- | --- |
| ch_PP-OCRv4_det_infer.onnx | 4,745,517 | `d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9` |
| ch_PP-OCRv4_rec_infer.onnx | 10,857,958 | `48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b` |
| ch_ppocr_mobile_v2.0_cls_infer.onnx | 585,532 | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

The tag's README credits Baidu for the OCR models and describes conversion from
PaddleOCR. The complete, untruncated Git tree of that commit contains no ONNX
files. This check therefore could not connect wheel bytes to a model file in
the tag. Original sources, conversion, and applicable terms for each weight
remain to be recorded. These are not Scientific Workbench's own weights.

## Repeating the check

Download the exact distributions referenced by the inventories beforehand and
keep them outside the checkout. The auditor neither downloads files nor
installs dependencies. Multiple `--archives-dir` arguments are supported:

```bash
python3 script/audit_dependency_licenses.py \
  --archives-dir "$HOME/ScientificWorkbenchRuns/dependency-archives" \
  --output "$HOME/ScientificWorkbenchRuns/dependency-notices-01.json"
```

The output parent must exist and the output file must be new. Missing files or
hash mismatches produce technical FAIL with a retained report; technical PASS
never changes `license_review_complete` to true.

External local evidence: `public-full-lock-20260915.wc19ryft/pip-pinned/` retains
`dependency-notices-nested.json` and `dependency-license-tests.log`. The initial
basename-only exploration remains in `dependency-notices.json`; the current
auditor also includes license directories.
`dependency-license-review-20260915.pm7v9fw1/` retains the pyxlsbwriter sdist,
RapidOCR tree, and model-hash inventory.
Copying texts from GitHub's raw host encountered a TLS error. That attempt was
preserved; LICENSE and README were recovered through the API at the same commit
with verified blob identifiers. `upstream-api-evidence.json` records SHA-256
values and URLs.

At the source date, ownership of project skills/examples/guides, the project
license, and third-party notice/material review remained open. Decisions must
consider actual scope: sources in Git, installations downloaded by each user,
or a future bundle containing dependencies. No component was packaged,
uploaded, removed, or relicensed in this batch.

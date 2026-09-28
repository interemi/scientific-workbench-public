# Source Distribution Boundary

Scientific Workbench is distributed here as a **source repository**. No
redistributable application bundle is provided. This boundary determines which
third-party materials are present in Git and which are downloaded independently into a
user-owned environment.

This document records engineering evidence. It does not change the selected
project license or replace review of the applicable third-party terms.

## Material present in the repository

This source repository contains:

- the Swift and Python source needed by the app and the five-skill family;
- setup, validation, and release scripts;
- core and full lock files containing package names, versions, URLs, and hashes;
- the reviewed skill snapshot and its manifest;
- synthetic fixtures and their provenance records; and
- documentation checked for English, links, and portable paths.

The repository does not contain Python wheels or source distributions, Python
environments, ONNX/Ollama model weights, signed app bundles, disk images,
installer packages, DOCUS, credentials, or local scientific runs. The Git
publication gate rejects these dependency and model payloads if they become
visible to Git.

## Installation boundary

The setup tool creates a new environment in a location chosen by the user and
asks the package index for the exact locked artifacts. Hashes are checked where
the platform lock supplies them. Scientific Workbench does not copy those
downloaded artifacts back into the repository.

This distinction does not make dependency licenses irrelevant. It means that
publishing source and shipping a self-contained app have different
redistribution scopes and need separate decisions.

| Distribution mode | Third-party payload | Current status |
| --- | --- | --- |
| Public source repository | References, lock data, source-level imports, and any third-party material already copied into Git | Reviewed source boundary; project-authored material uses PolyForm Noncommercial 1.0.0. Dependency terms and optional integrations remain separate. |
| User-created Python environment | Packages downloaded directly for that user | Core and Full locks passed fresh hosted arm64 installation. The focused Full job did not run the 38-case Full smoke. Package terms still apply to use. |
| Signed or downloadable app bundle | Any runtime, package, model, or backend embedded in the artifact | Not designed or approved; requires a new inventory, notices, license review, signing, notarization, and clean-machine test |
| Release archive containing dependencies | Redistributed wheels, source archives, model files, or external binaries | Prohibited by the current source boundary |

Adding an embedded Python runtime, copying a prepared environment, vendoring a
wheel, or placing model weights in Git changes this boundary. Such a change must
update the inventory and be reviewed before packaging.

## Sensitive dependency evidence

The exact full-profile package inventory remains the canonical list of resolved
versions. The following findings refine two previously open provenance items.

### RapidOCR 1.4.4 model weights

The three model files inside the locked `rapidocr-onnxruntime` wheel are not in
this Git repository. Their SHA-256 values are:

| Wheel member | SHA-256 |
| --- | --- |
| `ch_PP-OCRv4_det_infer.onnx` | `d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9` |
| `ch_PP-OCRv4_rec_infer.onnx` | `48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b` |
| `ch_ppocr_mobile_v2.0_cls_infer.onnx` | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

Those hashes match the ONNX PP-OCRv4 entries in RapidOCR's model registry at
commit [`64b1c680be9992b7500aecd89a484d161443612a`](https://github.com/RapidAI/RapidOCR/blob/64b1c680be9992b7500aecd89a484d161443612a/python/rapidocr/default_models.yaml).
The peeled `v1.4.4` commit
[`86ae3f5079df3422c1829cd84baf19bc8a7a9453`](https://github.com/RapidAI/RapidOCR/tree/86ae3f5079df3422c1829cd84baf19bc8a7a9453)
states that Baidu holds the OCR model copyright and that the project uses
Apache-2.0. The current upstream README further states that converted ONNX
artifacts use the upstream Apache-2.0 terms.

This establishes a direct hash route and upstream attribution. It does not
authorize Scientific Workbench to embed the weights in a future app bundle.
That bundle would need the applicable Apache-2.0 notice and a final review of
the exact model source and conversion record.

### pyxlsbwriter 0.1.0

The official PyPI metadata identifies author Krzysztof Duśko and includes the
classifier `License :: OSI Approved :: MIT License`. The metadata has no
`License-Expression`, license value, author email, or project URL. The verified
wheel and source archive contain no file whose name identifies a license,
copying notice, or notice file:

| Artifact | Verified SHA-256 |
| --- | --- |
| `pyxlsbwriter-0.1.0-py3-none-any.whl` | `f62bd36962f6d95335c8456e9705f00c4dd0f02da0655a2e817583569aa62eab` |
| `pyxlsbwriter-0.1.0.tar.gz` | `9de6750b1e5197aa18bf9d76a92b4731900d9fe1a73f6393cbd234ad183df828` |

The [PyPI page](https://pypi.org/project/pyxlsbwriter/0.1.0/) renders “MIT
License” from that classifier, but the artifacts do not provide the exact
copyright notice that must accompany an MIT-licensed redistribution. Do not
vendor or bundle this package until the exact notice and authority are obtained
from an upstream source. A source-only publication may keep the locked
dependency reference while this package remains downloaded by the user.

## Source publication safeguards

For this source repository and later updates:

1. preserve the selected PolyForm Noncommercial 1.0.0 license and required attribution for project-owned material;
2. record ownership and notices for fixtures, guides, icons, and copied source;
3. keep dependency archives and model files outside Git;
4. preserve the two private preparation histories without publishing or
   rewriting them; and
5. run history, secret, documentation, snapshot, test, and quality checks on
   each source commit before using its results as publication evidence.

A future downloadable app is a separate milestone and must not reuse the
source-only assessment as proof that bundled dependencies are cleared.

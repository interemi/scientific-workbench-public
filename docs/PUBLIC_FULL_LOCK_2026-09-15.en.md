# Full-profile lock — September 15, 2026

English publication edition of `docs/PUBLIC_FULL_LOCK_2026-09-15.md`
at private commit `4aae9a6`. Original SHA-256:
`d4b726447a8eba2c04c08c8913f2e641e2bc31663fd0f7360afacedc23d49db7`.
The Spanish original remains unchanged privately. Results and pending decisions
describe the source date; translation is not new execution evidence.

This batch continues from `dd466fddcda2f830669da42f22843c7d49324d27` on
`codex/public-readiness-foundation`. It resolves the dependency-lock blocker in
the [earlier full validation](PUBLIC_FULL_VALIDATION_2026-09-15.en.md), whose
report and runs remain preserved. Scientific Workbench remains private.

## What is pinned

| Group | Contents | File |
| --- | --- | --- |
| Runtime | 215 versions: 214 wheels and PIMS 0.7 source | `distribution/locks/full-macos-arm64-py311.txt` |
| Installation and build | pip 26.2.1, setuptools 79.0.1, wheel 0.45.1 | `distribution/locks/full-build-py311.txt` |
| Technical provenance | Names, versions, URLs, hashes, dependency/license metadata | `distribution/full-package-inventory.json` |

Downloaded distributions were checked against SHA-256 values published by PyPI
and confirmed not to have the `yanked` flag at the time. This identifies files;
it is not an audit of every package's code or a guarantee of future availability.

PIMS 0.7 is published as source. Its `setup.py` uses setuptools and bundled
versioneer, with no declared native extensions. The version installed during
the first validation is retained; it is not replaced with an older release just
to obtain a wheel. Reviewed source hash:
`55907a4c301256086d2aa4e34a5361b9109f24e375c2071e1117b9491e82946b`.
Reference: [PIMS 0.7 distributions on PyPI](https://pypi.org/project/PIMS/0.7/#files).

## Installation and protections

The installer requires a new external destination and verifies the snapshot
before creating the environment. For `--profile full --locked`, it:

1. Checks native arm64 Python 3.11 and macOS 15 or later.
2. Verifies both locks, the inventory, and direct core/full requirements.
3. Creates the venv and saves the plan, commands, and both lock hashes.
4. Installs the three tools using hashes and wheels. Forced reinstallation is
   limited to that fresh venv, including tools initially supplied by `venv`;
   existing environments are not updated.
5. Installs the runtime with hashes. Only PIMS may use source, with
   `--no-build-isolation` and `--no-cache-dir`: no other build tools are resolved
   and no wheel built by an earlier run is reused.
6. Runs `pip check`, saves the freeze, and requires core/full/teareduce readiness.

Using `--no-build-isolation` requires explicitly supplying build dependencies,
as described in the [pip documentation](https://pip.pypa.io/en/stable/reference/build-system/).
Here the tool lock supplies them inside the new environment; the author's
scientific environment is not used to build PIMS.

The first candidate installation retained pip 24.0 and passed 38/38 smoke cases.
Later review found that `--use-pep517` was no longer in the current pip CLI. The
final design pins pip 26.2.1 and removes that option; current pip uses PEP 517.
Another environment was created to verify this final design. The first
installation and its evidence remain unchanged.

## Scope and limits

The macOS 15 minimum comes from
`debugpy-1.8.21-cp311-cp311-macosx_15_0_universal2.whl`. It applies to this full
resolution; core retains macOS 14. Local execution uses macOS 26.6.2 arm64 and
Python 3.11.15, so it does not yet demonstrate execution on macOS 15, Intel, or
another user's clean Mac.

Input distributions and tools are pinned. A byte-identical PIMS wheel is not
promised: observed builds produce different hashes. Python, the initial pip
provided by `venv`, the SDK, and external applications remain outside the lock.
That initial pip only installs pinned tools; pip 26.2.1 then installs the entire
runtime. Full smoke requires an external LaTeX engine, already present on this Mac.

License metadata needs separate review, including AGPL/commercial declarations
in PyMuPDF, GPL in teareduce and pcodedmp, LGPL in enum-tools/pyxlsb, and MPL in
certifi/fqdn. Successful installation or tests do not establish redistribution
permissions. See [DEPENDENCIES_AND_LICENSES.md](DEPENDENCIES_AND_LICENSES.md).

## Evidence and maintenance

| Final check | Result |
| --- | --- |
| Installation with both locks | Exit 0; no `pip check` conflicts; core/full/teareduce readiness confirmed |
| Installed inventory | 218/218 versions match: 215 runtime and three tools; zero extras |
| Full smoke in the final environment | PASS, 38/38: 36 operations and two expected rejections; no missing core/full coverage |
| Snapshot before/after smoke | PASS, 1,919 entries verified both times |
| Distribution tests | PASS, 43/43, including requirement changes, hashes, additional source, build policy, and tool failure |
| PIMS source altered in a synthetic copy | Hash rejection, exit 1, before build; original downloaded source intact |
| Direct PIMS and dask-image reads | PASS: two 8×8 images with means 17 and 42; identical results and preserved input hashes |

Image reading emits a scikit-image `FutureWarning` for PIMS's plugin parameter.
It remains an upgrade risk; it was neither suppressed nor presented as a
warning-free stack.

Final lock SHA-256 values:

- Runtime: `929f5772e35e721d26887767970e83c5ab77be031c61e0aa5028a52ff2a96870`.
- Tools: `019579e45416357c53ac3cce8b8f092c58c0bda356cc6def7f7b07cb8ff2b541`.

Environments, wheels, downloaded source, and results remain outside Git in
`ScientificWorkbenchRuns/public-full-lock-20260915.wc19ryft/`.
The final installation/tests are under `pip-pinned/`; root-level files retain
the investigation and previous candidate installation.
Within `pip-pinned/`, `install.log`/`install.exit`,
`installed-verification.json`, `distribution-tests.log`,
`tamper-check/verification.json`, and `imaging-probe/verification.json` document
the table. `smoke-full/` retains logs, manifests, outputs, and
`verification.json` for the full profile installed with the final lock.
This batch did not change Swift sources or skills, or repeat historical
packaging/DOCUS gates.

To update the lock, resolve full in another empty environment, download each
exact distribution, verify hashes/provenance, and review platform, license, and
build-tool changes. Update locks and inventory together, run `check_full_lock.py`,
install with hashes into another fresh destination, and repeat full smoke.
Do not regenerate hashes during installation or edit previous reports to hide
divergences. Changed direct requirements invalidate this lock.

CI checks both locks for consistency, but its jobs still install/run core. They
are not evidence of hosted full execution. Real CI, other machines/platforms,
license/privacy/security review, and product criteria in
[PUBLIC_READINESS.md](PUBLIC_READINESS.md) remained pending at the source date.

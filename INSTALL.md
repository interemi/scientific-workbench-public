# Install and use Scientific Workbench

This guide describes a source installation. Core and an earlier Full profile
were installed in new, isolated Python environments on the development Mac,
preserving existing environments. Their synthetic smoke tests passed 23/23 and
38/38 cases respectively. The current Full lock has since replaced PyMuPDF
with pypdfium2: static lock checks and a 38/38 local smoke using an existing
environment passed. On 2026-09-28, commit `b57c168` also passed a fresh hosted
installation of the revised Full lock with focused Core and document tests.
The app has **not been manually tested on another Mac**. That commit passed
hosted macOS 15 Core CI on arm64 and Intel, but automated checks do not test
its user interface. Check the
[current repository's runs](https://github.com/interemi/scientific-workbench-public/actions/workflows/portable-validation.yml)
for the exact commit you use. Core has
a lock for native Python 3.11 on Apple Silicon;
full has a lock with pinned build tools for macOS 15 or later. Intel does not
yet have a validated lock.

Before installing, read [LICENSE](LICENSE) and the
[use limitations](README.md#use-limitations-and-no-warranty). Start with synthetic
data and keep independent backups of important files. This development software
is provided as is, subject to applicable law; it does not guarantee scientific
correctness, data preservation in every circumstance, or suitability for your task.

## 1. Requirements

- macOS 14 or later. Local Full smoke evidence comes from Apple Silicon;
  commit `b57c168` passed hosted Core CI on macOS 15 arm64 and Intel, and a
  focused fresh Full installation on macOS 15 arm64.
- Apple developer tools with Swift 6 or later to build the app.
- Python 3.11 for the scientific backend.
- An Internet connection to download dependencies and, for local AI, the chosen
  model. Cloning the repository does not download models.

Check existing tools:

```bash
xcode-select -p
swift --version
python3.11 --version
```

If Apple developer tools are missing, `xcode-select --install` opens their
installer. If you already use Homebrew, `brew install python@3.11` installs the
required Python branch; see the [official formula](https://formulae.brew.sh/formula/python@3.11).
Homebrew is optional. You may supply a different Python 3.11 interpreter,
including an existing Conda interpreter.

## 2. Obtain the complete source

On the [repository page](https://github.com/interemi/scientific-workbench-public),
choose **Code** to check its HTTPS clone URL. The URL is an argument to
`git clone`; pasting the URL by itself into Terminal does not clone anything.
Clone into a directory where you want to keep the project:

```bash
git clone https://github.com/interemi/scientific-workbench-public.git scientific-workbench
cd scientific-workbench
```

Work from the repository root, which contains `Package.swift`, `script/`, and
`skills/`. If a directory with this name already exists, choose another location
instead of replacing it.

Do not download individual folders: the 480 relative symlinks between scripts,
implementations, and documentation are part of the distribution.

```bash
python3 script/check_distribution_snapshot.py
```

The current backend manifest contains 1,926 entries. If verification fails,
stop and inspect the copy. Do not regenerate the manifest to hide a mismatch.

## 3. Create a new environment

Setup first shows a plan. It installs nothing without `--install`:

```bash
python3 script/setup_environment.py \
  --python python3.11 \
  --profile core --locked \
  --destination "$HOME/Library/Application Support/Scientific Workbench/environments/core/datanalysis"
```

Add `--install` to the same command to execute the installation. `--locked`
requires the 32 reviewed versions and wheel hashes in
`distribution/locks/core-macos-arm64-py311.txt`, including transitive
dependencies. It accepts native arm64 Python 3.11 on macOS 14 or later; the
recorded local run used macOS 26.6.2. Other architectures, incompatible wheels,
and hash mismatches are rejected without resolving alternative versions.

On Intel, omit `--locked`. This resolves currently available dependencies and
is not a pinned environment. The public macOS 15 Intel Core job passed on
`b57c168`, but that does not establish a repeatable Intel lock, full-profile
coverage, or manual app use on another Mac. Check exact-commit CI.
The core lock covers the Python runtime packages, excluding the interpreter,
bootstrap pip/setuptools, Apple tools, and external applications. See
[portable validation](docs/PORTABLE_VALIDATION.md) for its limits.

Packages are downloaded into the new environment. The final directory must be
named `datanalysis` to support skill environment discovery. Setup rejects an
existing destination and retains the package inventory and diagnostics in
`scientific-workbench-setup/` inside the environment.

Setup ignores inherited pip configuration and environment variables to prevent
redirection outside the environment. It requires a virtual environment and
checks the scientific core with `--strict-core` before reporting success.
Full additionally requires `full_ready`; TEAREDUCE is an optional external
notebook backend and is not installed by Full. A working core
alone does not establish a working full installation. If your network needs a
private package index or special pip settings, review that requirement before
adapting setup. The installer also runs `pip check` and preserves the plan and
selected lock's hash.

For Python extensions on Apple Silicon with macOS 15 or later, use another new
destination:

```bash
python3 script/setup_environment.py \
  --python python3.11 --profile full --locked \
  --destination "$HOME/Library/Application Support/Scientific Workbench/environments/full/datanalysis"
```

Add `--install` to execute the plan. The full lock pins 200 runtime packages and
three installation/build tools. PIMS 0.7 is built from its verified source
archive using pinned pip/setuptools/wheel inside the new environment, without
implicit build-dependency downloads. The macOS 15 minimum comes from the
selected debugpy wheel; core retains its macOS 14 minimum.

The optional manual [GitHub Actions Full job](https://github.com/interemi/scientific-workbench-public/actions/runs/36437566460)
installed this revised lock from scratch on hosted macOS 15 arm64 for commit
`b57c168`. It passed 23/23 Core synthetic cases and 39/39 document tests in
the new environment, not the entire 38-case Full smoke: the latter also
requires an external LaTeX engine. See
[portable validation](docs/PORTABLE_VALIDATION.md) for the exact CI scope.

Full does not install external applications such as LaTeX, LibreOffice, or IRAF.
It does download the three OCR ONNX models included in the RapidOCR wheel.
These are separate from Ollama models and stay inside the Python environment.
On Intel or macOS 14, full without `--locked` remains an experimental, unpinned
resolution. See the [full-lock evidence and limits](docs/PUBLIC_FULL_LOCK_2026-09-15.en.md).

If installation stops, its directory is preserved for diagnosis. Inspect the
error and choose another new destination for a retry. Do not run legacy Conda
installers against an environment you need to preserve: some use
`conda env update --prune`.

## 4. Build the app

To check compilation without opening the interface:

```bash
swift build
```

To create and open the development bundle:

```bash
./script/build_and_run.sh --build
open "dist/Scientific Workbench.app"
```

The bundle script closes running Scientific Workbench instances and recreates
the app inside this checkout's `dist/`. Save active work before running it.
The result uses ad hoc signing for local development; it is not a notarized
public installer. Open this copy from `dist/` before replacing any installed
app you wish to preserve.

On the maintainer's macOS 27.0.1 with Command Line Tools Swift 6.4, plain
`swift build` failed before source compilation. A scoped build using an older
SDK already present on that Mac succeeded:

```bash
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  swift build --build-system native
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
  SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM=native \
  ./script/build_and_run.sh --build
```

Check that this SDK path exists before using these commands. This is a
workaround for the observed toolchain combination, not evidence of a fresh
installation on macOS 27 or a general requirement to install an older SDK.

## 5. Configure the first launch

In Settings, configure:

| Field | Value |
| --- | --- |
| Mother skill root | Absolute path to this checkout's `skills/scientific-data-analysis` |
| Python | Absolute path to `datanalysis/bin/python` in the new environment |
| Output folder | A new results directory separate from original data |
| Local AI | Ollama and an available model, if you want local planning/conversation |

The other four skills are discovered as siblings of the mother root. Keep the
checkout at that location, or update Mother skill root in Settings after moving
it. You do not need to overwrite skills installed by another tool.

After entering the three paths, choose **Save Settings**, then **Reload Registry**
and **Refresh Environment** in Settings. Check that the setup checklist reports
the scientific environment, capabilities, and output folder
ready before running an example. Saving a new mother skill root does not
reload capabilities already held by the current app session; without the
reload, a run may still use scripts from the previously selected skill family.

For Ollama, follow the [official macOS instructions](https://docs.ollama.com/macos).
Open Ollama and use the app's settings to select and download a model suitable
for your available memory and storage. Weights stay outside Git. OpenAI, Grok,
and Gemini are optional and may incur charges; credentials and consent are
configured locally. **Test Connection** for a cloud provider sends a real
fixed-prompt API request and may consume quota or incur a charge. Follow the
[selective setup steps](docs/OPTIONAL_BACKENDS.md#local-ai-and-optional-cloud-providers)
before enabling any provider; none is required for local capability commands.

## 6. Verify using synthetic data

First verify the backend without opening the app, using the new environment:

```bash
"$HOME/Library/Application Support/Scientific Workbench/environments/core/datanalysis/bin/python" \
  script/run_portable_core.py \
  --output-dir "$HOME/ScientificWorkbenchRuns/core-check-01"
```

The output directory must be new and outside the checkout. The command runs
strict diagnostics and synthetic core workflows, checking snapshot hashes
before and after. It preserves logs, a manifest, and `verification.json`.
On failure, preserve the directory and inspect its logs before retrying with
another name. A backend PASS does not establish that the following UI journey
works.

To check full, use its environment's Python and add `--profile full`:

```bash
"$HOME/Library/Application Support/Scientific Workbench/environments/full/datanalysis/bin/python" \
  script/run_portable_core.py --profile full \
  --output-dir "$HOME/ScientificWorkbenchRuns/full-check-01"
```

The script name is retained for compatibility. Full executes notebooks on
copies and compiles a LaTeX document, requiring an external `latexmk` or
`pdflatex` executable. Python setup does not install that engine. Missing
external tools may fail this smoke even when Python package diagnostics pass;
preserve the failure for diagnosis.

For a first app run that does not need Ollama or a cloud account:

1. Check the Setup Checklist: scientific environment, capabilities, and output
   folder. Keep the output folder separate from the checkout and original data.
2. On **Dashboard**, find **Try a synthetic example** and choose **Prepare** beside
   **Small table**. The app creates a new local synthetic copy, selects it as
   input, and opens the `profile_table` capability under **Normal**. It does
   not edit the bundled example or another input you previously selected.
3. Read the **Synthetic example ready** panel, then check the selected input
   and output folder. Leave the advanced argument override empty.
4. Choose **Run Capability**.
   Direct capability runs execute when clicked. For a Chat-generated multi-step
   plan, use **Dry Run** to inspect its commands before **Run Enabled**.
5. Open **Jobs** and **Results**. Inspect the status, executed command,
   `summary.json`, and `manifest.json` in the new run folder. The fixture's
   expected summary is `app_status: PASS`, `rows: 3`, `columns: 4`, and
   `original_modified: false`. A different result needs diagnosis, not a
   rewritten fixture.
6. To repeat safely, return to **Dashboard** and choose **Reset Example (New Copy)**.
   This preserves the first copy and its result. The other four examples,
   expected values, and scientific limits are in the
   [first-run example guide](docs/SYNTHETIC_FIRST_RUN_EXAMPLES.md).

On 27 September 2026, an isolated GUI session on the development Mac followed
the **earlier manual path**, selecting the bundled `ops.csv` through **Add
Files**. Jobs showed a successful run; Results displayed the summary and
manifest with expected values and the input SHA-256 unchanged. That Mac
already had a scientific Python environment. The new **Dashboard** example launcher
was subsequently exercised on 30 September 2026 on the same Mac: five
examples were prepared, six GUI jobs passed, and the generated input hashes
remained unchanged. That newer GUI session used the locally installed skill
family; separate backend probes used the bundled skills from this checkout.
Neither session was a fresh installation or an independent trial on another
Mac. The
[capability matrix](docs/CAPABILITY_SETUP_MATRIX.md) includes a
standalone CLI version of this example if you want to test the backend
independently.

Record the journey with the [acceptance form](docs/CLEAN_INSTALL_ACCEPTANCE.md).
Preserve warnings and missing-backend findings as such. Do not use DOCUS or
other original data to validate a new installation.

## Common problems

- **Catalog missing:** check the mother root and its four siblings, then rerun
  snapshot verification.
- **Missing libraries:** check the Python selected in Settings. System Python
  may differ from the prepared environment.
- **Ollama unavailable:** open Ollama and check the model and local endpoint.
- **Missing LaTeX, Office, or another backend:** inspect workflow diagnostics,
  install only the required component, and check readiness again.
- **Swift Testing fails with Apple developer tools:** use
  `./script/run_swift_tests.sh`, which includes the project's test runner.
- **Swift build fails before source compilation on macOS 27:** see the scoped
  SDK workaround in [Build the app](#4-build-the-app). Record the exact macOS,
  Swift, and SDK versions if it does not apply.

See [what the skills and capabilities do](docs/SKILLS_AND_CAPABILITIES.md),
then use the [55-capability setup matrix](docs/CAPABILITY_SETUP_MATRIX.md) to choose
one route and its first safe input. Use [optional backends](docs/OPTIONAL_BACKENDS.md)
for only the extra tools it needs, [workflow requirements](docs/WORKFLOW_REQUIREMENTS.md)
for dependency classes, and [troubleshooting](docs/TROUBLESHOOTING.md) for
diagnosis.

Do not disable Gatekeeper, delete original inputs, or reuse historical evidence
directories to resolve an installation failure.

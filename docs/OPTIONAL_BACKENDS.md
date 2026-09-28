# Optional backends: install only what your workflow needs

Scientific Workbench runs its app and bundled scientific skills from the source
checkout. [INSTALL.md](../INSTALL.md) prepares the Python Core or Full profile;
it does **not** install the applications, Java tools, model weights, accounts,
or legacy research trees below. First choose one of the
[55 capabilities](CAPABILITY_SETUP_MATRIX.md), then prepare only its named
backend. A missing optional backend should produce a warning or controlled
block, not a successful scientific result.

Every external tool, Python dependency, service, and model remains the work of
its own author or publisher, under its own license and use terms. The upstream
links in each section identify where to check those terms and obtain the tool;
the [ownership and attribution map](DEPENDENCIES_AND_LICENSES.md#ownership-and-attribution-map)
explains what Scientific Workbench licenses itself. A link or acknowledgment
does not mean that Scientific Workbench owns or redistributes the external work.

These instructions describe the source tree reviewed on 25 September 2026.
External sites and system requirements can change. Their install links below
are upstream documentation; the commands shown here check or use the Scientific
Workbench interface. We have not installed and run every optional backend on a
second Mac. Record the tool version, selected Python, input hashes, and a new
output directory with each real run. Never test with an irreplaceable original.

## Local AI and optional cloud providers

Ollama is optional for conversation and AI planning. Scientific Workbench can
run local capability commands and use its deterministic planner without any
model or cloud account.

1. Follow the [official Ollama macOS installation guide](https://docs.ollama.com/macos)
   and open Ollama once. In Terminal, check `ollama --version` and `ollama ls`.
2. In **Settings > Local AI Setup**, select a model. The app's default is
   [`qwen3:4b-instruct`](https://ollama.com/library/qwen3:4b-instruct); the
   compact, stronger, and custom choices are optional. Review each model's
   license, memory, and disk requirements before downloading it.
3. Click **Check**. If the selected model is absent, click **Download Selected
   Model**, or use `ollama pull qwen3:4b-instruct` for the default model. This
   downloads weights outside Git. Check again and click **Test Local AI**;
   that test sends a fixed prompt to the local server. The selected model name
   must match an installed model. The default endpoint is
   `http://localhost:11434`; the app accepts only HTTP(S) loopback endpoints.

Cloud APIs are separate, optional accounts. The app does not supply keys or
pay usage fees. [OpenAI API billing](https://help.openai.com/en/articles/9039756)
is separate from a ChatGPT subscription. Check the provider's current model
availability, prices, quotas, and data-handling terms before enabling a route:

| Provider | Create an API key | Check models and cost |
| --- | --- | --- |
| OpenAI | [API quickstart](https://platform.openai.com/docs/quickstart) | [Model catalog](https://developers.openai.com/api/docs/models) and [pricing](https://developers.openai.com/api/docs/pricing) |
| Grok/xAI | [API quickstart](https://docs.x.ai/developers/quickstart) | [Pricing and model availability](https://docs.x.ai/developers/pricing) |
| Gemini | [Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key) in Google AI Studio; the app uses an API key, not OAuth | [Models](https://ai.google.dev/gemini-api/docs/models) and [pricing](https://ai.google.dev/gemini-api/docs/pricing) |

For a fresh app configuration, the suggested Gemini model is now
`gemini-3.5-flash-lite`, listed as stable in the current model catalog. Earlier
saved choices are **not** changed. In particular, a saved `gemini-2.5-pro`
selection can remain in Settings even though Google's catalog currently limits
2.5 model access for new projects. The built-in OpenAI and xAI suggestions are
`gpt-5.2` and `grok-4.3`; access still depends on the account. Use the exact
model ID available to **your** key rather than assuming any suggestion works.
For Gemini 3 models, the app leaves sampling temperature at the provider
default, as Google currently recommends. Its connection probe allows up to
512 output tokens because the limit also counts thinking tokens; the probe
still sends only a fixed, short prompt.

For one chosen provider, create a key in its own account. In **Settings > AI
Connections**, select that provider, enter its key and an available model ID,
choose **Cloud attachment context**, then click **Save Connections**. The
app stores keys in macOS Keychain; exported app configuration excludes them.
The save status appears below the button. Only keys you edited are written;
an error names the provider without showing the key. Retry **Save Connections**
before closing the app if a Keychain write fails. **Test Connection** checks
the current session's key but does not save it.
The default attachment mode sends file or folder names only. Select **No
attachment context** if even names should stay local; the current message
and any displayed conversation context still need separate review.

**Test Connection** makes a real HTTPS generation request with a fixed test
prompt, the selected model, and your key. It does not include user attachments
or conversation history, but it can consume quota or incur a charge. The result
is valid only for the current app session. If it reports **model unavailable**,
choose a model your account can access in Settings and test again; the app does
not silently switch providers or models. Actual cloud chat and workflow
planning present an outbound-data review before sending; the default approval
covers only that request. Do not put API keys in Git, a copied command, an
issue, or a support log. We have not tested these paid providers with real keys
for this public-source candidate. Web Astrometry.net solving is a separate
upload/API choice described below.

## LaTeX

`latex_workbench.scaffold` and `.review` do not need a TeX engine.
`latex_workbench.compile` needs `latexmk` or `pdflatex` on the Mac. The
[MacTeX download](https://tug.org/mactex/mactex-download.html) supplies a TeX
Live distribution; it is large and installed separately. After installing,
open a new Terminal and check:

```bash
command -v latexmk || command -v pdflatex
```

At least one executable must be found. Run `latexmk -v` if that was found, or
`pdflatex -version` if it was not. The compile command detects `latexmk` first
and falls back to `pdflatex`. Tectonic alone is not supported by this command.
Use a new or copied `.tex` project and an output directory outside it;
the compiler runs on another working copy. A test of the fallback uses a mocked
compiler, while the dated Full smoke included a real PDF compile on the
maintainer's Mac. Neither establishes a TeX install on another Mac.

## Java, STILTS/TOPCAT, and APT

For large catalogue and VO workflows, obtain STILTS or TOPCAT from the
[Starlink STILTS project](https://www.starlink.ac.uk/stilts/) and follow its
[command-line documentation](https://www.starlink.ac.uk/star/starjava/docs/topcat/sun253/topcatArgs.html).
Scientific Workbench accepts an executable command, a `stilts.jar`, or TOPCAT
in `-stilts` mode. Java is required for the JAR route. Check `java -version`,
then run this non-executing discovery check from the checkout root, replacing
the example JAR path with the one you installed:

```bash
python3 skills/scientific-data-astro/scripts/external_astro_tools_preflight.py \
  --require-stilts --stilts-jar "/absolute/path/to/stilts.jar"
```

On a Mac without another STILTS provider, the missing placeholder JAR above
produces exit code 2 and `status: blocked` /
`app_status: BLOCKED_CONTROLADO`. That is the
expected controlled block for a missing optional backend, not a successful
STILTS run. Configure the real JAR or command and repeat the preflight. Do not
replace it with a Python crossmatch silently; the native
`catalog_workbench.crossmatch-sky` route is a separately reviewed choice for
small or medium catalogues. The TOPCAT GUI is not driven automatically.

For Aperture Photometry Tool, download the macOS package from the
[APT project](https://aperturephotometry.org/downloads/) and follow its
[installation instructions](https://aperturephotometry.org/installation-execution/).
The app's wrapper needs Java, an `APT.csh`/equivalent command, and a saved
`APT.pref` for batch mode. Create that preferences file through the APT GUI
and review coordinate and aperture settings. Then use **Settings > Optional
Astronomy Backends > Run APT Preflight**, or from the checkout root:

```bash
python3 skills/scientific-data-astro/scripts/external_astro_tools_preflight.py \
  --require-apt --apt-command "/absolute/path/to/APT.csh" \
  --apt-preferences "/absolute/path/to/APT.pref"
```

On a Mac without APT configured, the missing placeholder command and
preferences paths likewise produce exit code 2 and `BLOCKED_CONTROLADO`,
naming both missing items.
It checks discovery and saved preferences; it does not establish correct
photometry. APT is different from the Hubble proposal tool of the
same abbreviation. If the external program is unavailable, use the separate
Python/photutils aperture-photometry route when its method fits your task.

## Astrometry.net

Existing celestial WCS can be verified without a solver or network service.
For a new local solve, follow the [Astrometry.net installation guide](https://astrometry.net/doc/readme.html)
and obtain only the [index files](https://astrometry.net/doc/readme.html#getting-index-files)
appropriate for your field scale. Check `command -v solve-field` and review the
solver's index configuration. `astrometry_net_workbench.py preflight` accepts a
copied FITS/image and reports hints without solving. Local execution needs
`solve-field` and suitable index files; a successful preflight alone is not a
solution.

The `solve-web` route sends a copied image to Astrometry.net. It requires an
API key and explicit review of upload, visibility, privacy, network access,
and service terms. The command defaults `--publicly-visible n`, but you must
still decide whether transmitting the input is appropriate. Store the key
outside Git; never add it to a manifest or public issue. Online availability
and service behavior are not controlled by Scientific Workbench.

## Legacy spectroscopy: IRAF and iSTARMOD

The [IRAF Community installation guide](https://iraf-community.github.io/install.html)
describes macOS packages and a Homebrew tap. It may also need XQuartz for
X11 tools. Check `command -v cl` and `command -v mkiraf` before the
`legacy_spectroscopy_envcheck` preflight. `fxcor_iraf_workbench.prepare-session`
creates a separate ASCII-safe coursework copy; run IRAF only there. No IRAF
installation or real fxcor result was established by hosted Core CI.

`istarmod_workbench` is a **legacy tree adapter**, not an installer of
[upstream iSTARMOD](https://github.com/flabarga/iSTARMOD). Its inspection
expects a tree with root-level `.sm` files, `lambdas.dat`, and `iStarmod.py`.
The current upstream repository presents a different layout and its own
GPL-3.0 license. Do not assume that cloning the current upstream release
makes `run-sm` usable; compatibility has not been demonstrated. You may run
`istarmod_workbench.py inspect-tree` on a *copy* of a tree you are entitled to
use. `prepare-copy` creates another new tree; only a reviewed prepared copy
may be passed to `run-sm`. The latter can archive or wipe cache files **inside
that copy**, so inspect the plan and never point it at an original tree.

## TEAREDUCE, documents, and macOS apps

Full includes OCR/document extras and the notebook launcher, but does **not**
install TEAREDUCE. `teareduce_healthcheck.py --concise` checks only the Python
interpreter running the healthcheck, using package metadata without importing
TEAREDUCE. It cannot check a different Jupyter kernel. The legacy-named
`teareduce_bridge` uses native NumPy and Matplotlib for numerical summaries
and FITS quicklooks; those outputs are not TEAREDUCE results.

For an optional TEAREDUCE notebook, first obtain and install the external
package under its own terms in a **separate** user-managed Python environment,
following [its upstream project](https://github.com/nicocardiel/teareduce).
That environment needs `ipykernel`. Inspect existing kernels with
`jupyter kernelspec list`; choose a unique name, since registering an existing
name overwrites its kernelspec. Register the kernel from that environment:

```bash
/path/to/external-env/bin/python -m ipykernel install --user \
  --name scientific-workbench-teareduce-external \
  --display-name "TEAREDUCE (external)"
```

The [IPython kernel guide](https://ipython.readthedocs.io/en/stable/install/kernel_install.html)
explains cross-environment kernels. With Full as the **launcher** Python,
run a reviewed notebook with paths chosen for your machine:

```bash
/path/to/full/datanalysis/bin/python \
  skills/scientific-data-astro/scripts/teareduce_notebook_runner.py \
  /path/to/reviewed-notebook.ipynb \
  --kernel-name scientific-workbench-teareduce-external \
  --output-dir /path/to/new-run-directory \
  --trust-notebook-code
```

Use `--stage-extra /path/to/input-copy` for required sidecars. The output
directory must be new, and the notebook must be reviewed because its code can
perform arbitrary file or network operations. The runner reports success or
cell errors from the selected kernel; its `teareduce` package-discovery field
still describes only the launcher. A registered kernel, a package name, or a
successful run does not verify TEAREDUCE API compatibility, the notebook's
scientific result, or license compatibility. A synthetic notebook ran on
27 September 2026 in a distinct, already installed Python kernel. It produced
an executed copy; the source notebook retained no outputs. That kernel did
**not** contain TEAREDUCE. Real TEAREDUCE notebook execution and scientific
comparison remain untested on this source tree. See the
[license review](DEPENDENCIES_AND_LICENSES.md).
The upstream [cookbook introduction](https://github.com/nicocardiel/teareduce-cookbook/blob/ba360766c98579d9a177223750507774ad2fc038/intro.md)
asks users of TEAREDUCE to cite the
[TEAREDUCE paper](https://arxiv.org/abs/2601.20914). This scholarly citation
does not replace its GPL terms or resolve our integration review.

[LibreOffice](https://www.libreoffice.org/download/) can provide copied Office
document export on macOS. Check its installed CLI with
`/Applications/LibreOffice.app/Contents/MacOS/soffice --version` if that app
exists. [Keynote](https://support.apple.com/guide/keynote/welcome/mac) and
iWork are Apple applications, installed separately. Keynote export is a
GUI/Apple Events route that must be explicitly confirmed on a copied deck;
its preflight reports whether the app and automation path are available.
Quick Look is a macOS service, not a Python package. Use a synthetic or copied
document and inspect the exported preview; visual fidelity still needs review.

Full includes RapidOCR and pypdfium2 for PDF recovery, rendering, and preview,
but it does not make every OCR format or model scientifically reliable. The
PDF backend replacement and the remaining third-party terms are tracked in
[dependencies and licenses](DEPENDENCIES_AND_LICENSES.md).
Legacy `.xls` inspection reports streams and metadata, but marks VBA assessment
`not_assessed`; do not interpret a missing `has_vba` value as a macro-free file.
Embedded-image extraction can omit separately stored transparency masks;
visually compare recovered figures with the source PDF before using them.
Do not install a separate OCR service or bypass a missing-backend block just
to make an unrelated capability appear ready.

## Additional document and notebook format helpers

`document_semantics.py` first uses its own readers or macOS `textutil` for
supported files. [Pandoc](https://pandoc.org/installing.html) is an **optional
fallback** for some HTML, legacy Word/RTF, DOCX, and OpenDocument inputs when
an earlier extraction route fails. It is not needed for the normal
DOCX inventory or for Core installation. If you already use Homebrew, its
optional install command is `brew install pandoc`; otherwise use the upstream
macOS installer. Check `command -v pandoc` and `pandoc --version` before a
copied-file trial. Record which extraction method the result actually reports;
installing Pandoc does not guarantee that a damaged document becomes readable.

Scientific Workbench's own PDF paths use pypdfium2, not Poppler. A **user
notebook** that imports `pdf2image` is different: `notebook_workbench.py`
preflight checks its Python import and looks for `pdftoppm` or `pdftocairo`.
Those executables come with [Poppler](https://formulae.brew.sh/formula/poppler),
which can optionally be installed with `brew install poppler` if Homebrew is
already available. Check `command -v pdftoppm || command -v pdftocairo`, then
run the notebook preflight on a copy. The reviewed Full lock does **not** pin
`pdf2image`; a notebook that needs it requires a separately reviewed Python
dependency plan in a new environment. Do not modify a validated research
environment just to satisfy an arbitrary notebook import. Pandoc, Poppler,
and any notebook-specific package retain their own licenses and are not
bundled in this source repository.

For each route, the app's **Environment** view and the capability's own
preflight are more useful than an installed-file check alone. Preserve a failed
preflight and retry in a new run directory after correcting its named cause.
See [Troubleshooting](TROUBLESHOOTING.md) for the status and recovery flow.

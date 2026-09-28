# TEAREDUCE: optional external notebook route

TEAREDUCE is a third-party astronomy package by Nicolás Cardiel. Its
[upstream package metadata](https://github.com/nicocardiel/teareduce/blob/ac508421ef6c1b1af03b221a2a686a7ffe3960f2/pyproject.toml)
declares GPL-3.0-or-later. Scientific Workbench does not own or bundle its
source, and the Full profile does not install it. Review the upstream terms
before obtaining it. Acknowledgment is not permission to relicense it.

Choose this route only when the user explicitly requests TEAREDUCE or needs to
reproduce a reviewed TEAREDUCE notebook. For ordinary FITS inspection,
photometry, or spectroscopy, first consider the appropriate native capability
and record why its method fits. The legacy-named `teareduce_bridge.py` produces
native NumPy/Matplotlib summaries and quicklooks; it does not execute or
reproduce TEAREDUCE.

`scripts/teareduce_healthcheck.py` discovers installed package metadata and
the module path in its **launcher Python**, without importing TEAREDUCE. It
cannot inspect a different Jupyter kernel or verify an API or scientific
result. `scripts/teareduce_notebook_runner.py` can execute a user-provided,
reviewed notebook in a copied workspace using a separately installed kernel.
Read the [practical guide](teareduce-practical-guide.md) for the safe setup and
the [workflow notes](teareduce-canonical-workflows.md) for the limits of the
older case families. The general installation and license boundaries are in
the repository's `docs/OPTIONAL_BACKENDS.md` and
`docs/DEPENDENCIES_AND_LICENSES.md`.

The files under `.cache/archived_references/` preserve earlier guidance as
history. They describe an older integrated environment and are **not** current
installation or validation instructions. A separate-kernel synthetic notebook
probe passed on 27 September 2026, but that kernel did not contain TEAREDUCE.
Real TEAREDUCE notebook execution, API compatibility, and scientific agreement
remain unverified for this source tree.

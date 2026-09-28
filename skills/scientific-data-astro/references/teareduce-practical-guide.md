# Practical TEAREDUCE route

Use this optional route only for a notebook whose TEAREDUCE dependency and
scientific method you have reviewed. Scientific Workbench's Full Python profile
is the **launcher** and does not install TEAREDUCE. Obtain the package from the
[upstream project](https://github.com/nicocardiel/teareduce) under its own
license in a separate, user-managed Python environment with `ipykernel`.
Review the package version and dependencies before installation.

1. Inspect existing Jupyter kernel names with `jupyter kernelspec list`. Choose
   a new, unique name: registering an existing name can replace its kernelspec.
2. Register the separate environment's Python as that kernel, following the
   [IPython kernel guide](https://ipython.readthedocs.io/en/stable/install/kernel_install.html):

   ```bash
   /path/to/external-env/bin/python -m ipykernel install --user \
     --name scientific-workbench-teareduce-external \
     --display-name "TEAREDUCE (external)"
   ```

3. From the Scientific Workbench checkout, use the **Full launcher Python** to
   execute one trusted notebook in a new output directory:

   ```bash
   /path/to/full/datanalysis/bin/python \
     skills/scientific-data-astro/scripts/teareduce_notebook_runner.py \
     /path/to/reviewed-notebook.ipynb \
     --kernel-name scientific-workbench-teareduce-external \
     --output-dir /path/to/new-run-directory \
     --trust-notebook-code
   ```

   Add `--stage-extra /path/to/input-copy` for each required sidecar or input
   tree. The output directory must be absent or empty. Keep irreplaceable
   originals outside the notebook's writable workspace.

4. Inspect the executed notebook copy, summary, manifest, input hashes,
   selected kernel, cell errors, output units, and scientific comparison. Do
   not label a run scientifically valid just because its process exited zero.

The trust flag is an explicit assertion that you inspected the notebook code:
the selected kernel executes arbitrary Python and may access files or the
network. The runner stages copies of detected inputs and requested sidecars,
but it cannot make arbitrary notebook code harmless. Its package-discovery
field describes the launcher, **not** the selected kernel. A registered kernel
alone is not evidence that TEAREDUCE is installed or compatible there.

The 27 September 2026 separate-kernel probe executed only a synthetic notebook
in another existing Python and preserved its source by SHA-256. That kernel
did not have TEAREDUCE. No real TEAREDUCE notebook or scientific output has
been validated on the current tree. See `docs/OPTIONAL_BACKENDS.md` for the
public setup scope and `docs/DEPENDENCIES_AND_LICENSES.md` for the license
review. The older `.cache/archived_references/` guides are historical.

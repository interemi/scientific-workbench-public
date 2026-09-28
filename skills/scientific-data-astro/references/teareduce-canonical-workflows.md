# TEAREDUCE notebook families and evidence limits

Earlier Scientific Workbench guidance grouped TEAREDUCE notebooks into four
case families: master bias, flat field, cookbook `cr2images`, and cookbook
`wavecalib`. They remain useful descriptions of potential user-provided
notebooks; they are **not** four passing tests of the current public source
tree. No official cookbook notebooks or data trees are bundled here. Do not
fetch a practice tree or scan a broad local directory merely to obtain a
nominal smoke result.

| Family | Question to verify on a reviewed copy |
| --- | --- |
| Master bias | Are selected bias frames, rejection choices, corrected frames, units, and output provenance appropriate? |
| Flat field | Are filter-specific input sets, master flats, normalization, and propagated uncertainties scientifically justified? |
| `cr2images` | Do the input images and cosmic-ray parameters support the corrected products without erasing real sources? |
| `wavecalib` | Do identified lines, fit residuals, wavelength units, and calibration direction support the resulting axis? |

The repository retains specialized `teareduce_*_workflow.py` helpers, but
their names and presence are not evidence that the current external
TEAREDUCE package, a notebook, or a dataset will work. Use the
[practical guide](teareduce-practical-guide.md) for the separate-kernel path.
Choose a single, trusted notebook and new output directory; compare any
derived FITS products with explicit scientific tolerances and record the
external package/kernel version. Report a missing package, sidecar, or dataset
as a dependency block rather than a successful result.

The four-case smoke claim in `.cache/archived_references/` belongs to an
earlier environment and must not be transferred to the current source tree.
The only current cross-kernel execution evidence is a synthetic notebook run
on 27 September 2026 in a kernel without TEAREDUCE. Real external-package API
and scientific agreement remain untested.

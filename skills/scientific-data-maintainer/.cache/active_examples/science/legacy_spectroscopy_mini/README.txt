# Legacy Spectroscopy Mini Example

English publication edition of the preserved private README at d6583f1.
Original SHA-256:
6f362c240fe236faafd38b2cfd7110b0df7dd3ee4e3f99f524ff70b13fe66bff
The same original appears in the analysis, astro, and maintainer example roots;
distribution/public-documentation-map.json records each exact source path.
Originals and scientific fixture bytes remain unchanged privately.

A small bundled example for validating the legacy spectroscopy route without
using real coursework data.

Contents:

- mini_multispec.fits: synthetic FITS with MULTISPE/WAT* headers and two orders.
- sample_fxcor_rows.csv: a small example of rows already parsed from fxcor
  txtonly output.
- sample_case.sm: a minimal iSTARMOD-style configuration for routing tests and
  documentation.

Purpose:

- Check that echelle_multispec_inventory.py recognizes a small MULTISPE file.
- Provide a reference CSV for lightweight RV / v sin i analysis tests.
- Provide a portable .sm file for documentary inspection and packaging tests.

Notes:

- Contains no real scientific data.
- Does not replace validation against the actual coursework case.
- Names and magnitudes are deliberately synthetic.

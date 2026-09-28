scientific-data-astro

Staged child skill for FITS, WCS, photometry, spectroscopy, radial velocity, RGB FITS, optional astronomy backends, TEAREDUCE, and legacy coursework routes.

The supported public entrypoint remains scientific-data-analysis. This child exists so the mother router can delegate heavy astro workflows without loading the full megaskill for unrelated tasks.

v2.5 note: public astro scripts are thin entrypoints that dispatch to same-named fixtures for budget deferral. Dependency shims such as LaTeX and notebook handoffs still forward to their dedicated child skills.

# astronomy-fits.md

This mother-skill reference is intentionally compact in v2.5.

Full operational guidance now belongs to `scientific-data-astro` at `references/astronomy-fits.md`.

Scope: FITS inspection, WCS, headers, photometry and astronomy-specific image routing.

Use the mother skill as the router, then load the child skill when this domain is actually needed. This preserves usability while keeping the always-installed mother skill inside the plugin-eval deferred-budget envelope.

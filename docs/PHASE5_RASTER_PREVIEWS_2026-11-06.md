# Raster preview memory and responsiveness

Measured on the project Mac (Apple silicon, 16 GiB, macOS 27.0.1,
Swift 6.4 and macOS SDK 26.5), starting from `9552319`. This verifies
PERF.06 for the supported in-app raster and generated FITS quicklook
paths and moves raster decoding off the UI thread for PERF.02.

## Display policy

Results and artifact comparisons load PNG, JPEG and TIFF previews one
at a time off the main actor. The loader checks that the resolved file
is a regular file inside the recorded run folder. ImageIO returns a
decoded thumbnail with a maximum dimension of 1,600 pixels and applies
the image's orientation. The view receives the thumbnail directly.
[Apple ImageIO thumbnail options](https://developer.apple.com/documentation/imageio/kcgimagesourcecreatethumbnailwithtransform)

The preview declines sources above 256 MiB, 16,384 pixels on either
axis, or 100 million pixels in total. These are input and display
limits. Temporary decoder memory still depends on the format and
image contents. The original file remains available through Reveal,
and reduced previews identify their dimensions and display-only role.
Raw FITS continues to use a generated quicklook when available.

Selection changes cancel pending preview tasks. A decoder already
inside ImageIO may finish, and the canceled result is discarded.
The view associates the displayed result with both the job and the
artifact. PDF and text keep their existing preview behavior.

## Measured trade-offs

A component probe drew three encodings of the same synthetic
8,192 × 8,192 pattern into a 1,280 × 1,280 Core Graphics context.
It compared the previous loader and NSImage construction with the
new loader and direct thumbnail wrapping. Five fresh processes per
format and mode alternated order. Peak resident size is the whole
probe process as reported by macOS `getrusage`.

| Format | Previous peak (MiB) | Direct peak (MiB) | Previous time (ms) | Direct time (ms) |
| --- | ---: | ---: | ---: | ---: |
| PNG | 289.4 | 65.0 | 339.1 | 489.8 |
| TIFF | 288.0 | 53.6 | 179.5 | 211.3 |
| JPEG | 52.5 | 59.1 | 108.1 | 139.9 |

The values are medians. The display sample pixel matched within each
format. PNG and TIFF used substantially less memory with a longer
preparation time. JPEG used slightly more memory and time in this
sample. It still follows the same bounded display policy.

A separate app check used two isolated bundles and the same synthetic
PNG. `vmmap` reported peak physical footprint of 337.5M on the previous
build and 123.8M on the new one, with Chat baselines of 96.9M and 95.0M.
There was one app observation per build. This is a different memory
metric from the component probe and does not characterize other images.

## Verification

- Swift passed 384 tests. Raster regressions cover a downsampled EXIF
  rotation with colored orientation markers, oversized and corrupt
  input, out-of-run access and cancellation.
- In Results, PNG and TIFF displayed a 1,600-pixel preview. Corrupt
  and oversized files showed distinct errors. A rapid PNG-to-CSV
  switch ended with the correct CSV row. Comparison showed the CSV
  and TIFF together.
- The scientific known-answer check passed for FITS/WCS and sky
  crossmatch. The loader opened its generated 1,120 × 960 PNG and
  preserved the FITS and PNG hashes. Scientific values and units
  come from the data and run evidence.
- All nine GUI fixture files, the original probe fixtures and the
  22 ordinary app-state files matched their pre-test hashes. Ordinary
  app preferences also matched.

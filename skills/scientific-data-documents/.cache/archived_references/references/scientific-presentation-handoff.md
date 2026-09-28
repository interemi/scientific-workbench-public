# Scientific Presentation Handoff

Use this when scientific notebook outputs need to become an editable Keynote or PowerPoint deliverable based on an existing deck. The main risks are losing editability by flattening slides into screenshots, drifting away from the group's reference layout, and letting speaker-only detail leak into slide content.

## Core Rule

Only scientific figures should be images. Titles, captions, arrows, circles, labels, legends added for explanation, callouts, and slide text should remain editable whenever the user needs to keep working on the deck. Treat this as `editable-native-first`.

## Exact Figure Handoff

When the user asks for an "exact equivalent", do not generate by filename or rough visual similarity alone. Route through `references/coursework-figure-equivalents.md` and confirm the figure's intent, source product, notebook/cell/function, FITS or RGB input, scale, crop, overlays, and target slide position before rebuilding the asset.

Useful distinctions:

- detected sources and SDSS calibrators are overlays/evidence, not interchangeable with reduced-image views;
- a viridis diagnostic is not a final RGB product;
- a diagnostic crop is an extra explanation asset, not a replacement for the full figure;
- "same figure in another object/year/filter" means same visual recipe and scientific purpose, not just a similar name.

If the user corrects the result with "eso no es", "equivalente exacto", "era RGB", or similar, stop the analogy, reopen the reference figure/caption/notebook cell, and rebuild with traceability.

## Minimal Workflow

1. Preserve the original deck.
2. Create or request a working copy.
3. Run `existing-deck-style-audit` on the reference deck to derive title positions, figure boxes, caption zones, safe margins, and density patterns.
4. Generate and complete `scientific_asset_manifest.json` before moving figures into new slides.
5. Keep slide content, speaker script, and poster-style text in separate layer files so speaker-only detail does not crowd the slides.
6. Place scientific figures as image assets, not whole-slide screenshots.
7. Keep slide-level text and annotations editable.
8. Export a preview PDF or PNG pages for visual review.
9. Review whether the deck is figure-led, text-led, comparative, dense, or missing evidence.

## Useful Commands

```bash
python scripts/presentation_workbench.py inspect copied_deck.pptx \
  --summary-json deck_inspection.json
```

For a deck that already has good group-reference slides, audit the style first:

```bash
python scripts/presentation_workbench.py existing-deck-style-audit copied_deck.pptx audit_dir \
  --reference-slides 2,3,5-7 \
  --rule "Do not put notebook screenshots on slides" \
  --rule "Keep scope limited to the reduction photometry result" \
  --summary-json audit_dir/style_audit_summary.json
```

For PPTX/PPTM inputs, a preview PDF can be requested when an export backend is available:

```bash
python scripts/presentation_workbench.py inspect copied_deck.pptx \
  --export-preview-pdf deck_preview.pdf \
  --summary-json deck_inspection.json
```

For a copied handoff bundle:

```bash
python scripts/presentation_workbench.py handoff copied_deck.pptx handoff_dir \
  --export-pdf \
  --summary-json handoff_dir/summary.json
```

The handoff bundle now also writes:

- `scientific_asset_manifest.json`
- `presentation_constraints.json`
- `slide_content.md`
- `speaker_script.md`
- `poster_text.md`
- `new_slide_templates.json` when a PPTX style audit can derive reusable boxes

For coursework figures, complete the exact-equivalent fields in `scientific_asset_manifest.json`: final figure name, slide position such as `04_A`, source notebook/cell/function, FITS/RGB source, object, filter/channel, visual mode, crop, scaling, overlays, annotations, and generation command.

## Mini Checklist

- Original deck identified and untouched.
- Working copy created.
- Reference slide audit run when the deck already has a stable visual language.
- Scientific assets listed separately from slide screenshots.
- Figures are image assets; explanatory text is editable.
- Captions are short enough for slides and visibly present under the relevant figure.
- Preview PDF/PNG exported.
- Visual review done for overlaps, clipped labels, low-resolution figures, alignment drift, and too much prose.
- `scientific_asset_manifest.json` completed with source path, notebook/product origin, visual intent, visual mode, scale criteria, and reason for use.
- Slide assets named or grouped by destination and position, for example `04_A`, `04_B`, while source assets and temporary previews remain separate.
- Slide content kept separate from speaker-only material.

## Visual Evidence Checklist

Prefer figures that demonstrate something the speaker would otherwise have to describe verbally:

- **Protagonist figure**: the main result or strongest visual evidence.
- **Control figure**: diagnostic, calibration, residual, comparison, or sanity check.
- **Oral support figure**: useful while speaking but not central enough for the poster.
- **Reject figure**: too redundant, too low-quality, too text-heavy, or not tied to the user's scope.

Rule of thumb: the voice explains; the slide demonstrates.

## Comparative Oral Style

Use this when the useful material is not just the deck, but the relationship between a person's slides and the way they speak over them. The goal is to learn pacing and density, not to copy content.

Workflow:

1. Read the other person's script, notes, or transcript separately from the slides.
2. Inspect the slides and identify what is actually visible on screen.
3. Separate scientific content from oral style:
   - content: results, method, numbers, limitations, claims
   - style: pacing, connectors, amount of context per slide, how problems are introduced, how captions are expanded aloud
4. Note how the speaker expands slide evidence without reading it verbatim.
5. Rewrite the user's part in the user's speaker voice, with similar density and rhythm only where it helps.
6. Verify that no phrases, claims, or examples from classmates have been copied unless explicitly shared for reuse.

Useful output structure:

- what the reference speaker puts on screen
- what they add orally
- connectors or rhythm patterns worth adapting
- what not to copy
- rewritten user block
- slide text that should stay short
- speaker-only detail that should not go on the slide

Hard rules:

- do not copy phrases or content from classmates
- do not import science that belongs to another person's scope
- keep the user's speaker voice recognizable
- if the slide is already dense, move explanation to speech instead of adding text

## QA Focus

The style audit and handoff QA should explicitly check:

- safe area and margins
- title alignment relative to reference slides
- centered or intentionally aligned protagonist figures
- no clipping
- captions visible
- consistency with neighboring slides
- no accidental rasterized whole-slide compositions

Use the generated report as a hard stop before hand-editing more slides.

## Keynote Support

`.key` support should be treated as best-effort:

- keep a backup before any round-trip
- export a PNG or preview image for visual review
- verify the result manually
- roll back if alignment or editability regresses

Do not promise the same geometry-level reliability for `.key` that you can derive from a native PPTX object model.

## What Not To Automate

- Do not build a full scientific poster generator inside this skill.
- Do not turn Keynote into a complex layout engine.
- Do not flatten complete slides into PNGs when editability matters.
- Do not treat notebook screenshots as acceptable slide content just because they are easy to paste.
- Do not mix unrelated science threads just because their products live in the same folder.

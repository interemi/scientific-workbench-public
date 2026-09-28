# Academic Reporting

## Use This Reference For

- scientific reports, investigation projects, paper-style coursework, and manuscript-like LaTeX deliverables
- improving an existing report without touching the original
- doing a supervisor-style pre-submission review before the final PDF is shared
- pairing a report workflow with reduced ASCII spectra or notebook-based coursework inputs
- astrophysics practices where the final text must separate measurements, physical interpretation, and limitations

## Recommended Workflow

1. Rebuild the evidence chain first.
Start from the source tables, figures, notebooks, or reduction outputs instead of only rewriting the final PDF.

2. Separate content work from layout work.
Get the argument, numbers, and caveats right in a robust draft before polishing the final two-column or paper-like layout.

3. Use generated assets.
Prefer figures and tables produced by scripts over manual edits inside LaTeX.

4. Review claim strength explicitly.
Distinguish clearly between:
- well-supported findings
- suggestive interpretations
- context-specific choices already accepted by the user, teacher, or supervisor
- speculation or physical explanations that need more evidence

For scientific or astrophysics reports, also keep three layers visible:
- procedure: what was done, with which data, tools, selections, and parameters
- physical interpretation: what the measured result plausibly means
- limitations: uncertainties, biases, assumptions, manual choices, and what the data cannot prove

5. Then polish the manuscript.
Once the evidence is stable, improve layout, captions, appendix handling, and handoff outputs.

6. Use the narrower coursework path when it fits.
If the job is really "reduced ASCII spectra + existing notebook + final memory", pair this reference with `coursework-spectra.md` instead of improvising the whole workflow from scratch.

7. Use the astrophysics writing layer when interpretation matters.
For master-level astrophysics practice reports, pair this reference with `astrophysics-academic-writing.md` and run `scientific_writeup_review.py` before final submission.

## Practical Guidance

- For a fresh paper-like template:

```bash
python3 scripts/latex_workbench.py scaffold /path/to/output --kind academic-report --title "Project title"
```

- For a pre-submission advisory review:

```bash
python3 scripts/latex_workbench.py review /path/to/main.tex --report-md /tmp/report_review.md --summary-json /tmp/report_review.json
```

- For a scientific argument and interpretation review:

```bash
python3 scripts/scientific_writeup_review.py /path/to/main.tex --report-md /tmp/scientific_writeup_review.md --summary-json /tmp/scientific_writeup_review.json
```

- For safe compilation in a copy:

```bash
python3 scripts/latex_workbench.py compile /path/to/main.tex --output-dir /tmp/latex-build --manifest-json /tmp/latex-build/compile_manifest.json
```

## What The Review Looks For

- missing abstract or weak manuscript structure
- too many forced `[H]` floats in a two-column layout
- longtables inside two-column projects without a clear one-column appendix switch
- wide included tables that may overflow a single column
- absolute filesystem paths that hurt portability
- phrasing that may read stronger than the evidence level, while treating this as advisory rather than as an automatic error
- missing bibliography files, unresolved citation keys, and suspiciously thin discussion or conclusion sections
- missing units, uncertainties, assumptions, limitations, or explicit comparison with literature when the assignment calls for it
- results sections that mix measurement and interpretation so tightly that the evidence chain becomes hard to audit

## Important Nuance

- A methodological choice is not automatically wrong just because it is pragmatic or course-specific.
- If the user already knows that a teacher or supervisor approved a choice, treat that as context, not as something the tool should blindly fight.
- The review should help catch unsupported leaps, not override accepted expert guidance.
- The review is still a strong smoke test and advisory pass, not a substitute for an expert reading the manuscript end to end.
- A missing uncertainty is not always fatal in coursework, but the text should either provide one or explain why only a first-pass or qualitative estimate is defensible.

## Good Habits

- keep one copied project per submission pass
- preserve the script that generated each key figure or table
- make the abstract and conclusion slightly more cautious than the discussion, not the other way around
- move wide appendix tables to one-column mode when the manuscript body is in two columns
- treat the final PDF as the end of a reproducible pipeline, not as the source of truth
- run both reviews before delivery when the report is scientific: `latex_workbench.py review` for source/layout risks and `scientific_writeup_review.py` for argument quality

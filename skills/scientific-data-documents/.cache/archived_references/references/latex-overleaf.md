# LaTeX and Overleaf

This belongs to the `documents + reporting` block.

## Use This Reference For

- `.tex`, `.bib`, and multi-file LaTeX projects
- Overleaf-ready manuscripts, reports, proposals, appendices, and thesis-like documents
- converting analysis outputs into tables, figures, and reproducible technical writing
- validating existing LaTeX projects without touching the originals

## Core Rules

- Treat LaTeX as source code, not as a final artifact.
- Prefer compiling in a copied working directory when the original project must remain untouched.
- Keep relative paths simple so the same project can run locally and in Overleaf.
- Use standard packages unless the user explicitly needs a niche setup.
- Separate content from generated tables and figures when possible.

## Recommended Workflow

1. Inspect the project.
Find the main `.tex` file, `\documentclass`, included files, bibliography, figures, and custom commands.

2. Check portability.
Look for local absolute paths, shell-escape assumptions, non-standard fonts, or platform-specific packages that may break in Overleaf.

3. Compile in a copy.
Use `latexmk` in a temporary or output directory and keep logs.

4. Review the output and the logs.
Distinguish warnings from hard errors. Missing citations, missing figure files, and undefined references matter.

5. Feed analysis outputs back into LaTeX.
Generate tables, plots, and appendix material from scripts and save them with stable names.

## Overleaf Compatibility Checklist

- The main file compiles with `latexmk -pdf`.
- Figures use relative paths.
- Bibliography files are present and referenced correctly.
- No hardcoded local filesystem paths remain.
- The project does not depend on external binaries unless explicitly planned.
- Encodings and package usage are standard enough for a remote TeX environment.

## Common Patterns

### Scientific article or report

- `main.tex`
- `bibliography.bib`
- `figures/`
- `tables/`
- optional `sections/`

### Proposal or technical note

- Keep section structure shallow and easy to scan.
- Prefer concise abstract, motivation, methods, feasibility, timeline, and expected outputs.

### Generated appendix tables

- Generate long tables from scripts rather than hand-editing rows.
- Use `longtable` or `tabularx` when the content calls for it.
- Keep units in headers and notes in captions.

## Creation Guidance

- Use the helper script when you want a clean starting project:

```bash
python3 scripts/latex_workbench.py scaffold /path/to/output --title "Project title" --kind article
```

- For a paper-style academic template with a safer default appendix layout:

```bash
python3 scripts/latex_workbench.py scaffold /path/to/output --title "Project title" --kind academic-report
```

- Inspect an existing project:

```bash
python3 scripts/latex_workbench.py inspect /path/to/main.tex
```

- Compile safely in a copy:

```bash
python3 scripts/latex_workbench.py compile /path/to/main.tex --output-dir /tmp/latex-build
```

- Run an advisory review before the final submission:

```bash
python3 scripts/latex_workbench.py review /path/to/main.tex --report-md /tmp/latex-review.md --summary-json /tmp/latex-review.json
```

## Bibliography Guidance

- Preserve `.bib` keys unless the user asks for renaming.
- Keep one bibliography file per project unless there is a clear need to split it.
- For astronomy-heavy work, ADS-style exports are often acceptable starting points, but check formatting expectations.

## Scientific Writing Guidance

- Keep equations, units, symbols, and citations consistent with the analysis code.
- If a table or figure is derived from data processing, mention or preserve the script that generated it.
- For bilingual work, prefer one language per manuscript unless the user explicitly wants bilingual sections.
- For long academic reports, prefer a two-step process: first stabilize the evidence and argument, then polish the final layout.
- If the user mentions a teacher or supervisor already approved a methodological choice, treat that as context; the review tooling should warn about unsupported leaps, not automatically fight accepted guidance.

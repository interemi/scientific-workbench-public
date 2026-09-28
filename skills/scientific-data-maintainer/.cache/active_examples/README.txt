# Packaged Examples

This folder contains small portable examples meant for installation checks, smoke tests, and first-use demonstrations on a new machine.

What is here:

- `tabular/`: small operational-style tables for CSV and JSONL profiling
- `documents/`: plain-text and markdown documents for intake workflows
- `science/`: a tiny ASCII spectrum for lightweight science-oriented testing
- `science/legacy_spectroscopy_mini/`: tiny legacy spectroscopy example with a synthetic `MULTISPE` FITS, parsed `fxcor` CSV, and `.sm` sample
- `queries/`: example SQL snippets for DuckDB-based exploration

What is not here:

- no user data
- no large binaries
- no proprietary originals

For richer examples such as generated FITS, DOCX, PPTX, and XLSX files, run:

```bash
python scripts/portable_smoke_test.py --output-dir smoke-out --examples-dir examples
```

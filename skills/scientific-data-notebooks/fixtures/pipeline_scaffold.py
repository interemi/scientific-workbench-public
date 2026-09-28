#!/usr/bin/env python3
"""Create a reproducible analysis pipeline scaffold."""

import argparse
from pathlib import Path


PIPELINE_TOML = """[project]
name = "{name}"
domain = "{domain}"
language = "{language}"
profile = "{profile}"

[paths]
raw = "data/raw"
interim = "data/interim"
reduced = "data/reduced"
figures = "reports/figures"
tables = "reports/tables"
qa = "reports/qa"
logs = "reports/logs"
notebooks = "notebooks"
scripts = "scripts"
config = "config"

[workflow]
inspect = true
validate = true
report = true
"""


RUNNER_PY = """#!/usr/bin/env python3
\"\"\"Starter script for a reproducible analysis pipeline.\"\"\"

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
REDUCED = ROOT / "data" / "reduced"
FIGURES = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"
QA = ROOT / "reports" / "qa"


def main():
    print(f"Raw data dir: {RAW}")
    print(f"Interim data dir: {INTERIM}")
    print(f"Reduced data dir: {REDUCED}")
    print(f"Figures dir: {FIGURES}")
    print(f"Tables dir: {TABLES}")
    print(f"QA dir: {QA}")


if __name__ == "__main__":
    main()
"""


VALIDATE_PY = """#!/usr/bin/env python3
\"\"\"Basic input validation for the pipeline scaffold.\"\"\"

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def main():
    if not RAW.exists():
        raise SystemExit(f"Missing raw-data directory: {RAW}")
    count = sum(1 for _ in RAW.iterdir()) if RAW.is_dir() else 0
    print(f"Raw data entries: {count}")
    if count == 0:
        print("Warning: data/raw is empty.")


if __name__ == "__main__":
    main()
"""


NOTEBOOK_MD = {
    "en": "# Pipeline Notes\n\nUse this folder for reproducible notebooks tied to the pipeline manifest.\n",
    "es": "# Notas del pipeline\n\nUsa esta carpeta para notebooks reproducibles ligados al manifiesto del pipeline.\n",
    "bilingual": "# Pipeline Notes / Notas del pipeline\n\nUse this folder for reproducible notebooks tied to the pipeline manifest. / Usa esta carpeta para notebooks reproducibles ligados al manifiesto del pipeline.\n",
}


ROOT_README = {
    "en": "# Analysis Pipeline\n\nThis scaffold separates raw, interim, reduced, and report-ready outputs so the workflow stays reproducible.\n",
    "es": "# Pipeline de analisis\n\nEste esqueleto separa datos brutos, intermedios, reducidos y listos para informe para mantener el flujo reproducible.\n",
    "bilingual": "# Analysis Pipeline / Pipeline de analisis\n\nThis scaffold separates raw, interim, reduced, and report-ready outputs so the workflow stays reproducible. / Este esqueleto separa datos brutos, intermedios, reducidos y listos para informe para mantener el flujo reproducible.\n",
}


PROFILE_NOTES = {
    "generic": {
        "en": "Generic analysis profile for reusable scientific workflows.",
        "es": "Perfil generico de analisis para flujos cientificos reutilizables.",
        "bilingual": "Generic analysis profile for reusable scientific workflows. / Perfil generico de analisis para flujos cientificos reutilizables.",
    },
    "imaging": {
        "en": "Imaging profile with space for calibration products, quicklooks, and masks.",
        "es": "Perfil de imagen con espacio para calibraciones, quicklooks y mascaras.",
        "bilingual": "Imaging profile with space for calibration products, quicklooks, and masks. / Perfil de imagen con espacio para calibraciones, quicklooks y mascaras.",
    },
    "spectroscopy": {
        "en": "Spectroscopy profile with calibration, extracted spectra, and line measurements.",
        "es": "Perfil de espectroscopia con calibraciones, espectros extraidos y medidas de lineas.",
        "bilingual": "Spectroscopy profile with calibration, extracted spectra, and line measurements. / Perfil de espectroscopia con calibraciones, espectros extraidos y medidas de lineas.",
    },
    "time-series": {
        "en": "Time-series profile with light curves, period searches, and QA products.",
        "es": "Perfil de series temporales con curvas de luz, busquedas de periodo y productos QA.",
        "bilingual": "Time-series profile with light curves, period searches, and QA products. / Perfil de series temporales con curvas de luz, busquedas de periodo y productos QA.",
    },
    "catalog": {
        "en": "Catalog profile with joins, cross-matches, and clean export tables.",
        "es": "Perfil de catalogos con joins, cross-match y tablas limpias de exportacion.",
        "bilingual": "Catalog profile with joins, cross-matches, and clean export tables. / Perfil de catalogos con joins, cross-match y tablas limpias de exportacion.",
    },
    "documents": {
        "en": "Document-centric profile for LaTeX, notebooks, reports, and supporting datasets.",
        "es": "Perfil centrado en documentos para LaTeX, notebooks, informes y datasets de apoyo.",
        "bilingual": "Document-centric profile for LaTeX, notebooks, reports, and supporting datasets. / Perfil centrado en documentos para LaTeX, notebooks, informes y datasets de apoyo.",
    },
}


PROFILE_DIRS = {
    "generic": [],
    "imaging": ["data/calibration", "products/quicklooks", "products/masks"],
    "spectroscopy": ["data/calibration", "products/spectra", "products/line-fits"],
    "time-series": ["products/lightcurves", "products/periodograms", "products/qa"],
    "catalog": ["products/catalogs", "products/crossmatch", "products/selection-cuts"],
    "documents": ["reports/drafts", "reports/bibliography", "assets"],
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", help="Target pipeline directory.")
    parser.add_argument("--name", default="analysis-pipeline")
    parser.add_argument("--domain", choices=["general", "astronomy"], default="general")
    parser.add_argument("--language", choices=["en", "es", "bilingual"], default="en")
    parser.add_argument(
        "--profile",
        choices=["generic", "imaging", "spectroscopy", "time-series", "catalog", "documents"],
        default="generic",
        help="Reusable project profile that adds a few domain-appropriate folders and notes.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    root = Path(args.output_dir)
    for rel in [
        "data/raw",
        "data/interim",
        "data/reduced",
        "notebooks",
        "scripts",
        "reports/figures",
        "reports/tables",
        "reports/qa",
        "reports/logs",
        "config",
    ]:
        (root / rel).mkdir(parents=True, exist_ok=True)
    for rel in PROFILE_DIRS[args.profile]:
        (root / rel).mkdir(parents=True, exist_ok=True)

    (root / "config" / "pipeline.toml").write_text(
        PIPELINE_TOML.format(name=args.name, domain=args.domain, language=args.language, profile=args.profile)
    )
    runner = root / "scripts" / "run_pipeline.py"
    runner.write_text(RUNNER_PY)
    runner.chmod(0o755)
    validator = root / "scripts" / "validate_inputs.py"
    validator.write_text(VALIDATE_PY)
    validator.chmod(0o755)
    (root / "notebooks" / "README.md").write_text(NOTEBOOK_MD[args.language])
    (root / "README.md").write_text(ROOT_README[args.language] + "\n" + PROFILE_NOTES[args.profile][args.language] + "\n")
    (root / "config" / "profile_notes.md").write_text(PROFILE_NOTES[args.profile][args.language] + "\n")
    print(f"Pipeline scaffold created at {root.resolve()}")


if __name__ == "__main__":
    main()

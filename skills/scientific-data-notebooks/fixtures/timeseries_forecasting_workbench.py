#!/usr/bin/env python3
"""Scaffold a reproducible forecasting notebook for general time-series coursework."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _internal.public_contract import build_blocked_payload, build_tool_payload, emit_payload, emit_payload_best_effort
from _internal.provenance_utils import public_path, sanitize_payload, write_manifest
from _internal.runtime_common import clean_known_stderr


TEXT = {
    "en": {
        "intro": "Build a reproducible forecasting notebook for a tabular time series using train/test evaluation, baseline comparisons, and clean exports.",
        "goals_heading": "## Goals",
        "goals_body": (
            "- Load and validate the time series.\n"
            "- Split the last observations into a hold-out test set.\n"
            "- Compare an identified ARIMA model against simple benchmark models.\n"
            "- Report metrics, diagnostic plots, and a short written interpretation.\n"
            "- Export figures and result tables in a portable way."
        ),
        "runtime_heading": "## Runtime profile",
        "runtime_body_local": (
            "This scaffold is prepared for a local Python environment. "
            "Keep paths relative when possible and export all deliverables under the chosen output folder."
        ),
        "runtime_body_colab": (
            "This scaffold is prepared for Google Colab or another notebook service. "
            "Avoid hard-coded home paths, keep inputs explicit, and write all exports to a single project folder."
        ),
        "results_heading": "## Deliverables",
        "results_body": (
            "- Executed notebook with narrative and outputs.\n"
            "- Clean metric table.\n"
            "- Forecast table.\n"
            "- Individual PNG figures.\n"
            "- One PDF containing all figures together."
        ),
    },
    "es": {
        "intro": "Construye un notebook reproducible de prediccion para una serie temporal tabular, con evaluacion train/test, comparacion con benchmarks y exportaciones limpias.",
        "goals_heading": "## Objetivos",
        "goals_body": (
            "- Cargar y validar la serie temporal.\n"
            "- Separar las ultimas observaciones como muestra de test.\n"
            "- Comparar un ARIMA identificado con modelos benchmark sencillos.\n"
            "- Reportar metricas, graficos diagnosticos e interpretacion breve.\n"
            "- Exportar figuras y tablas de resultados de forma portable."
        ),
        "runtime_heading": "## Perfil de ejecucion",
        "runtime_body_local": (
            "Este scaffold esta preparado para un entorno Python local. "
            "Mantiene rutas relativas cuando sea posible y exporta todos los entregables dentro de la carpeta de salida elegida."
        ),
        "runtime_body_colab": (
            "Este scaffold esta preparado para Google Colab u otro servicio de notebooks. "
            "Evita rutas absolutas de usuario, deja los datos de entrada explicitos y escribe todas las salidas en una sola carpeta de proyecto."
        ),
        "results_heading": "## Entregables",
        "results_body": (
            "- Notebook ejecutado con narrativa y outputs.\n"
            "- Tabla limpia de metricas.\n"
            "- Tabla de prediccion.\n"
            "- Figuras PNG por separado.\n"
            "- Un PDF con todas las figuras juntas."
        ),
    },
    "bilingual": {
        "intro": (
            "Build a reproducible forecasting notebook / "
            "Construye un notebook reproducible de prediccion para una serie temporal tabular."
        ),
        "goals_heading": "## Goals / Objetivos",
        "goals_body": (
            "- Load and validate the time series / Cargar y validar la serie temporal.\n"
            "- Split the last observations into a hold-out test set / Separar las ultimas observaciones como muestra de test.\n"
            "- Compare an identified ARIMA model against simple benchmarks / Comparar un ARIMA identificado con benchmarks sencillos.\n"
            "- Report metrics, plots, and interpretation / Reportar metricas, graficos e interpretacion.\n"
            "- Export clean deliverables / Exportar entregables limpios."
        ),
        "runtime_heading": "## Runtime profile / Perfil de ejecucion",
        "runtime_body_local": (
            "Prepared for local Python work / Preparado para trabajo local en Python."
        ),
        "runtime_body_colab": (
            "Prepared for Colab-style execution / Preparado para ejecucion tipo Colab."
        ),
        "results_heading": "## Deliverables / Entregables",
        "results_body": (
            "- Executed notebook / Notebook ejecutado.\n"
            "- Metrics and forecast tables / Tablas de metricas y prediccion.\n"
            "- PNG figures and one PDF bundle / Figuras PNG y un PDF conjunto."
        ),
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Directory where the notebook and side products will be created.")
    parser.add_argument("--title", default="General Time-Series Forecasting Notebook", help="Notebook title.")
    parser.add_argument("--language", choices=["en", "es", "bilingual"], default="en")
    parser.add_argument("--runtime-profile", choices=["local", "colab"], default="local")
    parser.add_argument("--data-path", help="Optional data file path to prefill in the notebook.")
    parser.add_argument("--date-column", help="Optional date column name.")
    parser.add_argument("--value-column", help="Optional target/value column name.")
    parser.add_argument("--frequency", default="MS", help="Pandas frequency string, for example MS or M.")
    parser.add_argument("--test-horizon", type=int, default=12, help="Number of trailing observations kept for test.")
    parser.add_argument("--notebook-name", default="timeseries_forecasting_notebook.ipynb")
    parser.add_argument("--summary-json")
    parser.add_argument("--manifest-json")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


DATE_CANDIDATES = ("date", "fecha", "period", "time", "month", "mes")
VALUE_CANDIDATES = ("value", "target", "y", "ipc", "inflation", "annualrate", "annual_rate", "rate", "series")
SUPPORTED_DATA_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls"}


def resolve_summary_path(args, output_dir: Path | None = None) -> Path | None:
    if getattr(args, "summary_json", None):
        return Path(args.summary_json).expanduser()
    if output_dir is not None:
        return output_dir / "summary.json"
    return None


def paths_refer_to_same_file(left: Path, right: Path) -> bool:
    """Compare existing aliases/hardlinks and not-yet-created paths canonically."""
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError:
        pass
    return left.expanduser().resolve(strict=False) == right.expanduser().resolve(strict=False)


def path_is_within(candidate: Path, directory: Path) -> bool:
    try:
        candidate.expanduser().resolve(strict=False).relative_to(
            directory.expanduser().resolve(strict=False)
        )
        return True
    except ValueError:
        return False


def requested_output_targets(args) -> list[tuple[str, Path]]:
    """Enumerate every path this scaffold itself may create or replace."""
    output_dir = Path(args.output_dir).expanduser()
    targets = [
        ("--output-dir", output_dir),
        ("generated notebook (--notebook-name)", output_dir / args.notebook_name),
    ]
    if getattr(args, "summary_json", None):
        targets.append(("--summary-json", Path(args.summary_json).expanduser()))
    else:
        # Validation blockers use this default even though successful runs only
        # print their envelope when --summary-json is omitted.
        targets.append(("implicit blocked summary", output_dir / "summary.json"))
    if getattr(args, "manifest_json", None):
        targets.append(("--manifest-json", Path(args.manifest_json).expanduser()))
    return targets


def find_data_output_collision(args) -> str | None:
    """Reject source replacement and writes inside a directory data source."""
    raw_data_path = getattr(args, "data_path", None)
    if not raw_data_path:
        return None
    data_path = Path(raw_data_path).expanduser()
    data_is_directory = data_path.is_dir()
    for label, output_path in requested_output_targets(args):
        if paths_refer_to_same_file(output_path, data_path):
            return (
                f"Refusing to overwrite --data-path: {label} resolves to the same path as "
                f"{public_path(data_path)}."
            )
        if data_is_directory and path_is_within(output_path, data_path):
            return (
                f"Refusing to write inside directory --data-path: {label} resolves under "
                f"{public_path(data_path)}."
            )
    return None


def emit_blocked(
    args,
    message: str,
    *,
    error_type: str | None = None,
    stdout_only: bool = False,
) -> int:
    # Defensive backstop for all early-exit call sites, including exceptions
    # raised before run_workflow has created its output directory.
    if find_data_output_collision(args):
        stdout_only = True
    output_dir = Path(args.output_dir).expanduser() if getattr(args, "output_dir", None) else None
    summary_path = None if stdout_only else resolve_summary_path(args, output_dir)
    payload = build_blocked_payload(
        "timeseries_forecasting_workbench",
        message,
        notes=[
            "The forecasting notebook scaffold was not completed.",
            "No source data was modified; fix the blocked argument or destination and rerun.",
        ],
        artifacts={
            "summary_json": summary_path,
            "output_dir": None if stdout_only else output_dir,
        },
        results={
            "blocked_reason": message,
            "error_type": error_type,
            "output_dir": str(output_dir) if output_dir else None,
            "data_path": getattr(args, "data_path", None),
            "notebook_name": getattr(args, "notebook_name", None),
        },
        inputs=[getattr(args, "data_path", None)] if getattr(args, "data_path", None) else [],
    )
    emit_payload_best_effort(payload, summary_path)
    return 2


def validate_output_target(raw_path: str | None, label: str) -> None:
    if not raw_path:
        return
    path = Path(raw_path).expanduser()
    parent = path.parent
    if parent.exists() and not parent.is_dir():
        raise SystemExit(f"{label} parent is not a directory: {parent}")


def validate_notebook_name(raw_name: str) -> None:
    path = Path(raw_name)
    if path.is_absolute() or path.name != raw_name or ".." in path.parts:
        raise SystemExit("--notebook-name must be a simple relative .ipynb filename, not a path.")
    if path.suffix.lower() != ".ipynb":
        raise SystemExit("--notebook-name must end with .ipynb.")


def read_input_table(path: Path):
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise SystemExit(f"Unsupported input format for generated notebook: {suffix or '(none)'}")


def detect_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {str(col).strip().lower(): str(col) for col in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def validate_frequency(frequency: str) -> None:
    import pandas as pd

    try:
        pd.tseries.frequencies.to_offset(frequency)
    except Exception as exc:
        raise SystemExit(f"Invalid pandas frequency string: {frequency!r}") from exc


def validate_data_path(args) -> tuple[dict | None, list[str]]:
    import numpy as np
    import pandas as pd

    warnings = []
    if not args.data_path:
        return None, warnings
    data_path = Path(args.data_path).expanduser()
    if not data_path.exists():
        message = f"Input data file does not exist locally: {data_path}"
        if args.runtime_profile == "colab":
            warnings.append(message)
            return {"path": str(data_path), "exists": False}, warnings
        raise SystemExit(message)
    if data_path.suffix.lower() not in SUPPORTED_DATA_SUFFIXES:
        raise SystemExit(f"Unsupported input format for generated notebook: {data_path.suffix.lower() or '(none)'}")
    try:
        df = read_input_table(data_path)
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(f"Could not read input data table: {exc.__class__.__name__}: {exc}") from exc
    if df.empty:
        raise SystemExit("Input data table is empty.")
    columns = [str(col) for col in df.columns]
    date_col = args.date_column or detect_column(columns, DATE_CANDIDATES) or columns[0]
    if date_col not in columns:
        raise SystemExit(f"Requested date column not found: {date_col}")
    if args.value_column:
        value_col = args.value_column
    else:
        numeric_cols = [
            str(col)
            for col in df.columns
            if str(col) != date_col and pd.api.types.is_numeric_dtype(df[col])
        ]
        value_col = detect_column([str(col) for col in df.columns if str(col) != date_col], VALUE_CANDIDATES)
        if value_col is None and numeric_cols:
            value_col = numeric_cols[0]
    if not value_col or value_col not in columns:
        raise SystemExit(f"Requested or inferred value column not found: {value_col or '(none)'}")
    parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
    parsed_values = pd.to_numeric(df[value_col], errors="coerce")
    finite_values = pd.Series(
        np.isfinite(parsed_values.to_numpy(dtype=float, na_value=np.nan)),
        index=df.index,
    )
    valid_mask = parsed_dates.notna() & parsed_values.notna() & finite_values
    valid_rows = int(valid_mask.sum())
    if valid_rows == 0:
        raise SystemExit("No rows have both a parseable date and numeric target value.")
    if args.test_horizon >= valid_rows:
        raise SystemExit("--test-horizon must be smaller than the valid input row count.")
    if valid_rows - args.test_horizon < 8:
        raise SystemExit("The training split is too short for this ARIMA scaffold; provide at least 8 training rows.")
    invalid_date_count = int(parsed_dates.isna().sum())
    non_numeric_count = int(parsed_values.isna().sum())
    infinite_value_count = int((parsed_values.notna() & ~finite_values).sum())
    if parsed_dates.dropna().duplicated().any():
        warnings.append("Input data contains duplicate dates; the generated notebook will keep the first occurrence.")
    if invalid_date_count or non_numeric_count or infinite_value_count:
        warnings.append(
            "Input cleaning will exclude invalid rows: "
            f"invalid_dates={invalid_date_count}, non_numeric_values={non_numeric_count}, "
            f"infinite_values={infinite_value_count}."
        )
    return (
        {
            "path": str(data_path),
            "exists": True,
            "row_count": int(df.shape[0]),
            "valid_row_count": valid_rows,
            "invalid_date_count": invalid_date_count,
            "non_numeric_value_count": non_numeric_count,
            "infinite_value_count": infinite_value_count,
            "columns": columns,
            "resolved_date_column": date_col,
            "resolved_value_column": value_col,
        },
        warnings,
    )


def validate_args(args, output_dir: Path) -> tuple[dict | None, list[str]]:
    if output_dir.exists() and not output_dir.is_dir():
        raise SystemExit(f"--output-dir must point to a directory, not an existing file: {output_dir}")
    validate_output_target(args.summary_json, "--summary-json")
    validate_output_target(args.manifest_json, "--manifest-json")
    validate_notebook_name(args.notebook_name)
    if args.test_horizon <= 0:
        raise SystemExit("--test-horizon must be a positive integer.")
    validate_frequency(args.frequency)
    return validate_data_path(args)


def md_cell(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in text.strip().splitlines()],
    }


def code_cell(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in text.strip().splitlines()],
    }


def build_setup_cell(runtime_profile: str) -> str:
    lines = [
        "from pathlib import Path",
        "",
        "import json",
        "import math",
        "import warnings",
        "",
        "import numpy as np",
        "import pandas as pd",
        "import matplotlib.pyplot as plt",
        "from IPython.display import display",
        "from scipy import stats",
        "from sklearn.metrics import mean_absolute_error, mean_squared_error",
        "from statsmodels.graphics.tsaplots import plot_acf, plot_pacf",
        "from statsmodels.tsa.arima.model import ARIMA",
        "",
        "plt.style.use('seaborn-v0_8-whitegrid')",
        "MODEL_WARNINGS = []",
    ]
    if runtime_profile == "colab":
        lines.extend(
            [
                "",
                "try:",
                "    import google.colab  # type: ignore",
                "    IN_COLAB = True",
                "except Exception:",
                "    IN_COLAB = False",
            ]
        )
    else:
        lines.extend(["", "IN_COLAB = False"])
    return "\n".join(lines)


def build_config_cell(data_path: str | None, date_column: str | None, value_column: str | None, frequency: str, test_horizon: int) -> str:
    data_literal = repr(data_path) if data_path else "None"
    date_literal = repr(date_column) if date_column else "None"
    value_literal = repr(value_column) if value_column else "None"
    return "\n".join(
        [
            f"DATA_PATH = {data_literal}",
            f"DATE_COLUMN = {date_literal}",
            f"VALUE_COLUMN = {value_literal}",
            f"FREQUENCY = {frequency!r}",
            f"TEST_HORIZON = {int(test_horizon)}",
            "",
            "PROJECT_ROOT = Path.cwd()",
            "OUTPUT_DIR = PROJECT_ROOT / 'timeseries_outputs'",
            "OUTPUT_DIR.mkdir(parents=True, exist_ok=True)",
            "FIGURE_REGISTRY = []",
            "",
            "if DATA_PATH is None:",
            "    print('Set DATA_PATH before running the notebook.')",
            "else:",
            "    print(f'Configured input: {DATA_PATH}')",
            "print(f'Exports will go to: {OUTPUT_DIR.resolve()}')",
        ]
    )


def build_helper_cell() -> str:
    return "\n".join(
        [
            "DATE_CANDIDATES = ('date', 'fecha', 'period', 'time', 'month', 'mes')",
            "VALUE_CANDIDATES = ('value', 'target', 'y', 'ipc', 'inflation', 'annualrate', 'annual_rate', 'rate', 'series')",
            "",
            "def detect_date_column(df):",
            "    lowered = {str(col).strip().lower(): col for col in df.columns}",
            "    for candidate in DATE_CANDIDATES:",
            "        if candidate in lowered:",
            "            return lowered[candidate]",
            "    for col in df.columns:",
            "        if pd.api.types.is_datetime64_any_dtype(df[col]):",
            "            return col",
            "    return df.columns[0]",
            "",
            "def detect_value_column(df, date_col):",
            "    lowered = {str(col).strip().lower(): col for col in df.columns if col != date_col}",
            "    for candidate in VALUE_CANDIDATES:",
            "        if candidate in lowered:",
            "            return lowered[candidate]",
            "    numeric_cols = [col for col in df.columns if col != date_col and pd.api.types.is_numeric_dtype(df[col])]",
            "    if len(numeric_cols) == 1:",
            "        return numeric_cols[0]",
            "    if numeric_cols:",
            "        return numeric_cols[0]",
            "    raise ValueError('Could not detect a numeric target column automatically.')",
            "",
            "def save_current_figure(name):",
            "    path = OUTPUT_DIR / name",
            "    plt.gcf().tight_layout()",
            "    plt.savefig(path, dpi=160, bbox_inches='tight')",
            "    FIGURE_REGISTRY.append(path)",
            "    print(f'Saved figure: {path}')",
            "",
            "def msfe(y_true, y_pred):",
            "    errors = np.asarray(y_true) - np.asarray(y_pred)",
            "    return float(np.mean(errors ** 2))",
            "",
            "def record_model_warnings(caught, context):",
            "    for item in caught:",
            "        MODEL_WARNINGS.append({'context': context, 'category': item.category.__name__, 'message': str(item.message)})",
            "",
            "def diebold_mariano(errors_a, errors_b, power=2):",
            "    loss_diff = np.abs(np.asarray(errors_a)) ** power - np.abs(np.asarray(errors_b)) ** power",
            "    n = loss_diff.size",
            "    if n < 2:",
            "        return {'dm_stat': np.nan, 'p_value': np.nan, 'n': int(n)}",
            "    mean_diff = float(loss_diff.mean())",
            "    var_diff = float(loss_diff.var(ddof=1))",
            "    if var_diff == 0:",
            "        return {'dm_stat': 0.0, 'p_value': 1.0, 'n': int(n)}",
            "    dm_stat = mean_diff / math.sqrt(var_diff / n)",
            "    p_value = 2 * (1 - stats.t.cdf(abs(dm_stat), df=n - 1))",
            "    return {'dm_stat': float(dm_stat), 'p_value': float(p_value), 'n': int(n)}",
            "",
            "def select_arima_order(train_series, max_order=2):",
            "    candidates = []",
            "    for d in (0, 1):",
            "        for p in range(max_order + 1):",
            "            for q in range(max_order + 1):",
            "                if p == 0 and d == 0 and q == 0:",
            "                    continue",
            "                caught = []",
            "                try:",
            "                    with warnings.catch_warnings(record=True) as caught:",
            "                        warnings.simplefilter('always')",
            "                        fit = ARIMA(train_series, order=(p, d, q), enforce_stationarity=False, enforce_invertibility=False).fit()",
            "                except Exception:",
            "                    record_model_warnings(caught, f'failed candidate {(p, d, q)}')",
            "                    continue",
            "                record_model_warnings(caught, f'candidate {(p, d, q)}')",
            "                candidates.append({'order': (p, d, q), 'aic': float(fit.aic), 'bic': float(fit.bic)})",
            "    if not candidates:",
            "        raise RuntimeError('Could not estimate any ARIMA candidate.')",
            "    candidates = sorted(candidates, key=lambda item: item['aic'])",
            "    return candidates[0], pd.DataFrame(candidates)",
            "",
            "def rolling_one_step_forecast(train_series, test_series, order):",
            "    history = train_series.copy()",
            "    preds = []",
            "    for idx, actual in test_series.items():",
            "        caught = []",
            "        try:",
            "            with warnings.catch_warnings(record=True) as caught:",
            "                warnings.simplefilter('always')",
            "                fit = ARIMA(history, order=order, enforce_stationarity=False, enforce_invertibility=False).fit()",
            "        finally:",
            "            record_model_warnings(caught, f'rolling {order} at {idx}')",
            "        forecast = fit.forecast(steps=1)",
            "        value = float(forecast.iloc[0] if hasattr(forecast, 'iloc') else forecast[0])",
            "        preds.append(value)",
            "        history = pd.concat([history, pd.Series([actual], index=[idx])])",
            "    return pd.Series(preds, index=test_series.index, name=str(order))",
            "",
            "def bundle_figures_to_pdf(pdf_name='all_figures.pdf'):",
            "    from matplotlib.backends.backend_pdf import PdfPages",
            "    pdf_path = OUTPUT_DIR / pdf_name",
            "    with PdfPages(pdf_path) as pdf:",
            "        for image_path in FIGURE_REGISTRY:",
            "            img = plt.imread(image_path)",
            "            fig, ax = plt.subplots(figsize=(10, 6))",
            "            ax.imshow(img)",
            "            ax.axis('off')",
            "            pdf.savefig(fig, bbox_inches='tight')",
            "            plt.close(fig)",
            "    print(f'Figure bundle written to: {pdf_path}')",
            "    return pdf_path",
        ]
    )


def build_load_cell() -> str:
    return "\n".join(
        [
            "if DATA_PATH is None:",
            "    raise ValueError('Set DATA_PATH before running the notebook.')",
            "",
            "path = Path(DATA_PATH)",
            "if not path.exists():",
            "    raise FileNotFoundError(f'Input data not found: {path}')",
            "",
            "suffix = path.suffix.lower()",
            "if suffix == '.csv':",
            "    raw = pd.read_csv(path)",
            "elif suffix == '.tsv':",
            "    raw = pd.read_csv(path, sep='\\t')",
            "elif suffix in {'.xlsx', '.xls'}:",
            "    raw = pd.read_excel(path)",
            "else:",
            "    raise ValueError(f'Unsupported input format: {suffix}')",
            "",
            "date_col = DATE_COLUMN or detect_date_column(raw)",
            "value_col = VALUE_COLUMN or detect_value_column(raw, date_col)",
            "raw[date_col] = pd.to_datetime(raw[date_col], errors='coerce')",
            "raw = raw.sort_values(date_col).reset_index(drop=True)",
            "series_df = raw[[date_col, value_col]].rename(columns={date_col: 'date', value_col: 'value'})",
            "series_df['value'] = pd.to_numeric(series_df['value'], errors='coerce')",
            "invalid_date_count = int(series_df['date'].isna().sum())",
            "non_numeric_count = int(series_df['value'].isna().sum())",
            "infinite_value_count = int(np.isinf(series_df['value'].to_numpy(dtype=float, na_value=np.nan)).sum())",
            "series_df['value'] = series_df['value'].replace([np.inf, -np.inf], np.nan)",
            "duplicate_date_count = int(series_df.loc[series_df['date'].notna(), 'date'].duplicated().sum())",
            "series_df = series_df.dropna(subset=['date', 'value']).drop_duplicates(subset=['date'])",
            "series_df = series_df.set_index('date').asfreq(FREQUENCY)",
            "frequency_gap_count = int(series_df['value'].isna().sum())",
            "series_df['value'] = series_df['value'].interpolate(method='time').ffill().bfill()",
            "series = series_df['value'].astype(float)",
            "if not np.isfinite(series.to_numpy()).all():",
            "    raise ValueError('Non-finite target values remain after cleaning; modeling was blocked.')",
            "cleaning_report = {'invalid_dates': invalid_date_count, 'non_numeric_values': non_numeric_count, 'infinite_values': infinite_value_count, 'duplicate_dates': duplicate_date_count, 'frequency_gaps_filled': frequency_gap_count}",
            "",
            "display(series_df.head())",
            "print({'rows': int(series.shape[0]), 'start': str(series.index.min()), 'end': str(series.index.max()), 'freq': str(series.index.freq), 'cleaning': cleaning_report})",
        ]
    )


def build_plot_series_cell() -> str:
    return "\n".join(
        [
            "plt.figure(figsize=(10, 4.5))",
            "series.plot(color='tab:blue', linewidth=1.8)",
            "plt.title('Full time series')",
            "plt.xlabel('Date')",
            "plt.ylabel('Value')",
            "save_current_figure('01_full_series.png')",
            "plt.show()",
        ]
    )


def build_split_cell() -> str:
    return "\n".join(
        [
            "if TEST_HORIZON <= 0 or TEST_HORIZON >= len(series):",
            "    raise ValueError('TEST_HORIZON must be smaller than the available series length.')",
            "",
            "train = series.iloc[:-TEST_HORIZON].copy()",
            "test = series.iloc[-TEST_HORIZON:].copy()",
            "if len(train) < 8:",
            "    raise ValueError('Training split has fewer than 8 observations after cleaning and resampling.')",
            "",
            "plt.figure(figsize=(10, 4.5))",
            "train.plot(label='Train', color='tab:blue')",
            "test.plot(label='Test', color='tab:orange')",
            "plt.axvline(test.index.min(), color='black', linestyle='--', linewidth=1)",
            "plt.title('Train/Test split')",
            "plt.legend()",
            "save_current_figure('02_train_test_split.png')",
            "plt.show()",
            "",
            "print({'train_n': int(train.shape[0]), 'test_n': int(test.shape[0])})",
        ]
    )


def build_identification_cell() -> str:
    return "\n".join(
        [
            "diagnostic_lags = max(1, min(24, len(train) // 2 - 1))",
            "fig, axes = plt.subplots(1, 2, figsize=(12, 4))",
            "plot_acf(train, ax=axes[0], lags=diagnostic_lags)",
            "plot_pacf(train, ax=axes[1], lags=diagnostic_lags, method='ywm')",
            "axes[0].set_title('ACF on train')",
            "axes[1].set_title('PACF on train')",
            "save_current_figure('03_acf_pacf.png')",
            "plt.show()",
            "",
            "best_model, candidate_table = select_arima_order(train, max_order=2)",
            "display(candidate_table.head(10))",
            "print({'selected_order': best_model['order'], 'selected_aic': best_model['aic']})",
        ]
    )


def build_forecast_eval_cell() -> str:
    return "\n".join(
        [
            "selected_order = tuple(best_model['order'])",
            "ar_order = (2, selected_order[1], 0)",
            "ma_order = (0, selected_order[1], 2)",
            "",
            "pred_arima = rolling_one_step_forecast(train, test, selected_order)",
            "pred_ar2 = rolling_one_step_forecast(train, test, ar_order)",
            "pred_ma2 = rolling_one_step_forecast(train, test, ma_order)",
            "",
            "comparison = pd.DataFrame({",
            "    'observed': test,",
            "    'ARIMA': pred_arima,",
            "    'AR(2)': pred_ar2,",
            "    'MA(2)': pred_ma2,",
            "})",
            "display(comparison)",
            "",
            "plt.figure(figsize=(10, 4.5))",
            "comparison['observed'].plot(label='Observed', color='black', linewidth=2)",
            "comparison['ARIMA'].plot(label=f'ARIMA{selected_order}', color='tab:blue')",
            "comparison['AR(2)'].plot(label=f'AR(2) with d={selected_order[1]}', color='tab:green')",
            "comparison['MA(2)'].plot(label=f'MA(2) with d={selected_order[1]}', color='tab:red')",
            "plt.title('Out-of-sample predictions')",
            "plt.legend()",
            "save_current_figure('04_test_predictions.png')",
            "plt.show()",
        ]
    )


def build_metrics_cell() -> str:
    return "\n".join(
        [
            "metrics = []",
            "for name in ['ARIMA', 'AR(2)', 'MA(2)']:",
            "    preds = comparison[name]",
            "    errors = comparison['observed'] - preds",
            "    metrics.append({",
            "        'model': name,",
            "        'mae': float(mean_absolute_error(comparison['observed'], preds)),",
            "        'rmse': float(np.sqrt(mean_squared_error(comparison['observed'], preds))),",
            "        'msfe': float(msfe(comparison['observed'], preds)),",
            "    })",
            "metrics_df = pd.DataFrame(metrics).sort_values('rmse').reset_index(drop=True)",
            "display(metrics_df)",
            "metrics_df.to_csv(OUTPUT_DIR / 'metrics_summary.csv', index=False)",
            "",
            "errors_arima = comparison['observed'] - comparison['ARIMA']",
            "errors_ar2 = comparison['observed'] - comparison['AR(2)']",
            "errors_ma2 = comparison['observed'] - comparison['MA(2)']",
            "",
            "dm_results = pd.DataFrame([",
            "    {'comparison': 'ARIMA vs AR(2)', **diebold_mariano(errors_arima, errors_ar2, power=2)},",
            "    {'comparison': 'ARIMA vs MA(2)', **diebold_mariano(errors_arima, errors_ma2, power=2)},",
            "    {'comparison': 'AR(2) vs MA(2)', **diebold_mariano(errors_ar2, errors_ma2, power=2)},",
            "])",
            "display(dm_results)",
            "dm_results.to_csv(OUTPUT_DIR / 'diebold_mariano_results.csv', index=False)",
        ]
    )


def build_final_forecast_cell() -> str:
    return "\n".join(
        [
            "with warnings.catch_warnings(record=True) as caught:",
            "    warnings.simplefilter('always')",
            "    final_fit = ARIMA(series, order=selected_order, enforce_stationarity=False, enforce_invertibility=False).fit()",
            "record_model_warnings(caught, f'final {selected_order}')",
            "future_forecast = final_fit.forecast(steps=TEST_HORIZON)",
            "future_df = future_forecast.rename('forecast').to_frame()",
            "forecast_output = OUTPUT_DIR / f'future_{TEST_HORIZON}_step_forecast.csv'",
            "future_df.to_csv(forecast_output)",
            "display(future_df)",
            "",
            "plt.figure(figsize=(10, 4.5))",
            "series.plot(label='Observed', color='tab:blue')",
            "future_df['forecast'].plot(label='Forecast', color='tab:orange')",
            "plt.axvline(series.index.max(), color='black', linestyle='--', linewidth=1)",
            "plt.title('Final forecast')",
            "plt.legend()",
            "save_current_figure('05_final_forecast.png')",
            "plt.show()",
        ]
    )


def build_export_cell() -> str:
    return "\n".join(
        [
            "bundle_path = bundle_figures_to_pdf('all_figures.pdf')",
            "summary = {",
            "    'selected_arima_order': list(selected_order),",
            "    'test_horizon': int(TEST_HORIZON),",
            "    'figure_files': [str(path) for path in FIGURE_REGISTRY],",
            "    'figure_bundle_pdf': str(bundle_path),",
            "    'metrics_csv': str(OUTPUT_DIR / 'metrics_summary.csv'),",
            "    'dm_csv': str(OUTPUT_DIR / 'diebold_mariano_results.csv'),",
            "    'future_forecast_csv': str(forecast_output),",
            "    'cleaning': cleaning_report,",
            "    'model_warning_count': len(MODEL_WARNINGS),",
            "    'model_warnings_json': str(OUTPUT_DIR / 'model_warnings.json'),",
            "}",
            "with open(OUTPUT_DIR / 'model_warnings.json', 'w', encoding='utf-8') as handle:",
            "    json.dump(MODEL_WARNINGS, handle, indent=2)",
            "print(json.dumps(summary, indent=2))",
            "with open(OUTPUT_DIR / 'run_summary.json', 'w', encoding='utf-8') as handle:",
            "    json.dump(summary, handle, indent=2)",
        ]
    )


def build_notebook(args) -> dict:
    text = TEXT[args.language]
    runtime_body = text["runtime_body_colab"] if args.runtime_profile == "colab" else text["runtime_body_local"]
    cells = [
        md_cell(f"# {args.title}\n\n{text['intro']}"),
        md_cell(f"{text['goals_heading']}\n\n{text['goals_body']}"),
        md_cell(f"{text['runtime_heading']}\n\n{runtime_body}"),
        code_cell(build_setup_cell(args.runtime_profile)),
        code_cell(build_config_cell(args.data_path, args.date_column, args.value_column, args.frequency, args.test_horizon)),
        code_cell(build_helper_cell()),
        md_cell("## Data loading and validation\n\nRead the source data, identify the date and target columns, and build a clean monthly series."),
        code_cell(build_load_cell()),
        md_cell("## First plot\n\nInspect the full series before modeling."),
        code_cell(build_plot_series_cell()),
        md_cell("## Train/test split\n\nLeave the last observations as the hold-out evaluation sample."),
        code_cell(build_split_cell()),
        md_cell("## Identification\n\nUse diagnostics plus a small AIC search to choose an ARIMA order."),
        code_cell(build_identification_cell()),
        md_cell("## Out-of-sample comparison\n\nCompare the selected ARIMA against AR(2) and MA(2) with recursive one-step forecasts."),
        code_cell(build_forecast_eval_cell()),
        md_cell("## Metrics and Diebold-Mariano\n\nCompute MAE, RMSE, MSFE, and compare predictive accuracy with a Diebold-Mariano test."),
        code_cell(build_metrics_cell()),
        md_cell("## Final forecast\n\nRefit the chosen ARIMA on the full sample and project the configured number of future periods."),
        code_cell(build_final_forecast_cell()),
        md_cell(f"{text['results_heading']}\n\n{text['results_body']}"),
        code_cell(build_export_cell()),
        md_cell("## Interpretation\n\nAdd the economic interpretation, caveats, and final conclusion here once the notebook has been executed."),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main():
    args = parse_args()
    collision = find_data_output_collision(args)
    if collision:
        raise SystemExit(
            emit_blocked(args, collision, error_type="output_input_collision", stdout_only=True)
        )
    try:
        raise SystemExit(run_workflow(args))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            raise
        message = clean_known_stderr(str(exc.code)) or "Time-series forecasting scaffold was blocked."
        raise SystemExit(emit_blocked(args, message, error_type="SystemExit")) from None
    except Exception as exc:
        message = clean_known_stderr(f"{exc.__class__.__name__}: {exc}") or f"{exc.__class__.__name__}: {exc}"
        raise SystemExit(emit_blocked(args, message, error_type=exc.__class__.__name__)) from None


def run_workflow(args) -> int:
    output_dir = Path(args.output_dir).expanduser().resolve()
    data_profile, validation_warnings = validate_args(args, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    notebook_path = output_dir / args.notebook_name
    if notebook_path.exists() and not args.overwrite:
        raise SystemExit(f"Notebook already exists: {notebook_path}. Use --overwrite to replace it.")
    notebook = build_notebook(args)
    notebook_path.write_text(json.dumps(notebook, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    summary = sanitize_payload(
        {
            "notebook_path": public_path(notebook_path),
            "output_dir": public_path(output_dir),
            "runtime_profile": args.runtime_profile,
            "language": args.language,
            "data_path": public_path(args.data_path) if args.data_path else None,
            "date_column": args.date_column,
            "value_column": args.value_column,
            "frequency": args.frequency,
            "test_horizon": args.test_horizon,
            "data_profile": data_profile,
            "validation_warnings": validation_warnings,
        }
    )
    status = "warning" if validation_warnings else "ok"
    payload = build_tool_payload(
        "timeseries_forecasting_workbench",
        status=status,
        notes=[
            "This scaffold creates a reproducible forecasting notebook; model adequacy is assessed after notebook execution.",
        ],
        artifacts={
            "summary_json": args.summary_json,
            "manifest_json": args.manifest_json,
            "notebook": public_path(notebook_path),
            "output_dir": public_path(output_dir),
        },
        results=summary,
        qa={
            "status": "warning" if validation_warnings else "ok",
            "findings": validation_warnings,
            "metrics": {
                "test_horizon": args.test_horizon,
                "validation_warning_count": len(validation_warnings),
                "data_rows": data_profile.get("valid_row_count") if data_profile else None,
            },
        },
        legacy=summary,
    )
    emit_payload(payload, args.summary_json)
    if args.manifest_json:
        outputs = [notebook_path]
        if args.summary_json and Path(args.summary_json).exists():
            outputs.append(Path(args.summary_json))
        write_manifest(
            args.manifest_json,
            outputs=outputs,
            parameters={
                "runtime_profile": args.runtime_profile,
                "language": args.language,
                "data_path": args.data_path,
                "date_column": args.date_column,
                "value_column": args.value_column,
                "frequency": args.frequency,
                "test_horizon": args.test_horizon,
            },
            command="timeseries_forecasting_workbench.py",
            notes=[
                "This workbench scaffolds a general forecasting notebook for local or Colab-style execution.",
                "The generated notebook compares an identified ARIMA model against AR(2) and MA(2), exports PNG figures, and bundles them into one PDF.",
            ],
        )
    return 0


if __name__ == "__main__":
    main()

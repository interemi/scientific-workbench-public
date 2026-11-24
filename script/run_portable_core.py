#!/usr/bin/env python3
"""Validate a bundled scientific profile with synthetic inputs in a new external directory."""

import argparse
from csv import DictReader
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys
from zipfile import ZipFile

from check_distribution_snapshot import ROOT, verify
from capability_io_contracts import validate_summary_contract
from setup_environment import installation_environment, validate_profile_readiness


def validate_output(path, root=ROOT):
    path = path.expanduser().absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("output already exists; choose a new directory to preserve evidence")
    if path.resolve().is_relative_to(root.resolve()):
        raise ValueError("output must be outside the source checkout")
    return path


def validate_summary(summary, profile="core"):
    runs = summary.get("feature_runs", {})
    coverage = summary.get("public_surface_coverage", {})
    required_tiers = {"core", "full"} if profile == "full" else {"core"}
    if (summary.get("overall_status") != "PASS" or summary.get("profile") != profile or not runs
            or any(run.get("returncode") != 0 for run in runs.values())
            or coverage.get("missing_coverage") != []
            or not required_tiers.issubset(coverage.get("tiers_enforced", []))):
        raise ValueError(f"{profile} smoke failed, returned no feature runs or has incomplete coverage")
    return len(runs)


def run_io_probe(evidence, environment, name, capability, arguments, expected, *,
                 stdout_target=None, stdout_only=False, summary_option="--summary-json"):
    summary = stdout_target or evidence / f"{name}.json"
    command = [sys.executable, *map(str, arguments), summary_option, str(summary)]
    process = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120)
    (evidence / f"{name}.stdout.log").write_text(process.stdout, encoding="utf-8")
    (evidence / f"{name}.stderr.log").write_text(process.stderr, encoding="utf-8")
    if stdout_only and summary.exists():
        raise ValueError(f"{capability} {name}: unexpectedly wrote a summary file")
    payload = json.loads(process.stdout if stdout_target or stdout_only else summary.read_text(encoding="utf-8"))
    validate_summary_contract(payload, capability=capability)
    status = payload["app_status"]
    if status not in expected.get(process.returncode, set()):
        raise ValueError(f"{capability} {name}: unexpected exit {process.returncode} with {status}")
    return {"returncode": process.returncode, "app_status": status}


def check_core_io_contracts(output, doctor, environment):
    """Exercise the published environment and advisory result shapes."""
    validate_summary_contract(doctor, capability="env_doctor")
    family = ROOT / "skills"
    analysis = family / "scientific-data-analysis/scripts"
    astro = family / "scientific-data-astro/scripts"
    evidence = output / "core-io"
    evidence.mkdir()
    original = evidence / "synthetic-file-hint.pdf"
    marker = b"synthetic file hint only\n"
    original.write_bytes(marker)

    advisory = analysis / "companion_route_check.py"
    external = astro / "external_astro_tools_preflight.py"
    cases = [
        ("discovery", "datanalysis_env.status", analysis / "datanalysis_env.py",
         ["status"], {0: {"PASS", "WARNING"}}),
        ("healthcheck", "datanalysis_healthcheck", analysis / "datanalysis_healthcheck.py",
         ["--skip-notebook-exec"], {0: {"PASS", "WARNING"}, 1: {"BLOCKED_CONTROLADO"}}),
        ("doctor-invalid-output", "env_doctor", analysis / "env_doctor.py",
         ["--manifest-json", str(evidence)], {2: {"BLOCKED_CONTROLADO"}}),
        ("advisory", "companion_route_check", advisory,
         ["--task", "Inspect a scientific report", "--file", str(original)], {0: {"PASS"}}),
        ("advisory-overlap", "companion_route_check", advisory,
         ["--file", str(original)], {2: {"BLOCKED_CONTROLADO"}}),
        ("external-discovery", "external_astro_tools_preflight", external,
         [], {0: {"PASS", "WARNING"}, 2: {"BLOCKED_CONTROLADO"}}),
        ("external-missing-required", "external_astro_tools_preflight", external,
         ["--require-apt", "--apt-command", str(evidence / "missing-apt"),
          "--apt-preferences", str(evidence / "missing.pref")], {2: {"BLOCKED_CONTROLADO"}}),
    ]
    records = {"doctor": {"returncode": 0, "app_status": doctor["app_status"]}}
    for name, capability, script, args, expected in cases:
        records[name] = run_io_probe(
            evidence, environment, name, capability, [script, *args], expected,
            stdout_target=original if name == "advisory-overlap" else None,
        )
    if original.read_bytes() != marker:
        raise ValueError("companion routing modified the synthetic file hint")
    return records


def check_tabular_io_contracts(output, environment):
    scripts = ROOT / "skills/scientific-data-notebooks/scripts"
    evidence = output / "tabular-io"
    sources = evidence / "sources"
    sources.mkdir(parents=True)
    table = sources / "synthetic.csv"
    table.write_text("ra_deg,dec_deg,flux,flux_err\n450,0,3,1\n120,1,2,1\n", encoding="ascii")
    archive = sources / "synthetic.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(table, arcname=table.name)
    branches = sources / "branches"
    branch_tables = [branches / branch / table.name for branch in ("a", "c")]
    for branch_table in branch_tables:
        branch_table.parent.mkdir(parents=True)
        branch_table.write_bytes(table.read_bytes())
    originals = {source: source.read_bytes() for source in [table, archive, *branch_tables]}

    notebook = sources / "generated.ipynb"
    missing = sources / "missing.csv"
    cross_products = evidence / "cross-products"
    branch_products = evidence / "branch-products"
    fidelity_report = evidence / "fidelity.md"
    passed = {0: {"PASS"}}
    warning = {0: {"WARNING"}}
    blocked = {2: {"BLOCKED_CONTROLADO"}}
    failure = {2: {"FAIL"}}
    cases = [
        ("profile", "profile_table", [table], passed),
        ("profile-missing", "profile_table", [missing], failure),
        ("container", "inspect_data_container", [archive], passed),
        ("container-missing", "inspect_data_container", [missing], blocked),
        ("physical", "physical_qa", [table], warning),
        ("physical-missing", "physical_qa", [missing], blocked),
        ("scaffold", "bootstrap_analysis_notebook", [notebook], passed),
        ("scaffold-existing", "bootstrap_analysis_notebook", [notebook], blocked),
        ("fidelity", "coursework_notebook_fidelity_check", [notebook, "--report-md", fidelity_report], warning),
        ("fidelity-missing", "coursework_notebook_fidelity_check", [missing], blocked),
        ("cross-domain", "cross_domain_data_workbench", [table, "--output-dir", cross_products], passed),
        ("cross-domain-missing", "cross_domain_data_workbench", [missing, "--output-dir", evidence / "unused"], failure),
        ("branches", "notebook_branch_compare", [branches, "--output-dir", branch_products], passed),
        ("branches-missing", "notebook_branch_compare", [missing], blocked),
    ]
    records = {}
    for name, capability, args, expected in cases:
        records[name] = run_io_probe(
            evidence, environment, name, capability, [scripts / f"{capability}.py", *args], expected,
        )
        if name == "scaffold":
            originals[notebook] = notebook.read_bytes()
    if any(source.read_bytes() != previous for source, previous in originals.items()):
        raise ValueError("tabular or notebook inspection modified a protected synthetic input")
    generated = json.loads(notebook.read_text(encoding="utf-8"))
    for cell in generated["cells"]:
        if cell["cell_type"] == "code" and (cell["execution_count"] is not None or cell["outputs"]):
            raise ValueError("notebook scaffold unexpectedly contains executed cells")
    expected_reports = (fidelity_report, cross_products / "report.md", branch_products / "branch_product_inventory.csv")
    if not all(report.is_file() for report in expected_reports):
        raise ValueError("a documented tabular or notebook report was not written")
    return records


def check_document_io_contracts(output, environment):
    from docx import Document

    scripts = ROOT / "skills/scientific-data-documents/scripts"
    evidence = output / "document-io"
    sources = evidence / "sources"
    sources.mkdir(parents=True)
    original_docx = sources / "synthetic.docx"
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Stellar flux").bold = True
    paragraph.add_run(" and Stellar flux in a plain run")
    document.save(original_docx)
    baseline = sources / "methods.md"
    baseline.write_text(
        "# Methods\nWe generated synthetic observations and included every sample in the comparison.\n\n"
        "# Results\nThe derived flux was 2 ADU. This demonstration describes a synthetic input only "
        "and makes no claim about an observed astronomical source.\n",
        encoding="utf-8",
    )
    candidate = sources / "revised.md"
    candidate.write_text(baseline.read_text(encoding="utf-8").replace("2 ADU", "3 ADU"), encoding="utf-8")
    before_table = sources / "before.csv"
    after_table = sources / "after.csv"
    before_table.write_text("source,flux\na,2\n", encoding="ascii")
    after_table.write_text("source,flux\na,3\n", encoding="ascii")
    originals = {path: path.read_bytes() for path in sources.iterdir()}

    edited = evidence / "edited.docx"
    replace = [original_docx, edited, "--find", "Stellar flux", "--replace", "Synthetic flux",
               "--require-bold", "--require-confirmation"]
    missing = sources / "missing.md"
    latex = evidence / "latex"
    deliverable = evidence / "deliverable"
    intake = evidence / "intake"
    completed = {0: {"PASS", "WARNING"}}
    blocked = {2: {"BLOCKED_CONTROLADO"}}
    failed = {2: {"FAIL"}}
    cases = [
        ("intake", "document_intake_workbench", [original_docx, baseline, "--output-dir", intake], completed),
        ("intake-missing", "document_intake_workbench", [missing, "--output-dir", evidence / "unused"], blocked),
        ("styles", "office_roundtrip.docx-style-inventory",
         [original_docx, "--require-bold", "--output-csv", evidence / "styles.csv"], completed),
        ("styles-missing", "office_roundtrip.docx-style-inventory", [sources / "missing.docx"], failed),
        ("replacement-unconfirmed", "office_roundtrip.docx-styled-replace", replace, failed),
        ("replacement", "office_roundtrip.docx-styled-replace",
         [*replace, "--confirmation-id", "synthetic-review", "--diff-json", evidence / "style-diff.json"], completed),
        ("latex-scaffold", "latex_workbench.scaffold", [latex, "--title", "Synthetic source"], completed),
        ("latex-existing", "latex_workbench.scaffold", [latex, "--title", "Overwrite probe"], blocked),
        ("latex-review", "latex_workbench.review", [latex, "--report-md", evidence / "latex-review.md"], completed),
        ("latex-missing", "latex_workbench.review", [missing], failed),
        ("writeup", "scientific_writeup_review", [baseline, "--report-md", evidence / "writeup.md"], completed),
        ("writeup-missing", "scientific_writeup_review", [missing], blocked),
        ("deliverable", "deliverable_factory.scaffold", [deliverable, "--title", "Synthetic handoff"], completed),
        ("deliverable-existing", "deliverable_factory.scaffold", [deliverable, "--title", "Overwrite probe"], blocked),
        ("document-diff", "semantic_diff", [baseline, candidate, "--output-md", evidence / "document-diff.md"], completed),
        ("table-diff", "semantic_diff", [before_table, after_table], completed),
        ("diff-missing", "semantic_diff", [baseline, missing], failed),
    ]
    records = {}
    for name, capability, args, expected in cases:
        tool, _, subcommand = capability.partition(".")
        route = [subcommand] if subcommand else []
        records[name] = run_io_probe(
            evidence, environment, name, capability, [scripts / f"{tool}.py", *route, *args], expected,
        )
        if name == "replacement-unconfirmed" and edited.exists():
            raise ValueError("unconfirmed DOCX replacement wrote an edited file")
        if name in {"latex-scaffold", "deliverable"}:
            written = latex if name == "latex-scaffold" else deliverable
            originals.update({path: path.read_bytes() for path in written.iterdir() if path.is_file()})
    if any(path.read_bytes() != content for path, content in originals.items()):
        raise ValueError("a document operation modified a protected synthetic input or scaffold")

    runs = Document(edited).paragraphs[0].runs
    if runs[0].text != "Synthetic flux" or runs[0].bold is not True or runs[1].text != " and Stellar flux in a plain run":
        raise ValueError("DOCX replacement did not preserve the style and the unselected run")
    inventory = json.loads((evidence / "styles.json").read_text(encoding="utf-8"))
    if inventory["results"]["inventory"]["match_count"] != 1:
        raise ValueError("DOCX inventory did not identify exactly one bold run")
    table_diff = json.loads((evidence / "table-diff.json").read_text(encoding="utf-8"))["results"]
    if table_diff["comparison_type"] != "table" or table_diff["cell_change_count"] != 1:
        raise ValueError("semantic diff did not retain the single synthetic table change")
    products = [intake / "inventory.csv", intake / "report.md", evidence / "styles.csv",
                evidence / "style-diff.json", latex / "main.tex", evidence / "latex-review.md",
                evidence / "writeup.md", deliverable / "deliverable.md", evidence / "document-diff.md"]
    if not all(path.is_file() and path.stat().st_size > 0 for path in products):
        raise ValueError("a documented synthetic document output was not written")
    return records


def check_document_preview_io_contracts(output, environment, include_full=False):
    from PIL import Image

    evidence = output / "document-preview-io"
    sources = evidence / "sources"
    sources.mkdir(parents=True)
    figure = sources / "synthetic.png"
    Image.new("RGB", (140, 100), (15, 65, 125)).save(figure)
    package = sources / "synthetic.pages"
    with ZipFile(package, "w") as bundle:
        bundle.write(figure, "preview.png")
        bundle.write(figure, "Data/figure.png")
    originals = {path: path.read_bytes() for path in (figure, package)}
    documents = ROOT / "skills/scientific-data-documents/scripts"
    iwork = documents / "iwork_workbench.py"
    quicklook = documents / "quicklook_bridge.py"
    inventory = evidence / "iwork"
    preview = evidence / "preview.png"
    preflight_output = evidence / "preflight-only.png"
    iwork_manifest = evidence / "iwork-manifest.json"
    preview_manifest = evidence / "preview-manifest.json"
    passed = {0: {"PASS", "WARNING"}}
    blocked = {2: {"BLOCKED_CONTROLADO"}}
    records = {
        "iwork": run_io_probe(evidence, environment, "iwork", "iwork_workbench",
                              [iwork, package, "--output-dir", inventory, "--manifest-json", iwork_manifest],
                              passed, summary_option="--output-json"),
        "iwork-missing": run_io_probe(evidence, environment, "iwork-missing", "iwork_workbench",
                                      [iwork, sources / "missing.pages", "--output-dir", evidence / "missing-iwork"],
                                      blocked, summary_option="--output-json"),
        "quicklook": run_io_probe(evidence, environment, "quicklook", "quicklook_bridge",
                                   [quicklook, figure, "--output", preview, "--size", 320, "--timeout-sec", 10,
                                    "--manifest-json", preview_manifest], passed),
        "quicklook-preflight": run_io_probe(evidence, environment, "quicklook-preflight", "quicklook_bridge",
                                             [quicklook, figure, "--output", preflight_output, "--preflight-only"], passed),
        "quicklook-missing": run_io_probe(evidence, environment, "quicklook-missing", "quicklook_bridge",
                                           [quicklook, sources / "missing.png", "--output", evidence / "missing.png"], blocked),
    }
    summary = json.loads((evidence / "iwork.json").read_text(encoding="utf-8"))["results"]
    if (summary["member_count"] != 2 or summary["image_asset_count"] != 2
            or summary["preview_files"] != ["preview.png"] or not (inventory / "member_manifest.csv").is_file()):
        raise ValueError("iWork inventory did not retain both synthetic ZIP members")
    with Image.open(preview) as thumbnail:
        if thumbnail.format != "PNG" or min(thumbnail.size) < 1:
            raise ValueError("Quick Look did not produce a readable PNG")
        thumbnail.verify()
    if preflight_output.exists():
        raise ValueError("Quick Look preflight wrote a preview")
    for path, manifest_path in ((package, iwork_manifest), (figure, preview_manifest)):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_record, = manifest["inputs"]
        if source_record["sha256"] != sha256(originals[path]).hexdigest():
            raise ValueError(f"{path.name}: preview manifest lost the source hash")
    if include_full:
        records.update(check_presentation_io_contracts(evidence, sources, figure, documents, environment))
    if any(path.read_bytes() != content for path, content in originals.items()):
        raise ValueError("a document preview workflow modified a protected synthetic input")
    return records


def check_presentation_io_contracts(evidence, sources, figure, documents, environment):
    from pptx import Presentation
    from pptx.util import Inches

    deck = sources / "synthetic.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Synthetic observations"
    slide.shapes.add_picture(str(figure), Inches(1), Inches(2), width=Inches(3))
    presentation.save(deck)
    original = deck.read_bytes()
    tool = documents / "presentation_workbench.py"
    inspect = "presentation_workbench.inspect"
    audit = "presentation_workbench.existing-deck-style-audit"
    report = evidence / "audit"
    manifest_path = evidence / "presentation-manifest.json"
    invalid_report = evidence / "invalid-audit"
    cases = [
        ("presentation", inspect, [tool, "inspect", deck], {0: {"PASS", "WARNING"}}),
        ("presentation-missing", inspect, [tool, "inspect", sources / "missing.pptx"], {2: {"BLOCKED_CONTROLADO"}}),
        ("style-audit", audit, [tool, "existing-deck-style-audit", deck, report, "--reference-slides", "1",
                                "--backend", "soffice", "--rule", "Label synthetic figures",
                                "--manifest-json", manifest_path], {0: {"PASS", "WARNING"}}),
        ("style-invalid", audit, [tool, "existing-deck-style-audit", deck, invalid_report,
                                  "--reference-slides", "9", "--backend", "soffice"], {2: {"BLOCKED_CONTROLADO"}}),
    ]
    records = {name: run_io_probe(evidence, environment, name, capability, arguments, expected)
               for name, capability, arguments, expected in cases}
    inspection = json.loads((evidence / "presentation.json").read_text(encoding="utf-8"))["results"]["inspection"]["inspection"]
    style = json.loads((evidence / "style-audit.json").read_text(encoding="utf-8"))["results"]["style_audit"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_record, = manifest["inputs"]
    if (inspection["slide_count"] != 1 or inspection["slide_titles"] != ["Synthetic observations"]
            or inspection["image_count"] != 1 or style["reference_slide_indices"] != [1]
            or source_record["sha256"] != sha256(original).hexdigest()
            or not (report / "scientific_asset_manifest.json").is_file() or invalid_report.exists()):
        raise ValueError("presentation audit lost structure, selected references or provenance")
    if deck.read_bytes() != original:
        raise ValueError("presentation inspection modified the source deck")
    return records


def check_scientific_workflow_io_contracts(output, environment, include_full=False):
    import numpy as np
    from astropy.io import fits

    evidence = output / "workflow-io"
    sources = evidence / "sources"
    rgb_inputs = sources / "rgb"
    rgb_inputs.mkdir(parents=True)
    for scale, band in enumerate("RGB", start=1):
        image = np.arange(256, dtype=np.float32).reshape(16, 16) * scale
        header = fits.Header({"OBJECT": "SYNTHETIC", "FILTER": band, "EXPTIME": 20})
        fits.PrimaryHDU(image, header).writeto(rgb_inputs / f"{band}.fits")
    spectrum = sources / "spectrum.dat"
    spectrum.write_text("".join(
        f"{6500 + index} {1 - 0.4 * np.exp(-0.15 * (index - 22)**2):.7f}\n"
        for index in range(50)
    ), encoding="ascii")
    series = sources / "series.csv"
    series.write_text("date,value\n" + "".join(
        f"{2020 + index // 12}-{index % 12 + 1:02d}-01,{2 * index + 3}\n"
        for index in range(36)
    ), encoding="ascii")
    core_inputs = {path: path.read_bytes() for path in [*rgb_inputs.iterdir(), spectrum, series]}
    astro = ROOT / "skills/scientific-data-astro/scripts"
    notebooks = ROOT / "skills/scientific-data-notebooks/scripts"
    rgb = astro / "fits_rgb_batch.py"
    ascii_coursework = astro / "spectra_ascii_coursework_workbench.py"
    forecast = notebooks / "timeseries_forecasting_workbench.py"
    forecast_manifest = evidence / "forecast-manifest.json"
    cases = [
        ("rgb", "fits_rgb_batch", [rgb, "--input-root", rgb_inputs, "--output-dir", evidence / "rgb",
                                 "--alignment-mode", "none", "--no-stacks"], {0: {"PASS"}}),
        ("rgb-missing", "fits_rgb_batch", [rgb, "--input-root", sources / "missing",
                                         "--output-dir", evidence / "rgb-missing"], {2: {"BLOCKED_CONTROLADO"}}),
        ("spectrum", "spectra_ascii_coursework_workbench", [ascii_coursework, spectrum, "--output-dir",
                     evidence / "spectrum", "--skip-report-project", "--line-window", "synthetic", 6517, 6527],
         {0: {"WARNING"}}),
        ("spectrum-missing", "spectra_ascii_coursework_workbench", [ascii_coursework, sources / "missing.dat",
                             "--output-dir", evidence / "spectrum-missing", "--skip-report-project"],
         {2: {"BLOCKED_CONTROLADO"}}),
        ("forecast", "timeseries_forecasting_workbench", [forecast, "--data-path", series, "--date-column",
                     "date", "--value-column", "value", "--test-horizon", 6, "--output-dir", evidence / "forecast",
                     "--manifest-json", forecast_manifest], {0: {"PASS"}}),
        ("forecast-invalid", "timeseries_forecasting_workbench", [forecast, "--data-path", series, "--test-horizon",
                             0, "--output-dir", evidence / "forecast-invalid"], {2: {"BLOCKED_CONTROLADO"}}),
    ]
    records = {name: run_io_probe(evidence, environment, name, capability, arguments, expected)
               for name, capability, arguments, expected in cases}

    rgb_summary = json.loads((evidence / "rgb.json").read_text(encoding="utf-8"))["results"]
    if (rgb_summary["counts"]["fits_records"] != 3 or rgb_summary["modes"]["true_rgb"] != 1
            or len(list((evidence / "rgb/rgb_png").glob("*.png"))) != 1):
        raise ValueError("RGB workflow did not produce one visual composite from three filters")
    ascii_summary = json.loads((evidence / "spectrum.json").read_text(encoding="utf-8"))["results"]
    profile, = ascii_summary["spectrum_bundle"]["profiles"]
    feature, = profile["line_windows"]
    if (profile["samples"] != 50 or feature["feature_center"] != 6522
            or not (evidence / "spectrum/spectra_analysis/spectrum_inventory.csv").is_file()):
        raise ValueError("ASCII profile lost the sample count, feature center or inventory artifact")
    forecast_summary = json.loads((evidence / "forecast.json").read_text(encoding="utf-8"))["results"]
    manifest = json.loads(forecast_manifest.read_text(encoding="utf-8"))
    source_record, = manifest["inputs"]
    draft = json.loads((evidence / "forecast/timeseries_forecasting_notebook.ipynb").read_text(encoding="utf-8"))
    if (forecast_summary["data_profile"]["valid_row_count"] != 36 or forecast_summary["test_horizon"] != 6
            or source_record["sha256"] != sha256(core_inputs[series]).hexdigest()
            or any(cell["execution_count"] is not None or cell["outputs"]
                   for cell in draft["cells"] if cell["cell_type"] == "code")):
        raise ValueError("forecast scaffold lost source provenance, holdout settings or unexecuted state")
    if include_full:
        records.update(check_full_workflow_io_contracts(evidence, sources, notebooks, environment))
    if any(path.read_bytes() != content for path, content in core_inputs.items()):
        raise ValueError("a scientific workflow modified a protected synthetic input")
    return records


def check_full_workflow_io_contracts(evidence, sources, scripts, environment):
    table = sources / "query.csv"
    table.write_text("id,flux\n1,2.5\n2,4.0\n", encoding="ascii")
    notebook = sources / "known-answer.ipynb"
    cell = {"cell_type": "code", "id": "known-answer", "metadata": {}, "execution_count": None,
            "outputs": [], "source": ["print(6 * 7)"]}
    draft = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [cell]}
    notebook.write_text(json.dumps(draft), encoding="utf-8")
    original = {path: path.read_bytes() for path in (table, notebook)}
    kernels = evidence / "jupyter"
    kernel = kernels / "kernels" / "workbench-contract"
    kernel.mkdir(parents=True)
    (kernel / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Scientific Workbench contract test", "language": "python",
    }), encoding="utf-8")
    environment = {**environment, "JUPYTER_PATH": str(kernels)}
    duckdb = scripts / "duckdb_workbench.py"
    execute = scripts / "notebook_workbench.py"
    query = evidence / "query-result.csv"
    trusted_output = evidence / "execution"
    untrusted_output = evidence / "untrusted-execution"
    blocked = {2: {"BLOCKED_CONTROLADO"}}
    passed = {0: {"PASS"}}
    records = {
        "duckdb": run_io_probe(evidence, environment, "duckdb", "duckdb_workbench",
                              [duckdb, table, "--sql", "SELECT sum(flux) AS flux_sum FROM source0",
                               "--output", query, "--manifest-json", evidence / "duckdb-manifest.json"], passed),
        "duckdb-missing": run_io_probe(evidence, environment, "duckdb-missing", "duckdb_workbench",
                                      [duckdb, sources / "missing.csv"], blocked),
        "execute-copy": run_io_probe(evidence, environment, "execute-copy", "notebook_workbench.execute-copy",
                                     [execute, "execute-copy", notebook, "--output-dir", trusted_output,
                                      "--kernel-name", "workbench-contract", "--timeout-sec", 30,
                                      "--trust-notebook-code", "--manifest-json", evidence / "execution-manifest.json"], passed),
        "execute-untrusted": run_io_probe(evidence, environment, "execute-untrusted", "notebook_workbench.execute-copy",
                                          [execute, "execute-copy", notebook, "--output-dir", untrusted_output],
                                          blocked, stdout_only=True),
    }
    with query.open(encoding="utf-8", newline="") as stream:
        rows = list(DictReader(stream))
    if len(rows) != 1 or float(rows[0]["flux_sum"]) != 6.5:
        raise ValueError("DuckDB output differs from the synthetic sum")
    executed = json.loads((trusted_output / notebook.name).read_text(encoding="utf-8"))
    result, = executed["cells"][0]["outputs"]
    text = result["text"]
    if "".join(text).strip() != "42" or untrusted_output.exists():
        raise ValueError("notebook execution did not preserve the known answer or the trust gate")
    if any(path.read_bytes() != content for path, content in original.items()):
        raise ValueError("a Full workflow modified a protected synthetic input")
    return records


def check_latex_compile_io_contract(output, environment):
    evidence = output / "latex-compile-io"
    sources = evidence / "sources"
    good = sources / "valid" / "main.tex"
    broken = sources / "invalid" / "main.tex"
    for source in (good, broken):
        source.parent.mkdir(parents=True)
    good.write_text(r"\documentclass{article}\begin{document}Synthetic workbench result\end{document}" + "\n",
                    encoding="ascii")
    broken.write_text(r"\documentclass{article}\begin{document}\undefinedcommand\end{document}" + "\n",
                      encoding="ascii")
    originals = {path: path.read_bytes() for path in (good, broken)}
    script = ROOT / "skills/scientific-data-documents/scripts/latex_workbench.py"
    capability = "latex_workbench.compile"
    build = evidence / "build"
    failed_build = evidence / "failed-build"
    manifest_path = evidence / "compile-manifest.json"
    failure_manifest_path = evidence / "failure-manifest.json"
    records = {
        "compile": run_io_probe(evidence, environment, "compile", capability,
                                [script, "compile", good, "--output-dir", build, "--manifest-json", manifest_path],
                                {0: {"PASS"}}),
    }
    pdf = build / "main.pdf"
    expected_pdf = pdf.read_bytes()
    if not expected_pdf.startswith(b"%PDF-"):
        raise ValueError("LaTeX success did not produce a PDF")
    stale = broken.with_suffix(".pdf")
    stale.write_bytes(expected_pdf)
    originals[stale] = expected_pdf
    records["compile-failed"] = run_io_probe(
        evidence, environment, "compile-failed", capability,
        [script, "compile", broken, "--output-dir", failed_build, "--manifest-json", failure_manifest_path],
        {1: {"FAIL"}},
    )
    records["compiler-unavailable"] = run_io_probe(
        evidence, environment, "compiler-unavailable", capability,
        [script, "compile", good, "--output-dir", evidence / "unavailable", "--latexmk-path", evidence / "missing-latexmk"],
        {1: {"BLOCKED_CONTROLADO"}},
    )
    records["compile-existing"] = run_io_probe(
        evidence, environment, "compile-existing", capability,
        [script, "compile", good, "--output-dir", build], {2: {"BLOCKED_CONTROLADO"}}, stdout_only=True,
    )
    records["compile-source-collision"] = run_io_probe(
        evidence, environment, "compile-source-collision", capability,
        [script, "compile", good, "--output-dir", evidence / "collision"], {2: {"BLOCKED_CONTROLADO"}},
        stdout_target=good,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failure = json.loads(failure_manifest_path.read_text(encoding="utf-8"))
    output_hashes = {Path(item["path"]).name: item["sha256"] for item in manifest["outputs"]}
    if (output_hashes.get("main.pdf") != sha256(expected_pdf).hexdigest()
            or output_hashes.get("compile.json") != sha256((evidence / "compile.json").read_bytes()).hexdigest()):
        raise ValueError("LaTeX manifest lost the PDF or summary hash")
    if (failure["extra"]["compile_result"]["success"] or (failed_build / "main.pdf").exists()
            or any(item["path"].endswith(".pdf") for item in failure["outputs"])):
        raise ValueError("a failed LaTeX build published a PDF")
    if pdf.read_bytes() != expected_pdf or any(path.read_bytes() != content for path, content in originals.items()):
        raise ValueError("LaTeX compilation modified a protected source or existing output")
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", choices=("core", "full"), default="core")
    parser.add_argument("--full-io-contracts", action="store_true",
                        help="also check presentations, DuckDB and notebook execution in an installed Full environment")
    args = parser.parse_args(argv)
    if sys.version_info[:2] != (3, 11):
        raise ValueError("run this script with the prepared Python 3.11 environment")
    output = validate_output(args.output_dir)
    entries = verify()
    output.mkdir(parents=True, exist_ok=False)
    environment = installation_environment()
    environment["DATAANALYSIS_PYTHON"] = sys.executable
    environment["MPLBACKEND"] = "Agg"
    environment["MPLCONFIGDIR"] = str(output / "matplotlib")
    scripts = ROOT / "skills/scientific-data-analysis/scripts"
    commands = [
        [sys.executable, str(scripts / "env_doctor.py"), "--strict-core",
         "--summary-json", str(output / "env-doctor.json")],
        [sys.executable, str(scripts / "portable_smoke_test.py"), "--profile", args.profile,
         "--output-dir", str(output / "artifacts"),
         "--summary-json", str(output / "smoke-summary.json"),
         "--manifest-json", str(output / "smoke-manifest.json")],
        [sys.executable, str(ROOT / "script/check_scientific_known_answers.py"),
         "--output-dir", str(output / "known-answer")],
    ]
    evidence = {"status": "FAIL", "profile": args.profile, "python": sys.version, "platform": platform.platform(),
                "architecture": platform.machine(), "snapshot_entries_before": entries,
                "commands": commands}
    try:
        for index, command in enumerate(commands):
            with (output / f"step-{index + 1}.log").open("w") as log:
                subprocess.run(command, env=environment, cwd=ROOT, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=600)
            if index == 0:
                doctor = json.loads((output / "env-doctor.json").read_text())
                full_io = args.full_io_contracts or args.profile == "full"
                validate_profile_readiness(doctor, "full" if full_io else args.profile)
                evidence["core_io_contracts"] = check_core_io_contracts(output, doctor, environment)
                evidence["tabular_io_contracts"] = check_tabular_io_contracts(output, environment)
                evidence["document_io_contracts"] = check_document_io_contracts(output, environment)
                evidence["document_preview_io_contracts"] = check_document_preview_io_contracts(
                    output, environment, include_full=full_io,
                )
                evidence["scientific_workflow_io_contracts"] = check_scientific_workflow_io_contracts(
                    output, environment, include_full=full_io,
                )
                if args.profile == "full":
                    evidence["latex_compile_io_contract"] = check_latex_compile_io_contract(output, environment)
        summary = json.loads((output / "smoke-summary.json").read_text())
        evidence["passed_features"] = validate_summary(summary, args.profile)
        known_answer = json.loads((output / "known-answer/verification.json").read_text())
        if known_answer.get("status") != "PASS":
            raise ValueError("scientific known-answer checks did not pass")
        evidence["known_answer_status"] = known_answer["status"]
        evidence["known_answer_fits_sha256"] = known_answer["fits"]["input_sha256"]
        evidence["known_answer_crossmatch_sep_arcsec"] = known_answer["crossmatch"]["actual_sep_arcsec"]
        evidence["status"] = "PASS"
    finally:
        # A changed backend is a failure even when all child commands succeeded.
        try:
            evidence["snapshot_entries_after"] = verify()
        except (OSError, ValueError, KeyError) as error:
            evidence.update(status="FAIL", snapshot_error=str(error))
            raise
        finally:
            (output / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Portable {args.profile} PASS: {evidence['passed_features']} features. Evidence: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Portable validation stopped: {error}. New evidence is preserved.", file=sys.stderr)
        raise SystemExit(1)

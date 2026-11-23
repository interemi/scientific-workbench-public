#!/usr/bin/env python3
"""Validate a bundled scientific profile with synthetic inputs in a new external directory."""

import argparse
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


def run_io_probe(evidence, environment, name, capability, arguments, expected, *, stdout_target=None):
    summary = stdout_target or evidence / f"{name}.json"
    command = [sys.executable, *map(str, arguments), "--summary-json", str(summary)]
    process = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=120)
    (evidence / f"{name}.stdout.log").write_text(process.stdout, encoding="utf-8")
    (evidence / f"{name}.stderr.log").write_text(process.stderr, encoding="utf-8")
    payload = json.loads(process.stdout if stdout_target else summary.read_text(encoding="utf-8"))
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", choices=("core", "full"), default="core")
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
                validate_profile_readiness(doctor, args.profile)
                evidence["core_io_contracts"] = check_core_io_contracts(output, doctor, environment)
                evidence["tabular_io_contracts"] = check_tabular_io_contracts(output, environment)
                evidence["document_io_contracts"] = check_document_io_contracts(output, environment)
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

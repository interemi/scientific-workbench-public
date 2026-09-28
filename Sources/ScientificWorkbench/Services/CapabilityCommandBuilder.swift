import Foundation

struct CapabilityCommandBuilder {
  var pythonExecutable: String
  var timeoutSeconds: TimeInterval? = nil

  func build(
    capability: CapabilityEntry,
    request: RunRequest,
    skillRoot: String
  ) throws -> ProcessCommand {
    let effectiveSkillRoot = capability.resolvedSkillRoot(fallback: skillRoot)
    let skillURL = URL(fileURLWithPath: effectiveSkillRoot)
    let envScript = skillURL.appendingPathComponent("scripts/datanalysis_env.py").path
    guard FileManager.default.fileExists(atPath: envScript) else {
      throw CommandBuildError.missingDatanalysisWrapper(envScript)
    }

    var arguments = [envScript, "run-tool", capability.scriptStem]
    if let subcommand = capability.inferredSubcommand {
      arguments.append(subcommand)
    }

    let rawArguments = try ShellWords.split(request.rawArguments)
    if rawArguments.isEmpty {
      arguments.append(contentsOf: try defaultArguments(
        for: capability,
        request: request,
        skillRoot: effectiveSkillRoot
      ))
    } else {
      try FilesystemSafetyPolicy().validateRawArguments(
        rawArguments,
        inputPaths: request.inputPaths,
        runDirectory: request.outputDirectory,
        capabilityID: capability.id,
        skillRoot: effectiveSkillRoot
      )
      arguments.append(contentsOf: rawArguments)
    }

    return ProcessCommand(
      executable: pythonExecutable.isEmpty ? DefaultPaths.systemPython : pythonExecutable,
      arguments: arguments,
      workingDirectory: effectiveSkillRoot,
      timeoutSeconds: timeoutSeconds,
      environmentPolicy: .restricted(allowing: capability.allowedEnvironmentKeys),
      environmentOverrides: SkillPythonEnvironment.overrides(forSkillRoot: effectiveSkillRoot)
    )
  }

  private func defaultArguments(
    for capability: CapabilityEntry,
    request: RunRequest,
    skillRoot: String
  ) throws -> [String] {
    let runURL = URL(fileURLWithPath: request.outputDirectory)
    let artifacts = runURL.appendingPathComponent("artifacts").path
    let summary = runURL.appendingPathComponent("summary.json").path
    let manifest = runURL.appendingPathComponent("manifest.json").path
    let examples = URL(fileURLWithPath: skillRoot).appendingPathComponent("examples").path

    switch capability.id {
    case "datanalysis_env.status":
      return ["--summary-json", summary]
    case "env_doctor", "datanalysis_healthcheck":
      return ["--summary-json", summary, "--manifest-json", manifest]
    case "stilts_workbench":
      return ["preflight", "--summary-json", summary]
    case "apt_workbench":
      return ["preflight", "--summary-json", summary]
    case "external_astro_tools_preflight":
      return ["--summary-json", summary]
    case "office_roundtrip.docx-style-inventory":
      return [
        try firstInput(request),
        "--output-csv", runURL.appendingPathComponent("tables/style_inventory.csv").path,
        "--report-md", runURL.appendingPathComponent("reports/style_inventory.md").path,
        "--summary-json", summary,
      ]
    case "keynote_export":
      return [
        try firstInput(request),
        runURL.appendingPathComponent("previews/keynote_export.pdf").path,
        "--preflight-only",
        "--log-txt", runURL.appendingPathComponent("logs/keynote_preflight.txt").path,
        "--summary-json", summary,
      ]
    case "radial_velocity_workbench.inspect":
      return [
        try firstInput(request),
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "radial_velocity_workbench.validate-manifest":
      return [
        try firstInput(request),
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "photometric_solution":
      let input = try firstInput(request)
      let header = tableHeader(at: input)
      var arguments = [
        input,
        "--inst-mag-col", "inst_mag",
        "--std-mag-col", "std_mag",
        "--airmass-col", "airmass",
      ]
      if header.contains("color_index") {
        arguments += ["--color-col", "color_index", "--include-color-term"]
      }
      if header.contains("offset_err") {
        arguments += ["--error-col", "offset_err"]
      }
      return arguments + [
        "--summary-json", summary,
        "--coefficients-csv", runURL.appendingPathComponent("artifacts/coefficients.csv").path,
        "--residual-csv", runURL.appendingPathComponent("tables/residuals.csv").path,
        "--residual-plot", runURL.appendingPathComponent("previews/residuals.png").path,
        "--report-md", runURL.appendingPathComponent("reports/photometric_solution.md").path,
        "--manifest-json", manifest,
      ]
    case "profile_table":
      return [try preferredTableInput(request), "--summary-json", summary, "--manifest-json", manifest]
    case "inspect_fits":
      return [
        try preferredFITSInput(request),
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "document_intake_workbench":
      return [
        "--output-dir", artifacts,
        "--summary-json", summary,
        "--manifest-json", manifest
      ] + (try allInputs(request))
    case "echelle_multispec_inventory":
      return [
        try preferredFITSRoot(request),
        "--output-dir", artifacts,
        "--report-md",
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "fits_rgb_batch":
      return [
        "--input-root", try preferredFITSRoot(request),
        "--output-dir", artifacts,
        "--clean-derived",
        "--summary-json", summary
      ]
    case "rgb_visual_fits_export":
      return [
        try firstInput(request),
        runURL.appendingPathComponent("artifacts/rgb_visual_export.fits").path,
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "astrometry_net_workbench.preflight":
      return [
        try preferredFITSInput(request),
        "--report-md", runURL.appendingPathComponent("reports/astrometry_preflight.md").path,
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "astrometry_net_workbench.verify-existing-wcs":
      return [
        try preferredFITSInput(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/astrometry_wcs").path,
        "--report-md", runURL.appendingPathComponent("reports/astrometry_wcs.md").path,
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "inspect_data_container":
      return [
        try firstInput(request),
        "--summary-json", summary,
        "--output-json", runURL.appendingPathComponent("container.json").path,
        "--manifest-json", manifest
      ]
    case "coursework_notebook_fidelity_check":
      return [
        try firstInput(request),
        "--report-md", runURL.appendingPathComponent("reports/notebook_fidelity.md").path,
        "--summary-json", summary,
      ]
    case "scientific_writeup_review":
      return [
        try firstInput(request),
        "--report-md", runURL.appendingPathComponent("reports/writeup_review.md").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "presentation_workbench.inspect":
      return [
        try firstInput(request),
        "--backend", "auto",
        "--export-preview-pdf", runURL.appendingPathComponent("previews/presentation_preview.pdf").path,
        "--summary-json", summary,
      ]
    case "presentation_workbench.existing-deck-style-audit":
      return [
        try firstInput(request),
        runURL.appendingPathComponent("artifacts/presentation_style_audit").path,
        "--backend", "auto",
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "iwork_workbench":
      return [
        try firstInput(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/iwork").path,
        "--output-json", runURL.appendingPathComponent("artifacts/iwork.json").path,
        "--contact-sheet", runURL.appendingPathComponent("previews/iwork_contact_sheet.png").path,
        "--html-report", runURL.appendingPathComponent("reports/iwork.html").path,
        "--native-preview", runURL.appendingPathComponent("previews/iwork_quicklook.png").path,
        "--manifest-json", manifest,
      ]
    case "quicklook_bridge":
      return [
        try firstInput(request),
        "--output", runURL.appendingPathComponent("previews/quicklook.png").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "latex_workbench.scaffold":
      return [
        runURL.appendingPathComponent("artifacts/latex_scaffold").path,
        "--title", "Scientific Workbench Report",
        "--author", "Scientific Workbench",
        "--language", "bilingual",
        "--kind", "academic-report",
        "--summary-json", summary,
      ]
    case "latex_workbench.review":
      return [
        try firstInput(request),
        "--report-md", runURL.appendingPathComponent("reports/latex_review.md").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "latex_workbench.compile":
      return [
        try firstInput(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/latex_compile").path,
        "--manifest-json", manifest,
      ]
    case "notebook_branch_compare":
      return [
        try firstInput(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/notebook_branch_compare").path,
        "--summary-json", summary,
      ]
    case "semantic_diff":
      let inputs = try firstTwoInputs(request)
      return inputs + [
        "--output-json", runURL.appendingPathComponent("artifacts/semantic_diff.json").path,
        "--output-md", runURL.appendingPathComponent("reports/semantic_diff.md").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "physical_qa":
      return [
        try firstInput(request),
        "--summary-json", summary,
      ]
    case "deliverable_factory.scaffold":
      return [
        runURL.appendingPathComponent("artifacts/deliverable").path,
        "--kind", "status-report",
        "--format", "markdown",
        "--title", "Scientific Workbench Deliverable",
        "--language", "bilingual",
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "bootstrap_analysis_notebook":
      var arguments = [
        runURL.appendingPathComponent("artifacts/analysis_notebook.ipynb").path,
        "--title", "Scientific Workbench Analysis",
        "--domain", "general",
        "--language", "bilingual",
        "--runtime-profile", "local",
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
      if let input = request.inputPaths.first {
        arguments += ["--data-path", input]
      }
      return arguments
    case "timeseries_forecasting_workbench":
      return [
        "--output-dir", runURL.appendingPathComponent("artifacts/forecasting").path,
        "--title", "Scientific Workbench Forecast",
        "--language", "bilingual",
        "--runtime-profile", "local",
        "--data-path", try firstInput(request),
        "--test-horizon", "12",
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "notebook_workbench.execute-copy":
      return [
        try firstInput(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/notebook_copy").path,
        "--trust-notebook-code",
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "cross_domain_data_workbench":
      return [
        "--output-dir", artifacts,
        "--summary-json", summary,
        "--manifest-json", manifest
      ] + (try allInputs(request))
    case "duckdb_workbench":
      return (try allInputs(request)) + [
        "--output", runURL.appendingPathComponent("tables/duckdb_preview.csv").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "teareduce_router":
      return (try allInputs(request)) + [
        "--summary-json", summary,
      ]
    case "spectra_ascii_coursework_workbench":
      return (try allInputs(request)) + [
        "--output-dir", runURL.appendingPathComponent("artifacts/spectra_coursework").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "legacy_rv_coursework_workbench.analyze":
      return (try allInputs(request)) + [
        "--output-dir", runURL.appendingPathComponent("artifacts/legacy_rv").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "sb2_double_gaussian_workbench.fit":
      return (try allInputs(request)) + [
        "--output-dir", runURL.appendingPathComponent("artifacts/sb2_fit").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "legacy_external_reference_check":
      return [
        "check",
        "--rv-summary", try firstInput(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/external_reference").path,
        "--summary-json", summary,
        "--manifest-json", manifest,
      ]
    case "legacy_spectroscopy_envcheck":
      return [
        try firstInput(request),
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "fxcor_iraf_workbench.prepare-session":
      return [
        try firstInput(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/fxcor_workspace").path,
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "fxcor_iraf_workbench.run-auto":
      return [
        try firstInput(request),
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "istarmod_workbench.inspect-tree":
      return [
        try preferredISTARMODRoot(request),
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "istarmod_workbench.prepare-copy":
      return [
        try preferredISTARMODRoot(request),
        "--output-dir", runURL.appendingPathComponent("artifacts/istarmod_clean_copy").path,
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "li6708_equivalent_width_workbench.measure":
      return [
        try preferredPWAndFITS(request),
        "--output-dir", artifacts,
        "--line-center", "6707.8",
        "--line-label", "Li I 6707.8",
        "--target-name", "PW And",
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "legacy_spectroscopy_report_builder.scaffold":
      return [
        runURL.appendingPathComponent("artifacts/legacy_report").path,
        "--title", "Practica 1 - Espectroscopia optica de alta resolucion",
        "--author", "Scientific Workbench",
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    case "portable_smoke_test":
      return [
        "--output-dir", artifacts,
        "--examples-dir", examples,
        "--profile", "core",
        "--summary-json", summary,
        "--manifest-json", manifest
      ]
    default:
      throw CommandBuildError.needsRawArguments(capability.label)
    }
  }

  private func firstInput(_ request: RunRequest) throws -> String {
    guard let first = request.inputPaths.first else {
      throw CommandBuildError.needsInput
    }
    return first
  }

  private func allInputs(_ request: RunRequest) throws -> [String] {
    guard !request.inputPaths.isEmpty else {
      throw CommandBuildError.needsInput
    }
    return request.inputPaths
  }

  private func firstTwoInputs(_ request: RunRequest) throws -> [String] {
    guard request.inputPaths.count >= 2 else {
      throw CommandBuildError.needsTwoInputs
    }
    return Array(request.inputPaths.prefix(2))
  }

  private func preferredFITSRoot(_ request: RunRequest) throws -> String {
    let first = try firstInput(request)
    let nested = URL(fileURLWithPath: first).appendingPathComponent("fits_p1").path
    if FileManager.default.fileExists(atPath: nested) {
      return nested
    }
    return first
  }

  private func preferredISTARMODRoot(_ request: RunRequest) throws -> String {
    let first = try firstInput(request)
    let nested = URL(fileURLWithPath: first).appendingPathComponent("iSTARMOD").path
    if FileManager.default.fileExists(atPath: nested) {
      return nested
    }
    return first
  }

  private func preferredTableInput(_ request: RunRequest) throws -> String {
    let first = try firstInput(request)
    let calibration = URL(fileURLWithPath: first).appendingPathComponent("FWHM_vsini_datafit.csv").path
    if FileManager.default.fileExists(atPath: calibration) {
      return calibration
    }
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: first, isDirectory: &isDirectory), isDirectory.boolValue else {
      return first
    }
    guard let enumerator = FileManager.default.enumerator(
      at: URL(fileURLWithPath: first),
      includingPropertiesForKeys: [.isRegularFileKey],
      options: [.skipsHiddenFiles]
    ) else {
      return first
    }
    for case let fileURL as URL in enumerator {
      guard ["csv", "tsv", "xlsx", "xls", "parquet"].contains(fileURL.pathExtension.localizedLowercase) else { continue }
      return fileURL.path
    }
    return first
  }

  private func preferredPWAndFITS(_ request: RunRequest) throws -> String {
    let first = try firstInput(request)
    let candidate = URL(fileURLWithPath: first)
      .appendingPathComponent("fits_p1")
      .appendingPathComponent("npwand_n3.fits")
      .path
    if FileManager.default.fileExists(atPath: candidate) {
      return candidate
    }
    return try preferredFITSInput(request)
  }

  private func preferredFITSInput(_ request: RunRequest) throws -> String {
    let first = try firstInput(request)
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: first, isDirectory: &isDirectory), isDirectory.boolValue else {
      return first
    }
    guard let enumerator = FileManager.default.enumerator(
      at: URL(fileURLWithPath: first),
      includingPropertiesForKeys: [.isRegularFileKey],
      options: [.skipsHiddenFiles]
    ) else {
      return first
    }
    for case let fileURL as URL in enumerator {
      guard ["fit", "fits", "fts"].contains(fileURL.pathExtension.localizedLowercase) else { continue }
      return fileURL.path
    }
    return first
  }

  private func tableHeader(at path: String) -> Set<String> {
    guard let line = try? String(contentsOfFile: path, encoding: .utf8)
      .components(separatedBy: .newlines)
      .first(where: { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
    else {
      return []
    }
    return Set(
      line.split(separator: ",")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    )
  }
}

enum CommandBuildError: LocalizedError, Equatable {
  case missingDatanalysisWrapper(String)
  case needsInput
  case needsTwoInputs
  case needsRawArguments(String)

  var errorDescription: String? {
    switch self {
    case .missingDatanalysisWrapper(let path):
      return "Could not find datanalysis_env.py at \(path)."
    case .needsInput:
      return "This guided run needs at least one input file or folder."
    case .needsTwoInputs:
      return "This guided comparison needs a baseline and a candidate."
    case .needsRawArguments(let label):
      return "\(label) needs raw CLI arguments in this first version."
    }
  }
}

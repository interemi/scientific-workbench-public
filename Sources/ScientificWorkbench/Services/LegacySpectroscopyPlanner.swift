import Foundation

struct LegacySpectroscopyPlanner: Sendable {
  func shouldUseDeterministicPlan(prompt: String, inputPaths: [String]) -> Bool {
    guard legacySpectroscopyPracticeRoot(inputPaths) != nil else { return false }
    let lowerPrompt = prompt.localizedLowercase
    let asksForFinalReport = lowerPrompt.contains("pdf") ||
      lowerPrompt.contains("report") ||
      lowerPrompt.contains("informe") ||
      lowerPrompt.contains("producto final") ||
      lowerPrompt.contains("resultado final")
    return asksForPracticeWork(lowerPrompt) && asksForFinalReport
  }

  func planIfNeeded(
    prompt: String,
    inputPaths: [String],
    capabilities: [CapabilityEntry],
    startingSteps: [AgentPlanStep]
  ) -> AgentPlan? {
    let lowerPrompt = prompt.localizedLowercase
    guard let practiceRoot = legacySpectroscopyPracticeRoot(inputPaths),
          asksForPracticeWork(lowerPrompt) else {
      return nil
    }

    var steps = startingSteps
    appendRaw(
      "legacy_spectroscopy_envcheck",
      to: &steps,
      capabilities: capabilities,
      summary: "Check the UCM legacy spectroscopy environment and confirm the original DOCUS tree stays read-only.",
      rawArguments: "\(ShellWords.quote(practiceRoot)) --summary-json {summaryJson} --manifest-json {manifestJson}"
    )
    appendRaw(
      "document_intake_workbench",
      to: &steps,
      capabilities: capabilities,
      summary: "Read the practice PDFs and reference handoff files to extract requirements.",
      rawArguments: "--deep-pdf --max-files 12 --output-dir {artifactsDir} --summary-json {summaryJson} --manifest-json {manifestJson} \(documentIntakeTargets(for: practiceRoot).map(ShellWords.quote).joined(separator: " "))"
    )
    appendRaw(
      "echelle_multispec_inventory",
      to: &steps,
      capabilities: capabilities,
      summary: "Inventory the seven MULTISPE FITS spectra order by order.",
      rawArguments: "\(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("fits_p1").path)) --output-dir {artifactsDir} --report-md --summary-json {summaryJson} --manifest-json {manifestJson}"
    )
    appendRaw(
      "profile_table",
      to: &steps,
      capabilities: capabilities,
      summary: "Profile the FWHM-v sin i calibration table.",
      rawArguments: "\(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("FWHM_vsini_datafit.csv").path)) --summary-json {summaryJson} --manifest-json {manifestJson}"
    )
    appendRaw(
      "istarmod_workbench.inspect-tree",
      to: &steps,
      capabilities: capabilities,
      summary: "Inspect the iSTARMOD tree before copying or running it.",
      rawArguments: "\(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("iSTARMOD").path)) --summary-json {summaryJson} --manifest-json {manifestJson}"
    )
    appendRaw(
      "istarmod_workbench.prepare-copy",
      to: &steps,
      capabilities: capabilities,
      summary: "Prepare a clean iSTARMOD copy outside DOCUS so stale outputs and broken venvs do not pollute the run.",
      rawArguments: "\(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("iSTARMOD").path)) --output-dir {artifactsDir}/istarmod_clean_copy --summary-json {summaryJson} --manifest-json {manifestJson}"
    )
    appendRaw(
      "fxcor_iraf_workbench.prepare-session",
      to: &steps,
      capabilities: capabilities,
      summary: "Create a safe IRAF/fxcor workspace for RV and v sin i coursework passes.",
      rawArguments: "\(ShellWords.quote(practiceRoot)) --output-dir {artifactsDir}/fxcor_workspace --summary-json {summaryJson} --manifest-json {manifestJson}"
    )
    appendRaw(
      "fxcor_iraf_workbench.run-auto",
      to: &steps,
      capabilities: capabilities,
      summary: "Run the automatic fxcor batches from the prepared workspace.",
      rawArguments: "{previousArtifactsDir}/fxcor_workspace --summary-json {summaryJson} --manifest-json {manifestJson}",
      usesInputs: false,
      usesPreviousOutput: true
    )
    appendRaw(
      "legacy_rv_coursework_workbench.analyze",
      to: &steps,
      capabilities: capabilities,
      summary: "Consolidate fxcor outputs into filtered RV/v sin i tables and summaries.",
      rawArguments: "{previousSummaryJson} --fits-root \(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("fits_p1").path)) --calibration-csv \(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("FWHM_vsini_datafit.csv").path)) --output-dir {artifactsDir} --summary-json {summaryJson} --manifest-json {manifestJson}",
      usesInputs: true,
      usesPreviousOutput: true
    )
    appendRaw(
      "legacy_external_reference_check",
      to: &steps,
      capabilities: capabilities,
      summary: "Compare the derived Practice 1 results against the bundled literature-reference route.",
      rawArguments: "check --rv-summary {previousSummaryJson} --gzleo-fits \(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("fits_p1/nrej1101_foces02_n2.fits").path)) --output-dir {artifactsDir} --summary-json {summaryJson} --manifest-json {manifestJson}",
      usesInputs: true,
      usesPreviousOutput: true
    )
    appendRaw(
      "li6708_equivalent_width_workbench.measure",
      to: &steps,
      capabilities: capabilities,
      summary: "Measure the Li I 6707.8 equivalent width in PW And as an additional activity diagnostic.",
      rawArguments: "\(ShellWords.quote(URL(fileURLWithPath: practiceRoot).appendingPathComponent("fits_p1/npwand_n3.fits").path)) --output-dir {artifactsDir} --line-center 6707.8 --line-label 'Li I 6707.8' --target-name 'PW And' --summary-json {summaryJson} --manifest-json {manifestJson}"
    )
    appendRaw(
      "legacy_spectroscopy_report_builder.scaffold",
      to: &steps,
      capabilities: capabilities,
      summary: "Create the Spanish LaTeX report project that will receive the measured results.",
      rawArguments: "{artifactsDir}/legacy_report --title 'Practica 1 - Espectroscopia optica de alta resolucion' --author 'Scientific Workbench' --summary-json {summaryJson} --manifest-json {manifestJson}",
      usesInputs: false
    )
    appendRaw(
      "legacy_spectroscopy_report_builder.populate",
      to: &steps,
      capabilities: capabilities,
      summary: "Populate the report project with the generated environment, FITS, RV, v sin i, iSTARMOD, EW, and literature-check outputs.",
      rawArguments: "{artifactsDir:legacy_spectroscopy_report_builder.scaffold}/legacy_report --envcheck {summaryJson:legacy_spectroscopy_envcheck} --inventory-summary {summaryJson:echelle_multispec_inventory} --fxcor-summary {summaryJson:fxcor_iraf_workbench.run-auto} --rv-summary {summaryJson:legacy_rv_coursework_workbench.analyze} --istarmod-summary {summaryJson:istarmod_workbench.prepare-copy} --li-summary {summaryJson:li6708_equivalent_width_workbench.measure} --external-reference-summary {summaryJson:legacy_external_reference_check} --summary-json {summaryJson} --manifest-json {manifestJson}",
      usesInputs: false
    )
    appendRaw(
      "latex_workbench.review",
      to: &steps,
      capabilities: capabilities,
      summary: "Review the populated LaTeX report for structure, unresolved figures, citations, and layout risks before compiling.",
      rawArguments: "{artifactsDir:legacy_spectroscopy_report_builder.populate}/legacy_report --report-md {artifactsDir}/latex_review.md --summary-json {summaryJson} --manifest-json {manifestJson}",
      usesInputs: false
    )
    appendRaw(
      "latex_workbench.compile",
      to: &steps,
      capabilities: capabilities,
      summary: "Compile the populated LaTeX project into the final PDF report.",
      rawArguments: "{artifactsDir:legacy_spectroscopy_report_builder.populate}/legacy_report --output-dir {artifactsDir} --manifest-json {manifestJson}",
      usesInputs: false
    )

    return AgentPlan(
      title: "UCM legacy spectroscopy practice workflow",
      rationale: "Detected a DOCUS-style Practice 1 bundle with PDFs, fits_p1, iSTARMOD, and FWHM-v sin i calibration. The plan routes each internal asset to the matching skill capability while writing outputs outside the original folder.",
      steps: steps,
      source: .local
    )
  }

  func legacySpectroscopyPracticeRoot(_ inputPaths: [String]) -> String? {
    for path in inputPaths {
      var isDirectory: ObjCBool = false
      guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory), isDirectory.boolValue else {
        continue
      }
      let root = URL(fileURLWithPath: path)
      let expected = [
        root.appendingPathComponent("fits_p1").path,
        root.appendingPathComponent("iSTARMOD").path,
        root.appendingPathComponent("FWHM_vsini_datafit.csv").path
      ]
      if expected.allSatisfy({ FileManager.default.fileExists(atPath: $0) }) {
        return path
      }
    }
    return nil
  }

  func documentIntakeTargets(for practiceRoot: String) -> [String] {
    let root = URL(fileURLWithPath: practiceRoot)
    let preferred = [
      root.appendingPathComponent("P1_parte1.pdf").path,
      root.appendingPathComponent("P1_parte2.pdf").path
    ].filter { FileManager.default.fileExists(atPath: $0) }

    let htmlFiles = ((try? FileManager.default.contentsOfDirectory(
      at: root,
      includingPropertiesForKeys: [.isRegularFileKey],
      options: [.skipsHiddenFiles]
    )) ?? [])
      .filter { $0.pathExtension.localizedLowercase == "html" }
      .map(\.path)
      .sorted { $0.localizedStandardCompare($1) == .orderedAscending }

    let targets = preferred + htmlFiles
    return targets.isEmpty ? [practiceRoot] : targets
  }

  private func asksForPracticeWork(_ lowerPrompt: String) -> Bool {
    lowerPrompt.contains("práctica") ||
      lowerPrompt.contains("practica") ||
      lowerPrompt.contains("espectros") ||
      lowerPrompt.contains("ucm") ||
      lowerPrompt.contains("docus") ||
      lowerPrompt.contains("fits")
  }

  private func appendRaw(
    _ capabilityID: String,
    to steps: inout [AgentPlanStep],
    capabilities: [CapabilityEntry],
    summary: String,
    rawArguments: String,
    usesInputs: Bool = true,
    usesPreviousOutput: Bool = false
  ) {
    guard capabilities.contains(where: { $0.id == capabilityID }) else { return }
    guard !steps.contains(where: { $0.capabilityID == capabilityID }) else { return }
    steps.append(AgentPlanStep(
      capabilityID: capabilityID,
      summary: summary,
      rawArguments: rawArguments,
      usesInputs: usesInputs,
      usesPreviousOutput: usesPreviousOutput
    ))
  }
}

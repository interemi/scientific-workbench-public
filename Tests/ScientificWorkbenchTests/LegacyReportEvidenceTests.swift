import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func legacyReportEvidenceMappingBuildsReviewedRepeatableArguments() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Legacy-Evidence-\(UUID().uuidString)", isDirectory: true)
    let project = root.appendingPathComponent("legacy_report", isDirectory: true)
    let envcheck = root.appendingPathComponent("envcheck.json")
    let fxcorOne = root.appendingPathComponent("fxcor-one.json")
    let fxcorTwo = root.appendingPathComponent("fxcor-two.json")
    let lithium = root.appendingPathComponent("lithium.json")
    let run = root.appendingPathComponent("run", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: project, withIntermediateDirectories: true)
    try "report\n".write(
      to: project.appendingPathComponent("main.tex"),
      atomically: true,
      encoding: .utf8
    )
    try writeEvidence(tool: "legacy_spectroscopy_envcheck", to: envcheck)
    try writeEvidence(tool: "fxcor_iraf_workbench.run-auto", to: fxcorOne)
    try writeEvidence(tool: "fxcor_iraf_workbench.run-auto", to: fxcorTwo)
    try writeEvidence(tool: "li6708_equivalent_width_workbench.measure", to: lithium)

    let service = LegacyReportEvidenceService()
    let evidence = [envcheck.path, fxcorOne.path, fxcorTwo.path, lithium.path]
    let reviews = try Dictionary(uniqueKeysWithValues: evidence.map {
      ($0, try service.inspect(path: $0))
    })
    let assignments = [
      LegacyReportEvidenceAssignment(path: envcheck.path, role: .environment),
      LegacyReportEvidenceAssignment(path: fxcorOne.path, role: .fxcor),
      LegacyReportEvidenceAssignment(path: fxcorTwo.path, role: .fxcor),
      LegacyReportEvidenceAssignment(path: lithium.path, role: .lithium),
    ]
    let selection = LegacyReportPopulateSelection(
      projectPath: project.path,
      assignments: assignments,
      mappingConfirmed: true
    )
    let attached = [project.path] + evidence

    #expect(service.validate(
      selection: selection,
      attachedInputPaths: attached,
      reviews: reviews
    ).status == .pass)

    let prepared = try service.prepare(
      selection: selection,
      attachedInputPaths: attached,
      reviews: reviews
    )
    let arguments = prepared.arguments(runURL: run)
    #expect(arguments.first == project.path)
    #expect(arguments.filter { $0 == "--fxcor-summary" }.count == 2)
    #expect(arguments.filter { $0 == "--li-summary" }.count == 1)
    #expect(prepared.inputPaths == [project.path, envcheck.path, fxcorOne.path, fxcorTwo.path, lithium.path])
    #expect(arguments.contains(run.appendingPathComponent("summary.json").path))
    #expect(arguments.contains(run.appendingPathComponent("manifest.json").path))

    let skillRoot = try makeScenarioFixture(
      name: "legacy-evidence-guided-builder",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    let rawArguments = arguments.map(ShellWords.quote).joined(separator: " ")
    let stagedArguments = try LegacyReportProjectStagingService().stagePopulateProjectIfNeeded(
      capabilityID: LegacyReportProjectStagingService.populateCapabilityID,
      rawArguments: rawArguments,
      inputPaths: prepared.inputPaths,
      runDirectory: run.path
    )
    let entry = CapabilityEntry(
      id: LegacyReportProjectStagingService.populateCapabilityID,
      label: "Legacy report populate",
      script: "scripts/legacy_spectroscopy_report_builder.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: true,
      preflightMode: "none",
      smokeTier: "full",
      shortDescription: "Populate an isolated report."
    )
    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: entry,
      request: RunRequest(
        capabilityID: entry.id,
        inputPaths: prepared.inputPaths,
        outputDirectory: run.path,
        rawArguments: stagedArguments
      ),
      skillRoot: skillRoot.path
    )
    #expect(command.arguments.contains(run.appendingPathComponent("artifacts/legacy_report").path))
    #expect(command.arguments.contains(envcheck.path))
    #expect(!command.arguments.contains(project.path))
  }

  @Test
  func legacyReportEvidenceMappingBlocksMismatchedAndUnconfirmedRoles() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Legacy-Evidence-Invalid-\(UUID().uuidString)", isDirectory: true)
    let project = root.appendingPathComponent("legacy_report", isDirectory: true)
    let rv = root.appendingPathComponent("rv.json")
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: project, withIntermediateDirectories: true)
    try "report\n".write(
      to: project.appendingPathComponent("main.tex"),
      atomically: true,
      encoding: .utf8
    )
    try writeEvidence(tool: "legacy_rv_coursework_workbench.analyze", to: rv)

    let service = LegacyReportEvidenceService()
    let review = try service.inspect(path: rv.path)
    let attached = [project.path, rv.path]
    let wrongRole = LegacyReportPopulateSelection(
      projectPath: project.path,
      assignments: [LegacyReportEvidenceAssignment(path: rv.path, role: .environment)],
      mappingConfirmed: true
    )
    let mismatch = service.validate(
      selection: wrongRole,
      attachedInputPaths: attached,
      reviews: [rv.path: review]
    )
    #expect(mismatch.status == .blocked)
    #expect(mismatch.findings.first?.contains("does not match") == true)

    let unconfirmed = LegacyReportPopulateSelection(
      projectPath: project.path,
      assignments: [LegacyReportEvidenceAssignment(path: rv.path, role: .radialVelocity)],
      mappingConfirmed: false
    )
    let needsReview = service.validate(
      selection: unconfirmed,
      attachedInputPaths: attached,
      reviews: [rv.path: review]
    )
    #expect(needsReview.status == .blocked)
    #expect(needsReview.findings.first?.contains("confirm") == true)
  }

  private func writeEvidence(tool: String, to url: URL) throws {
    let payload: [String: Any] = [
      "tool": tool,
      "status": "ok",
      "results": [:],
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted])
    try data.write(to: url, options: .atomic)
  }
}

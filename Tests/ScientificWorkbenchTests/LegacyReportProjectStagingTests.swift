import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func legacyReportPopulateStagesAnIsolatedCopyAndRewritesOnlyTheProjectArgument() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Legacy-Staging-\(UUID().uuidString)", isDirectory: true)
    let inputRoot = root.appendingPathComponent("attached input", isDirectory: true)
    let source = inputRoot.appendingPathComponent("legacy report", isDirectory: true)
    let run = root.appendingPathComponent("runs/current", isDirectory: true)
    let sourceReport = source.appendingPathComponent("report.tex")
    defer { try? FileManager.default.removeItem(at: root) }

    try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    try Data("original\n".utf8).write(to: sourceReport, options: [.atomic])

    let summary = run.appendingPathComponent("summary.json")
    let rawArguments = [source.path, "--summary-json", summary.path]
      .map(ShellWords.quote)
      .joined(separator: " ")
    let rewritten = try LegacyReportProjectStagingService().stagePopulateProjectIfNeeded(
      capabilityID: LegacyReportProjectStagingService.populateCapabilityID,
      rawArguments: rawArguments,
      inputPaths: [inputRoot.path],
      runDirectory: run.path
    )
    let arguments = try ShellWords.split(rewritten)
    let staged = run.appendingPathComponent("artifacts/legacy_report", isDirectory: true)

    #expect(arguments == [staged.path, "--summary-json", summary.path])
    #expect(try String(contentsOf: staged.appendingPathComponent("report.tex"), encoding: .utf8) == "original\n")

    try Data("derived\n".utf8).write(
      to: staged.appendingPathComponent("report.tex"),
      options: [.atomic]
    )
    #expect(try String(contentsOf: sourceReport, encoding: .utf8) == "original\n")
  }

  @Test
  func legacyReportPopulateRejectsAProjectContainingSymbolicLinks() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Legacy-Symlink-\(UUID().uuidString)", isDirectory: true)
    let source = root.appendingPathComponent("input/legacy_report", isDirectory: true)
    let external = root.appendingPathComponent("external.txt")
    let run = root.appendingPathComponent("runs/current", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }

    try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    try Data("must stay external\n".utf8).write(to: external, options: [.atomic])
    try FileManager.default.createSymbolicLink(
      at: source.appendingPathComponent("external-link.txt"),
      withDestinationURL: external
    )

    #expect(throws: LegacyReportProjectStagingError.self) {
      try LegacyReportProjectStagingService().stagePopulateProjectIfNeeded(
        capabilityID: LegacyReportProjectStagingService.populateCapabilityID,
        rawArguments: ShellWords.quote(source.path),
        inputPaths: [source.deletingLastPathComponent().path],
        runDirectory: run.path
      )
    }
    #expect(!FileManager.default.fileExists(
      atPath: run.appendingPathComponent("artifacts/legacy_report").path
    ))
  }

  @Test
  func legacyReportStagingLeavesOtherCapabilitiesUntouched() throws {
    let rawArguments = "--sql 'SELECT * FROM source0'"
    let result = try LegacyReportProjectStagingService().stagePopulateProjectIfNeeded(
      capabilityID: "profile_table",
      rawArguments: rawArguments,
      inputPaths: [],
      runDirectory: "/tmp/not-created"
    )
    #expect(result == rawArguments)
  }

  @Test
  func legacyPopulateBuilderAcceptsOnlyTheCurrentRunCopy() throws {
    let skillRoot = try makeScenarioFixture(
      name: "legacy-populate-builder",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Legacy-Builder-\(UUID().uuidString)", isDirectory: true)
    let inputRoot = root.appendingPathComponent("previous-run", isDirectory: true)
    let source = inputRoot.appendingPathComponent("artifacts/legacy_report", isDirectory: true)
    let run = root.appendingPathComponent("current-run", isDirectory: true)
    defer {
      try? FileManager.default.removeItem(at: root)
      try? FileManager.default.removeItem(at: skillRoot)
    }
    try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    try Data("report\n".utf8).write(
      to: source.appendingPathComponent("report.tex"),
      options: [.atomic]
    )
    let originalRaw = ShellWords.quote(source.path)
    let entry = CapabilityEntry(
      id: LegacyReportProjectStagingService.populateCapabilityID,
      label: "Legacy report populate",
      script: "fixtures/legacy_spectroscopy_report_builder.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "full",
      shortDescription: "Populate an isolated legacy report project."
    )
    let builder = CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")

    #expect(throws: FilesystemSafetyError.self) {
      try builder.build(
        capability: entry,
        request: RunRequest(
          capabilityID: entry.id,
          inputPaths: [inputRoot.path],
          outputDirectory: run.path,
          rawArguments: originalRaw
        ),
        skillRoot: skillRoot.path
      )
    }

    let stagedRaw = try LegacyReportProjectStagingService().stagePopulateProjectIfNeeded(
      capabilityID: entry.id,
      rawArguments: originalRaw,
      inputPaths: [inputRoot.path],
      runDirectory: run.path
    )
    let command = try builder.build(
      capability: entry,
      request: RunRequest(
        capabilityID: entry.id,
        inputPaths: [inputRoot.path],
        outputDirectory: run.path,
        rawArguments: stagedRaw
      ),
      skillRoot: skillRoot.path
    )

    #expect(command.arguments.contains("\(run.path)/artifacts/legacy_report"))
    #expect(!command.arguments.contains(source.path))
  }
}

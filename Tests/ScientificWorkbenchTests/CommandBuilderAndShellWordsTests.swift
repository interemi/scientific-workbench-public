import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func shellWordsSplitAndQuote() throws {
    let words = try ShellWords.split(#""/tmp/a file.csv" --flag 'two words'"#)
    #expect(words == ["/tmp/a file.csv", "--flag", "two words"])
    #expect(ShellWords.quote("/tmp/a file.csv") == "'/tmp/a file.csv'")
  }

  @Test
  func quotedLiteralBackslashPathSurvivesIntoCapabilityArguments() throws {
    let roundTripWords = [
      #"A\&A"#,
      #"folder\name"#,
      #"two\\backslashes"#,
      #"O'Brien\paper"#,
      "trailing\\",
    ]
    let encodedWords = roundTripWords.map(ShellWords.quote).joined(separator: " ")
    #expect(try ShellWords.split(encodedWords) == roundTripWords)
    #expect(try ShellWords.split(#"'A\&A'"#) == [#"A\&A"#])
    #expect(try ShellWords.split(#""A\&A""#) == [#"A\&A"#])
    #expect(try ShellWords.split(#"A\\&A"#) == [#"A\&A"#])

    let skillRoot = try makeScenarioFixture(
      name: "literal-backslash-skill",
      files: ["scripts/datanalysis_env.py": "# wrapper\n"]
    )
    let dataRoot = try makeScenarioFixture(
      name: "literal-backslash-input",
      files: [#"inputs/Lopez-Santiago A\&A.html"#: "reference\n"]
    )
    let runParent = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Literal-Backslash-Runs-\(UUID().uuidString)", isDirectory: true)
    let runRoot = runParent.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: runRoot, withIntermediateDirectories: true)
    defer {
      try? FileManager.default.removeItem(at: skillRoot)
      try? FileManager.default.removeItem(at: dataRoot)
      try? FileManager.default.removeItem(at: runParent)
    }

    let input = dataRoot.appendingPathComponent(#"inputs/Lopez-Santiago A\&A.html"#).path
    let summary = runRoot.appendingPathComponent("summary.json").path
    let expectedRawArguments = [input, "--summary-json", summary]
    let rawArguments = expectedRawArguments.map(ShellWords.quote).joined(separator: " ")
    #expect(try ShellWords.split(rawArguments) == expectedRawArguments)

    let capability = CapabilityEntry(
      id: "document_intake_workbench",
      label: "document_intake_workbench.py",
      script: "scripts/document_intake_workbench.py",
      visibleBlock: "documents + reporting",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inspect scientific documents.",
      owningSkillRoot: skillRoot.path,
      owningSkillRole: SkillRootRole.documents.rawValue
    )
    let builder = CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
    let command = try builder.build(
      capability: capability,
      request: RunRequest(
        capabilityID: capability.id,
        inputPaths: [input],
        outputDirectory: runRoot.path,
        rawArguments: rawArguments
      ),
      skillRoot: skillRoot.path
    )

    #expect(Array(command.arguments.dropFirst(3)) == expectedRawArguments)
    #expect(command.arguments.filter { $0 == input }.count == 1)
    #expect(throws: FilesystemSafetyError.self) {
      try builder.build(
        capability: capability,
        request: RunRequest(
          capabilityID: capability.id,
          inputPaths: [],
          outputDirectory: runRoot.path,
          rawArguments: rawArguments
        ),
        skillRoot: skillRoot.path
      )
    }
  }

  @Test
  func commandBuilderCreatesProfileTableCommand() throws {
    let entry = CapabilityEntry(
      id: "profile_table",
      label: "profile_table.py",
      script: "scripts/profile_table.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Profile a table.",
      allowedEnvironmentKeys: ["STILTS_COMMAND", "SERVICE_TOKEN"]
    )
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Tests-\(UUID().uuidString)", isDirectory: true)
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: ["/tmp/data.csv"],
      outputDirectory: tempDir.path,
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(
      pythonExecutable: "/usr/bin/python3",
      timeoutSeconds: 45 * 60
    )
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)
    #expect(command.executable == "/usr/bin/python3")
    #expect(command.arguments.contains("run-tool"))
    #expect(command.arguments.contains("profile_table"))
    #expect(command.arguments.contains("/tmp/data.csv"))
    #expect(command.arguments.contains("--summary-json"))
    let timeoutSeconds = try #require(command.timeoutSeconds)
    #expect(timeoutSeconds == TimeInterval(45 * 60))
    #expect(command.environmentPolicy == .restricted(allowing: ["STILTS_COMMAND", "SERVICE_TOKEN"]))
    let environment = ProcessRunner.sanitizedEnvironment(
      parent: [
        "STILTS_COMMAND": "/opt/tools/stilts",
        "SERVICE_TOKEN": "must-not-leak"
      ],
      policy: command.environmentPolicy
    )
    #expect(environment["STILTS_COMMAND"] == "/opt/tools/stilts")
    #expect(environment["SERVICE_TOKEN"] == nil)
  }

  @Test
  func commandBuilderUsesCapabilityOwningSkillRootAsWorkingDirectory() throws {
    let fallbackRoot = try makeScenarioFixture(
      name: "fallback-skill-root",
      files: ["scripts/datanalysis_env.py": "# fallback\n"]
    )
    let owningRoot = try makeScenarioFixture(
      name: "owning-skill-root",
      files: ["scripts/datanalysis_env.py": "# owner\n"]
    )
    defer {
      try? FileManager.default.removeItem(at: fallbackRoot)
      try? FileManager.default.removeItem(at: owningRoot)
    }
    let entry = CapabilityEntry(
      id: "inspect_fits",
      label: "inspect_fits.py",
      script: "scripts/inspect_fits.py",
      visibleBlock: "astronomy observational",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inspect FITS.",
      owningSkillRoot: owningRoot.path,
      owningSkillRole: SkillRootRole.astro.rawValue
    )
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: ["/tmp/frame.fits"],
      outputDirectory: "/tmp/fits-run",
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: fallbackRoot.path)

    #expect(command.workingDirectory == owningRoot.path)
    #expect(command.arguments.first == owningRoot.appendingPathComponent("scripts/datanalysis_env.py").path)
    #expect(command.arguments.contains("inspect_fits"))
  }

  @Test
  func commandBuilderChoosesNestedTableWhenFolderIsInput() throws {
    let entry = CapabilityEntry(
      id: "profile_table",
      label: "profile_table.py",
      script: "scripts/profile_table.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Profile a table."
    )
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Tests-\(UUID().uuidString)", isDirectory: true)
    let tableURL = tempDir
      .appendingPathComponent("tables", isDirectory: true)
      .appendingPathComponent("measurements.csv")
    try FileManager.default.createDirectory(at: tableURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try "wavelength,flux\n6707.8,0.64\n".write(to: tableURL, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: [tempDir.path],
      outputDirectory: tempDir.appendingPathComponent("run").path,
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)
    #expect(command.arguments.contains { canonicalPath($0) == canonicalPath(tableURL.path) })
    #expect(!command.arguments.contains { canonicalPath($0) == canonicalPath(tempDir.path) })
  }

  @Test
  func commandBuilderCreatesFitsRGBBatchCommand() throws {
    let entry = CapabilityEntry(
      id: "fits_rgb_batch",
      label: "fits_rgb_batch.py",
      script: "scripts/fits_rgb_batch.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: true,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Build RGB FITS products."
    )
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-FitsRGB-\(UUID().uuidString)", isDirectory: true)
    let fitsRoot = tempDir.appendingPathComponent("fits_p1", isDirectory: true)
    try FileManager.default.createDirectory(at: fitsRoot, withIntermediateDirectories: true)
    try Data([0]).write(to: fitsRoot.appendingPathComponent("frame_R.fits"))
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let runURL = tempDir.appendingPathComponent("run", isDirectory: true)
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: [tempDir.path],
      outputDirectory: runURL.path,
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)

    #expect(command.arguments.contains("fits_rgb_batch"))
    #expect(command.arguments.contains("--input-root"))
    #expect(command.arguments.contains { canonicalPath($0) == canonicalPath(fitsRoot.path) })
    #expect(command.arguments.contains("--output-dir"))
    #expect(command.arguments.contains { canonicalPath($0) == canonicalPath(runURL.appendingPathComponent("artifacts").path) })
    #expect(command.arguments.contains("--clean-derived"))
    #expect(command.arguments.contains("--summary-json"))
    #expect(!command.arguments.contains("--manifest-json"))
  }

  @Test
  func commandBuilderCreatesSTILTSPreflightCommand() throws {
    let entry = CapabilityEntry(
      id: "stilts_workbench",
      label: "stilts_workbench.py",
      script: "scripts/stilts_workbench.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "optional",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "explicit",
      smokeTier: "none",
      shortDescription: "Optional STILTS wrapper."
    )
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: [],
      outputDirectory: "/tmp/stilts-preflight",
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)

    #expect(command.arguments.contains("stilts_workbench"))
    #expect(command.arguments.contains("preflight"))
    #expect(command.arguments.contains("--summary-json"))
    #expect(!command.arguments.contains("--manifest-json"))
    #expect(entry.guidedRunRequirement == .noInput)
  }

  @Test
  func commandBuilderCreatesAPTPreflightCommand() throws {
    let entry = CapabilityEntry(
      id: "apt_workbench",
      label: "apt_workbench.py",
      script: "scripts/apt_workbench.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "optional",
      platform: "portable",
      requiresDatanalysis: true,
      preflightMode: "explicit",
      smokeTier: "none",
      shortDescription: "Optional APT wrapper."
    )
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: [],
      outputDirectory: "/tmp/apt-preflight",
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)

    #expect(command.arguments.contains("apt_workbench"))
    #expect(command.arguments.contains("preflight"))
    #expect(command.arguments.contains("--summary-json"))
    #expect(entry.guidedRunRequirement == .noInput)
  }

  @Test
  func commandBuilderCreatesDOCXStyleInventoryCommand() throws {
    let entry = CapabilityEntry(
      id: "office_roundtrip.docx-style-inventory",
      label: "office_roundtrip.py docx-style-inventory",
      script: "scripts/office_roundtrip.py",
      visibleBlock: "documents + reporting",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Inspect explicit DOCX styles."
    )
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: ["/tmp/source.docx"],
      outputDirectory: "/tmp/docx-inventory",
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)

    #expect(command.arguments.contains("office_roundtrip"))
    #expect(command.arguments.contains("docx-style-inventory"))
    #expect(command.arguments.contains("/tmp/source.docx"))
    #expect(command.arguments.contains("--output-csv"))
    #expect(command.arguments.contains("--report-md"))
    #expect(command.arguments.contains("--summary-json"))
    #expect(entry.guidedRunRequirement == .singleInput)
  }

  @Test
  func commandBuilderCreatesKeynotePreflightCommand() throws {
    let entry = CapabilityEntry(
      id: "keynote_export",
      label: "keynote_export.py",
      script: "scripts/keynote_export.py",
      visibleBlock: "documents + reporting",
      kind: "supporting_tool",
      supportLevel: "platform_bound",
      platform: "macos",
      requiresDatanalysis: false,
      preflightMode: "explicit",
      smokeTier: "none",
      shortDescription: "Export a copied deck through Keynote."
    )
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: ["/tmp/copied.key"],
      outputDirectory: "/tmp/keynote-preflight",
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)

    #expect(command.arguments.contains("keynote_export"))
    #expect(command.arguments.contains("/tmp/copied.key"))
    #expect(command.arguments.contains("--preflight-only"))
    #expect(command.arguments.contains("--log-txt"))
    #expect(command.arguments.contains { $0.hasSuffix("/logs/keynote_preflight.txt") })
    #expect(command.arguments.contains("--summary-json"))
    #expect(entry.guidedRunRequirement == .singleInput)
  }

  @Test
  func commandBuilderCreatesReviewedRadialVelocityInspectCommand() throws {
    let entry = CapabilityEntry(
      id: "radial_velocity_workbench.inspect",
      label: "radial_velocity_workbench.py inspect",
      script: "scripts/radial_velocity_workbench.py",
      visibleBlock: "astronomy observational",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inspect radial-velocity inputs."
    )
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: ["/tmp/reviewed.vels"],
      outputDirectory: "/tmp/rv-run",
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)

    #expect(command.arguments.contains("radial_velocity_workbench"))
    #expect(command.arguments.contains("inspect"))
    #expect(command.arguments.contains("/tmp/reviewed.vels"))
    #expect(command.arguments.contains("--summary-json"))
    #expect(command.arguments.contains("--manifest-json"))
    #expect(entry.guidedRunRequirement == .singleInput)
  }

  @Test
  func commandBuilderCreatesReviewedPhotometricSolutionCommand() throws {
    let entry = CapabilityEntry(
      id: "photometric_solution",
      label: "photometric_solution.py",
      script: "scripts/photometric_solution.py",
      visibleBlock: "astronomy observational",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "datanalysis",
      requiresDatanalysis: true,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Fit a first-order photometric calibration."
    )
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Photometric-\(UUID().uuidString)", isDirectory: true)
    let input = root.appendingPathComponent("selected.csv")
    let run = root.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try """
    inst_mag,std_mag,airmass,color_index,offset_err
    12.1,11.0,1.1,0.4,0.02
    12.3,11.2,1.4,0.6,0.02
    12.6,11.4,1.8,0.9,0.03
    """.write(to: input, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: root) }
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: [input.path],
      outputDirectory: run.path,
      rawArguments: ""
    )

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
      .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)

    #expect(command.arguments.contains("photometric_solution"))
    #expect(command.arguments.contains(input.path))
    #expect(command.arguments.contains("--inst-mag-col"))
    #expect(command.arguments.contains("--std-mag-col"))
    #expect(command.arguments.contains("--airmass-col"))
    #expect(command.arguments.contains("--include-color-term"))
    #expect(command.arguments.contains("--error-col"))
    #expect(command.arguments.contains(run.appendingPathComponent("artifacts/coefficients.csv").path))
    #expect(command.arguments.contains(run.appendingPathComponent("tables/residuals.csv").path))
    #expect(command.arguments.contains(run.appendingPathComponent("previews/residuals.png").path))
    #expect(command.arguments.contains(run.appendingPathComponent("reports/photometric_solution.md").path))
    #expect(entry.guidedRunRequirement == .singleInput)
  }

  @Test
  func commandBuilderBlocksUnknownGuidedRun() {
    let entry = CapabilityEntry(
      id: "unknown_tool",
      label: "unknown_tool.py",
      script: "scripts/unknown_tool.py",
      visibleBlock: "core / routing",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Unknown."
    )
    let request = RunRequest(
      capabilityID: entry.id,
      inputPaths: [],
      outputDirectory: "/tmp/run",
      rawArguments: ""
    )

    #expect(throws: CommandBuildError.needsRawArguments("unknown_tool.py")) {
      try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
        .build(capability: entry, request: request, skillRoot: DefaultPaths.motherSkillRoot)
    }
  }

  @Test
  func commandBuilderCreatesGeneralGuidedWorkflowCommands() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-General-Guided-\(UUID().uuidString)", isDirectory: true)
    let run = root.appendingPathComponent("run", isDirectory: true)
    let baseline = root.appendingPathComponent("baseline.csv")
    let candidate = root.appendingPathComponent("candidate.csv")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "id,value\n1,10\n".write(to: baseline, atomically: true, encoding: .utf8)
    try "id,value\n1,11\n".write(to: candidate, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: root) }

    let semanticDiff = CapabilityEntry(
      id: "semantic_diff",
      label: "semantic_diff.py",
      script: "scripts/semantic_diff.py",
      visibleBlock: "documents + reporting",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Compare two inputs."
    )
    let diffCommand = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: semanticDiff,
      request: RunRequest(
        capabilityID: semanticDiff.id,
        inputPaths: [baseline.path, candidate.path],
        outputDirectory: run.path,
        rawArguments: ""
      ),
      skillRoot: DefaultPaths.motherSkillRoot
    )
    #expect(diffCommand.arguments.contains(baseline.path))
    #expect(diffCommand.arguments.contains(candidate.path))
    #expect(diffCommand.arguments.contains("--output-md"))
    #expect(diffCommand.arguments.contains("--manifest-json"))

    let notebook = CapabilityEntry(
      id: "bootstrap_analysis_notebook",
      label: "bootstrap_analysis_notebook.py",
      script: "scripts/bootstrap_analysis_notebook.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Create a notebook."
    )
    let notebookCommand = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: notebook,
      request: RunRequest(
        capabilityID: notebook.id,
        inputPaths: [baseline.path],
        outputDirectory: run.path,
        rawArguments: ""
      ),
      skillRoot: DefaultPaths.motherSkillRoot
    )
    #expect(notebookCommand.arguments.contains { $0.hasSuffix("/artifacts/analysis_notebook.ipynb") })
    #expect(notebookCommand.arguments.contains("--data-path"))
    #expect(notebookCommand.arguments.contains(baseline.path))
    #expect(notebookCommand.arguments.contains("--summary-json"))

    let latexScaffold = CapabilityEntry(
      id: "latex_workbench.scaffold",
      label: "latex_workbench.py scaffold",
      script: "scripts/latex_workbench.py",
      visibleBlock: "documents + reporting",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "full",
      shortDescription: "Create a LaTeX report."
    )
    let latexCommand = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: latexScaffold,
      request: RunRequest(
        capabilityID: latexScaffold.id,
        inputPaths: [],
        outputDirectory: run.path,
        rawArguments: ""
      ),
      skillRoot: DefaultPaths.motherSkillRoot
    )
    #expect(latexCommand.arguments.contains("scaffold"))
    #expect(latexCommand.arguments.contains { $0.hasSuffix("/artifacts/latex_scaffold") })
    #expect(latexCommand.arguments.contains("--summary-json"))

    let presentationInspect = CapabilityEntry(
      id: "presentation_workbench.inspect",
      label: "presentation_workbench.py inspect",
      script: "scripts/presentation_workbench.py",
      visibleBlock: "documents + reporting",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "full",
      shortDescription: "Inspect a copied presentation."
    )
    let presentationCommand = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: presentationInspect,
      request: RunRequest(
        capabilityID: presentationInspect.id,
        inputPaths: [baseline.path],
        outputDirectory: run.path,
        rawArguments: ""
      ),
      skillRoot: DefaultPaths.motherSkillRoot
    )
    #expect(presentationCommand.arguments.contains("inspect"))
    #expect(presentationCommand.arguments.contains("--export-preview-pdf"))
    #expect(presentationCommand.arguments.contains("--summary-json"))
  }

  @Test
  func commandBuilderRejectsSemanticDiffWithOnlyOneInput() {
    let entry = CapabilityEntry(
      id: "semantic_diff",
      label: "semantic_diff.py",
      script: "scripts/semantic_diff.py",
      visibleBlock: "documents + reporting",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Compare two inputs."
    )

    #expect(throws: CommandBuildError.needsTwoInputs) {
      try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
        capability: entry,
        request: RunRequest(
          capabilityID: entry.id,
          inputPaths: ["/tmp/only-one.csv"],
          outputDirectory: "/tmp/semantic-diff",
          rawArguments: ""
        ),
        skillRoot: DefaultPaths.motherSkillRoot
      )
    }
  }

  @Test
  func commandBuilderEnforcesRawArgumentFilesystemBoundary() throws {
    let skillRoot = try makeScenarioFixture(
      name: "raw-filesystem-boundary",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let entry = CapabilityEntry(
      id: "keynote_export",
      label: "keynote_export.py",
      script: "scripts/keynote_export.py",
      visibleBlock: "documents + reporting",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "macos",
      requiresDatanalysis: false,
      preflightMode: "explicit",
      smokeTier: "none",
      shortDescription: "Export a copied deck through Keynote."
    )
    let input = "/Users/researcher/Desktop/original.key"
    let rawArguments = [input, input, "--preflight-only"]
      .map(ShellWords.quote)
      .joined(separator: " ")

    #expect(throws: FilesystemSafetyError.self) {
      try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
        capability: entry,
        request: RunRequest(
          capabilityID: entry.id,
          inputPaths: [input],
          outputDirectory: "/tmp/ScientificWorkbenchRuns/keynote-run",
          rawArguments: rawArguments
        ),
        skillRoot: skillRoot.path
      )
    }
  }

  @Test
  func commandBuilderAllowsCapabilityScopedAPTConfiguration() throws {
    let skillRoot = try makeScenarioFixture(
      name: "apt-configuration-boundary",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let entry = CapabilityEntry(
      id: "apt_workbench",
      label: "apt_workbench.py",
      script: "scripts/apt_workbench.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "optional",
      platform: "portable",
      requiresDatanalysis: true,
      preflightMode: "explicit",
      smokeTier: "none",
      shortDescription: "Optional APT wrapper."
    )
    let run = "/tmp/ScientificWorkbenchRuns/apt-run"
    let rawArguments = [
      "preflight",
      "--apt-command", "/Applications/APT/bin/apt",
      "--apt-preferences", "/Users/researcher/.config/apt/preferences.xml",
      "--summary-json", "\(run)/summary.json",
    ].map(ShellWords.quote).joined(separator: " ")

    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: entry,
      request: RunRequest(
        capabilityID: entry.id,
        inputPaths: [],
        outputDirectory: run,
        rawArguments: rawArguments
      ),
      skillRoot: skillRoot.path
    )

    #expect(command.arguments.contains("--apt-command"))
    #expect(command.arguments.contains("/Applications/APT/bin/apt"))
    #expect(command.arguments.contains("--apt-preferences"))
  }

  @Test
  func duckDBDefaultCommandProvidesSafePreviewWithoutArbitrarySQL() throws {
    let skillRoot = try makeScenarioFixture(
      name: "duckdb-safe-default",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let entry = CapabilityEntry(
      id: "duckdb_workbench",
      label: "duckdb_workbench.py",
      script: "scripts/duckdb_workbench.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "full",
      shortDescription: "Preview attached tables with DuckDB."
    )
    let run = "/tmp/ScientificWorkbenchRuns/duckdb-safe-default"
    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: entry,
      request: RunRequest(
        capabilityID: entry.id,
        inputPaths: ["/tmp/attached.csv"],
        outputDirectory: run,
        rawArguments: ""
      ),
      skillRoot: skillRoot.path
    )

    #expect(command.arguments.contains("/tmp/attached.csv"))
    #expect(command.arguments.contains("--output"))
    #expect(command.arguments.contains("\(run)/tables/duckdb_preview.csv"))
    #expect(command.arguments.contains("--summary-json"))
    #expect(command.arguments.contains("--manifest-json"))
    #expect(!command.arguments.contains("--sql"))
  }

  @Test
  func reviewedM102CapabilitiesBuildConservativeGuidedCommands() throws {
    let skillRoot = try makeScenarioFixture(
      name: "m102-guided-builders",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let run = "/tmp/ScientificWorkbenchRuns/m102-guided-builders"
    let first = "/tmp/source-one.fits"
    let second = "/tmp/source-two.csv"
    let builder = CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")

    struct Scenario {
      let id: String
      let script: String
      let inputs: [String]
      let requiredArguments: [String]
      let forbiddenArguments: [String]
    }

    let scenarios = [
      Scenario(
        id: "external_astro_tools_preflight",
        script: "scripts/external_astro_tools_preflight.py",
        inputs: [],
        requiredArguments: ["--summary-json", "\(run)/summary.json"],
        forbiddenArguments: ["--probe", "--require-stilts", "--require-apt"]
      ),
      Scenario(
        id: "rgb_visual_fits_export",
        script: "scripts/rgb_visual_fits_export.py",
        inputs: [first],
        requiredArguments: [
          first, "\(run)/artifacts/rgb_visual_export.fits", "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: ["--force"]
      ),
      Scenario(
        id: "astrometry_net_workbench.preflight",
        script: "scripts/astrometry_net_workbench.py",
        inputs: [first],
        requiredArguments: [
          "preflight", first, "--report-md", "\(run)/reports/astrometry_preflight.md",
          "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: []
      ),
      Scenario(
        id: "astrometry_net_workbench.verify-existing-wcs",
        script: "scripts/astrometry_net_workbench.py",
        inputs: [first],
        requiredArguments: [
          "verify-existing-wcs", first, "--output-dir", "\(run)/artifacts/astrometry_wcs",
          "--report-md", "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: []
      ),
      Scenario(
        id: "radial_velocity_workbench.validate-manifest",
        script: "scripts/radial_velocity_workbench.py",
        inputs: [first],
        requiredArguments: ["validate-manifest", first, "--summary-json", "--manifest-json"],
        forbiddenArguments: []
      ),
      Scenario(
        id: "iwork_workbench",
        script: "scripts/iwork_workbench.py",
        inputs: [first],
        requiredArguments: [
          first, "--output-dir", "\(run)/artifacts/iwork", "--output-json", "--contact-sheet",
          "--html-report", "--native-preview", "--manifest-json",
        ],
        forbiddenArguments: ["--enable-ocr"]
      ),
      Scenario(
        id: "quicklook_bridge",
        script: "scripts/quicklook_bridge.py",
        inputs: [first],
        requiredArguments: [
          first, "--output", "\(run)/previews/quicklook.png", "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: []
      ),
      Scenario(
        id: "teareduce_router",
        script: "scripts/teareduce_router.py",
        inputs: [first, second],
        requiredArguments: [first, second, "--summary-json", "\(run)/summary.json"],
        forbiddenArguments: ["--intent"]
      ),
      Scenario(
        id: "spectra_ascii_coursework_workbench",
        script: "scripts/spectra_ascii_coursework_workbench.py",
        inputs: [first, second],
        requiredArguments: [
          first, second, "--output-dir", "\(run)/artifacts/spectra_coursework",
          "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: ["--execute-notebook", "--compile-report"]
      ),
      Scenario(
        id: "legacy_rv_coursework_workbench.analyze",
        script: "scripts/legacy_rv_coursework_workbench.py",
        inputs: [first, second],
        requiredArguments: [
          "analyze", first, second, "--output-dir", "\(run)/artifacts/legacy_rv",
          "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: ["--fits-root", "--calibration-csv"]
      ),
      Scenario(
        id: "sb2_double_gaussian_workbench.fit",
        script: "scripts/sb2_double_gaussian_workbench.py",
        inputs: [first, second],
        requiredArguments: [
          "fit", first, second, "--output-dir", "\(run)/artifacts/sb2_fit",
          "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: ["--fxcor-csv", "--min-separation"]
      ),
      Scenario(
        id: "legacy_external_reference_check",
        script: "scripts/legacy_external_reference_check.py",
        inputs: [first],
        requiredArguments: [
          "check", "--rv-summary", first, "--output-dir",
          "\(run)/artifacts/external_reference", "--summary-json", "--manifest-json",
        ],
        forbiddenArguments: ["--gzleo-fits", "--li-summary", "--istarmod-summary"]
      ),
    ]

    for scenario in scenarios {
      let entry = CapabilityEntry(
        id: scenario.id,
        label: scenario.id,
        script: scenario.script,
        visibleBlock: "test",
        kind: "supporting_tool",
        supportLevel: "stable",
        platform: "portable",
        requiresDatanalysis: false,
        preflightMode: "none",
        smokeTier: "none",
        shortDescription: "Reviewed M102 command."
      )
      let command = try builder.build(
        capability: entry,
        request: RunRequest(
          capabilityID: entry.id,
          inputPaths: scenario.inputs,
          outputDirectory: run,
          rawArguments: ""
        ),
        skillRoot: skillRoot.path
      )

      for argument in scenario.requiredArguments {
        #expect(command.arguments.contains(argument), "\(scenario.id) is missing \(argument)")
      }
      for argument in scenario.forbiddenArguments {
        #expect(!command.arguments.contains(argument), "\(scenario.id) unexpectedly includes \(argument)")
      }
    }
  }

  @Test
  func notebookExecuteCopyCommandRequiresExplicitTrustedCodeFlag() throws {
    let skillRoot = try makeScenarioFixture(
      name: "notebook-execution-skill",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    let inputRoot = try makeScenarioFixture(
      name: "notebook-execution-input",
      files: ["reviewed.ipynb": #"{"cells":[],"metadata":{},"nbformat":4,"nbformat_minor":5}"#]
    )
    let runParent = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Notebook-Runs-\(UUID().uuidString)", isDirectory: true)
    let runRoot = runParent.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: runRoot, withIntermediateDirectories: true)
    defer {
      try? FileManager.default.removeItem(at: skillRoot)
      try? FileManager.default.removeItem(at: inputRoot)
      try? FileManager.default.removeItem(at: runParent)
    }

    let entry = CapabilityEntry(
      id: "notebook_workbench.execute-copy",
      label: "notebook_workbench.py execute-copy",
      script: "scripts/notebook_workbench.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "full",
      shortDescription: "Execute an explicitly reviewed notebook copy."
    )
    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: entry,
      request: RunRequest(
        capabilityID: entry.id,
        inputPaths: [inputRoot.appendingPathComponent("reviewed.ipynb").path],
        outputDirectory: runRoot.path,
        rawArguments: ""
      ),
      skillRoot: skillRoot.path
    )

    #expect(command.arguments.contains("notebook_workbench"))
    #expect(command.arguments.contains("execute-copy"))
    #expect(command.arguments.filter { $0 == "--trust-notebook-code" }.count == 1)
  }

  @Test
  func legacyWorkspacePolicyRoutesOnlyPathSensitiveCapabilities() {
    let policy = LegacyWorkspacePolicy(safeWorkspaceRoot: "/tmp/ScientificWorkbenchRuns/LegacyWorkspaces")
    let spacedRoot = "/tmp/Scientific Workbench Runs"
    let compatibleRoot = "/tmp/ScientificWorkbenchRuns"
    let overlyLongRoot = "/tmp/" + String(repeating: "a", count: 80)

    #expect(policy.runRoot(for: "fxcor_iraf_workbench.prepare-session", preferredOutputRoot: spacedRoot) == "/tmp/ScientificWorkbenchRuns/LegacyWorkspaces")
    #expect(policy.runRoot(for: "latex_workbench.compile", preferredOutputRoot: spacedRoot) == "/tmp/ScientificWorkbenchRuns/LegacyWorkspaces")
    #expect(policy.runRoot(for: "profile_table", preferredOutputRoot: spacedRoot) == spacedRoot)
    #expect(policy.runRoot(for: "fxcor_iraf_workbench.prepare-session", preferredOutputRoot: compatibleRoot) == compatibleRoot)
    #expect(policy.runRoot(for: "fxcor_iraf_workbench.prepare-session", preferredOutputRoot: overlyLongRoot) == "/tmp/ScientificWorkbenchRuns/LegacyWorkspaces")
    #expect(policy.isLegacyCompatible(path: "/tmp/ScientificWorkbenchRuns/LegacyWorkspaces"))
    #expect(!policy.isLegacyCompatible(path: "/tmp/Scientific Workbench Runs"))
    #expect(!policy.isLegacyCompatible(path: "/tmp/ScientificWorkbenchRuns/Práctica"))
    #expect(!policy.isLegacyCompatible(path: overlyLongRoot))
  }

  private func canonicalPath(_ path: String) -> String {
    URL(fileURLWithPath: path).resolvingSymlinksInPath().path
  }
}

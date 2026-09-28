import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func dryRunPreviewsLegacyCopyWithoutCreatingOrChangingFiles() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let entries = ["scaffold", "populate"].map { subcommand in
      CapabilityEntry(
        id: "legacy_spectroscopy_report_builder.\(subcommand)", label: "Legacy \(subcommand)",
        script: "scripts/legacy_spectroscopy_report_builder.py", visibleBlock: "astronomy observational",
        kind: "supporting_tool", supportLevel: "stable", platform: "portable",
        requiresDatanalysis: false, preflightMode: "none", smokeTier: "none", shortDescription: "Report fixture."
      )
    }
    let scaffold = entries[0]
    let populate = entries[1]
    let output = skillRoot.appendingPathComponent("planned-runs").path
    for source in ["{previousArtifactsDir}/legacy_report", "{artifactsDir:step1}/legacy_report"] {
      let report = WorkflowDryRunService().buildReport(request: dryRunRequest(
        plan: AgentPlan(title: "Report", rationale: "Preview staging.", steps: [
          AgentPlanStep(capabilityID: scaffold.id, summary: "Scaffold.", rawArguments: "{artifactsDir}/legacy_report", usesInputs: false, usesPreviousOutput: false),
          AgentPlanStep(capabilityID: populate.id, summary: "Populate a copy.", rawArguments: source, usesInputs: false, usesPreviousOutput: true)
        ], source: .local),
        capabilities: entries, inputPaths: [], outputRootPath: output, skillRootPath: skillRoot.path
      ))
      #expect(report.statusMessage == "Dry run passed.")
      #expect(report.report.contains("legacy_spectroscopy_report_builder.populate/artifacts/legacy_report"))
      #expect(!FileManager.default.fileExists(atPath: output))
    }
    #expect(throws: LegacyReportProjectStagingError.self) {
      try LegacyReportProjectStagingService().previewPopulateArgumentsIfNeeded(
        capabilityID: populate.id, rawArguments: "/unattached/report", inputPaths: [], runDirectory: output
      )
    }
  }

  @Test
  @MainActor
  func workflowDryRunServiceBuildsSuccessPreview() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let capability = sampleCapability()
    let report = WorkflowDryRunService().buildReport(
      request: dryRunRequest(
        plan: AgentPlan(
          title: "Dry run table plan",
          rationale: "Validate command build.",
          steps: [
            AgentPlanStep(
              capabilityID: capability.id,
              summary: "Profile table.",
              rawArguments: "",
              usesInputs: true,
              usesPreviousOutput: false
            )
          ],
          source: .local
        ),
        capabilities: [capability],
        inputPaths: ["/tmp/table.csv"],
        skillRootPath: skillRoot.path
      )
    )

    #expect(report.statusMessage == "Dry run passed.")
    #expect(report.report.contains("Dry run for 'Dry run table plan': 1 enabled step."))
    #expect(report.report.contains("No commands were executed and no output folders were created."))
    #expect(report.report.contains("1. OK `profile_table.py`"))
    #expect(report.report.contains("/tmp/table.csv"))
  }

  @Test
  @MainActor
  func workflowDryRunServiceReportsMissingCapability() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let report = WorkflowDryRunService().buildReport(
      request: dryRunRequest(
        plan: AgentPlan(
          title: "Missing capability",
          rationale: "Capability unavailable.",
          steps: [
            AgentPlanStep(
              capabilityID: "missing.tool",
              summary: "Run missing tool.",
              rawArguments: "",
              usesInputs: false,
              usesPreviousOutput: false
            )
          ],
          source: .local
        ),
        capabilities: [],
        inputPaths: [],
        skillRootPath: skillRoot.path
      )
    )

    #expect(report.statusMessage == "Dry run found issues.")
    #expect(report.report.contains("1. BLOCKED `missing.tool`: capability is not available in the current registry."))
  }

  @Test
  @MainActor
  func workflowDryRunServiceReportsMissingInput() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let capability = sampleCapability()
    let report = WorkflowDryRunService().buildReport(
      request: dryRunRequest(
        plan: AgentPlan(
          title: "Missing input",
          rationale: "Should block.",
          steps: [
            AgentPlanStep(
              capabilityID: capability.id,
              summary: "Profile table.",
              rawArguments: "",
              usesInputs: true,
              usesPreviousOutput: false
            )
          ],
          source: .local
        ),
        capabilities: [capability],
        inputPaths: [],
        skillRootPath: skillRoot.path
      )
    )

    #expect(report.statusMessage == "Dry run found issues.")
    #expect(report.report.contains("1. BLOCKED `profile_table.py`: This guided run needs at least one input file or folder."))
  }

  @Test
  @MainActor
  func workflowDryRunServiceResolvesPreviousOutputPreview() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let environment = environmentCapability()
    let table = sampleCapability()
    let report = WorkflowDryRunService().buildReport(
      request: dryRunRequest(
        plan: AgentPlan(
          title: "Previous output",
          rationale: "Second step should use first output.",
          steps: [
            AgentPlanStep(
              capabilityID: environment.id,
              summary: "Check environment.",
              rawArguments: "",
              usesInputs: false,
              usesPreviousOutput: false
            ),
            AgentPlanStep(
              capabilityID: table.id,
              summary: "Profile previous.",
              rawArguments: "{summaryJson:step1}",
              usesInputs: false,
              usesPreviousOutput: true
            )
          ],
          source: .local
        ),
        capabilities: [environment, table],
        inputPaths: [],
        skillRootPath: skillRoot.path
      )
    )

    #expect(report.statusMessage == "Dry run passed.")
    #expect(report.report.contains("1. OK `datanalysis_env.py status`"))
    #expect(report.report.contains("2. OK `profile_table.py`"))
    #expect(report.report.contains("/preview/datanalysis_env.status/summary.json"))
  }

  @Test
  @MainActor
  func workflowDryRunServiceAuthorizesNonAdjacentNamedDependency() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let environment = environmentCapability()
    let table = sampleCapability()
    let fits = expertFITSCapability()
    let report = WorkflowDryRunService().buildReport(
      request: dryRunRequest(
        plan: AgentPlan(
          title: "Non-adjacent named dependency",
          rationale: "The third step consumes the first step through an explicit placeholder.",
          steps: [
            AgentPlanStep(
              capabilityID: environment.id,
              summary: "Create the referenced summary.",
              rawArguments: "",
              usesInputs: false,
              usesPreviousOutput: false
            ),
            AgentPlanStep(
              capabilityID: table.id,
              summary: "Create an unrelated immediate previous run.",
              rawArguments: "",
              usesInputs: true,
              usesPreviousOutput: false
            ),
            AgentPlanStep(
              capabilityID: fits.id,
              summary: "Read the explicitly referenced summary.",
              rawArguments: "{summaryJson:step1}",
              usesInputs: false,
              usesPreviousOutput: false
            )
          ],
          source: .local
        ),
        capabilities: [environment, table, fits],
        inputPaths: ["/tmp/table.csv"],
        skillRootPath: skillRoot.path
      )
    )

    #expect(report.statusMessage == "Dry run passed.")
    #expect(report.report.contains("3. OK `inspect_fits.py`"))
    #expect(report.report.contains("/preview/datanalysis_env.status/summary.json"))
  }

  @Test
  @MainActor
  func workflowDryRunServiceUsesLegacyNoSpaceWorkspacePreview() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let capability = CapabilityEntry(
      id: "fxcor_iraf_workbench.prepare-session",
      label: "fxcor_iraf_workbench.py prepare-session",
      script: "scripts/fxcor_iraf_workbench.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "narrow",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Prepare an IRAF/fxcor workspace."
    )
    let report = WorkflowDryRunService().buildReport(
      request: dryRunRequest(
        plan: AgentPlan(
          title: "Legacy dry run",
          rationale: "Validate safe workspace routing.",
          steps: [
            AgentPlanStep(
              capabilityID: capability.id,
              summary: "Prepare workspace.",
              rawArguments: "",
              usesInputs: true,
              usesPreviousOutput: false
            )
          ],
          source: .local
        ),
        capabilities: [capability],
        inputPaths: ["/tmp/DOCUS"],
        outputRootPath: "/tmp/Scientific Workbench Runs",
        skillRootPath: skillRoot.path
      )
    )

    #expect(report.statusMessage == "Dry run passed.")
    #expect(report.report.contains("1. OK `fxcor_iraf_workbench.py prepare-session`"))
    #expect(report.report.contains("ScientificWorkbenchRuns/LegacyWorkspaces"))
    #expect(report.report.contains("fxcor_workspace"))
    #expect(!report.report.contains("/tmp/Scientific Workbench Runs"))
  }

  @Test
  @MainActor
  func workflowDryRunServiceBlocksUnresolvedPlaceholders() throws {
    let skillRoot = try makeDryRunSkillRoot()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let capability = sampleCapability()
    let report = WorkflowDryRunService().buildReport(
      request: dryRunRequest(
        plan: AgentPlan(
          title: "Incomplete dependency",
          rationale: "Missing step output must block.",
          steps: [
            AgentPlanStep(
              capabilityID: capability.id,
              summary: "Profile a missing prior summary.",
              rawArguments: "--source {summaryJson:missing_step}",
              usesInputs: false,
              usesPreviousOutput: false
            )
          ],
          source: .skillRouter
        ),
        capabilities: [capability],
        inputPaths: [],
        skillRootPath: skillRoot.path
      )
    )

    #expect(report.statusMessage == "Dry run found issues.")
    #expect(report.report.contains("unresolved placeholders {summaryJson:missing_step}"))
    #expect(!report.report.contains("1. OK"))
  }

  @MainActor
  private func dryRunRequest(
    plan: AgentPlan?,
    capabilities: [CapabilityEntry],
    inputPaths: [String],
    outputRootPath: String = "/preview",
    skillRootPath: String
  ) -> WorkflowDryRunService.Request {
    WorkflowDryRunService.Request(
      plan: plan,
      capabilities: capabilities,
      inputPaths: inputPaths,
      pythonExecutable: "/usr/bin/python3",
      timeoutSeconds: 1_800,
      skillRootPath: skillRootPath,
      makeRunDirectory: { capability in
        let runRoot = LegacyWorkspacePolicy.shared.runRoot(
          for: capability.id,
          preferredOutputRoot: outputRootPath
        )
        return URL(fileURLWithPath: runRoot)
          .appendingPathComponent(capability.id, isDirectory: true)
          .path
      },
      resolveRawArguments: { rawArguments, runDirectory, previousRunDirectory, completedRunDirectories in
        dryRunResolveRawArguments(
          rawArguments,
          inputPaths: inputPaths,
          outputRootPath: outputRootPath,
          runDirectory: runDirectory,
          previousRunDirectory: previousRunDirectory,
          completedRunDirectories: completedRunDirectories
        )
      },
      redact: { $0 }
    )
  }

  private func makeDryRunSkillRoot() throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-DryRun-Service-\(UUID().uuidString)", isDirectory: true)
    let scripts = root.appendingPathComponent("scripts", isDirectory: true)
    try FileManager.default.createDirectory(at: scripts, withIntermediateDirectories: true)
    try "#!/usr/bin/env python3\n".write(
      to: scripts.appendingPathComponent("datanalysis_env.py"),
      atomically: true,
      encoding: .utf8
    )
    return root
  }

  private func dryRunResolveRawArguments(
    _ rawArguments: String,
    inputPaths: [String],
    outputRootPath: String,
    runDirectory: String?,
    previousRunDirectory: String?,
    completedRunDirectories: [String: String]
  ) -> String {
    guard !rawArguments.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return rawArguments
    }

    let currentRun = runDirectory ?? outputRootPath
    var replacements: [String: String] = [
      "{outputRoot}": outputRootPath,
      "{runDirectory}": currentRun,
      "{artifactsDir}": URL(fileURLWithPath: currentRun).appendingPathComponent("artifacts").path,
      "{summaryJson}": URL(fileURLWithPath: currentRun).appendingPathComponent("summary.json").path,
      "{manifestJson}": URL(fileURLWithPath: currentRun).appendingPathComponent("manifest.json").path
    ]

    if let previousRunDirectory {
      replacements["{previousRunDirectory}"] = previousRunDirectory
      replacements["{previousArtifactsDir}"] = URL(fileURLWithPath: previousRunDirectory)
        .appendingPathComponent("artifacts")
        .path
      replacements["{previousSummaryJson}"] = URL(fileURLWithPath: previousRunDirectory)
        .appendingPathComponent("summary.json")
        .path
      replacements["{previousManifestJson}"] = URL(fileURLWithPath: previousRunDirectory)
        .appendingPathComponent("manifest.json")
        .path
    }

    for (index, inputPath) in inputPaths.enumerated() {
      replacements["{input\(index)}"] = inputPath
    }

    for (token, completedRunDirectory) in completedRunDirectories {
      replacements["{runDirectory:\(token)}"] = completedRunDirectory
      replacements["{artifactsDir:\(token)}"] = URL(fileURLWithPath: completedRunDirectory)
        .appendingPathComponent("artifacts")
        .path
      replacements["{summaryJson:\(token)}"] = URL(fileURLWithPath: completedRunDirectory)
        .appendingPathComponent("summary.json")
        .path
      replacements["{manifestJson:\(token)}"] = URL(fileURLWithPath: completedRunDirectory)
        .appendingPathComponent("manifest.json")
        .path
    }

    return replacements
      .sorted { $0.key.count > $1.key.count }
      .reduce(rawArguments) { partial, pair in
        partial.replacingOccurrences(of: pair.key, with: ShellWords.quote(pair.value))
      }
  }
}

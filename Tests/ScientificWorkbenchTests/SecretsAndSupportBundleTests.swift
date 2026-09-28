import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func secretsRedactorMasksConfiguredSecrets() {
    let text = "Authorization failed for sk-test-secret-123456789, xai-secret-987654321, and short."
    let redacted = SecretsRedactor.redact(
      text,
      secrets: ["sk-test-secret-123456789", "xai-secret-987654321", "short"]
    )

    #expect(!redacted.contains("sk-test-secret-123456789"))
    #expect(!redacted.contains("xai-secret-987654321"))
    #expect(redacted.contains("[REDACTED]"))
    #expect(redacted.contains("short"))
  }

  @Test
  @MainActor
  func workflowSummaryWritesReadableSafetyEvidenceAndRedactsSecrets() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Workflow-Summary-\(UUID().uuidString)", isDirectory: true)
    let runRoot = outputRoot.appendingPathComponent("run", isDirectory: true)
    let artifactURL = runRoot.appendingPathComponent("artifacts/final.pdf")
    try FileManager.default.createDirectory(
      at: artifactURL.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    try Data("pdf".utf8).write(to: artifactURL)
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.outputRootPath = outputRoot.path
    store.inputPaths = ["/Users/researcher/Desktop/synthetic-input"]
    store.openAIAPIKey = "sk-secret-workflow-summary"

    let capability = CapabilityEntry(
      id: "latex_workbench.compile",
      label: "latex_workbench.py compile",
      script: "scripts/latex_workbench.py",
      visibleBlock: "documents + reporting",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "full",
      shortDescription: "Compile LaTeX."
    )
    var job = JobRecord(capability: capability, runDirectory: runRoot.path)
    job.status = .succeeded
    job.exitCode = 0
    job.artifacts = [
      Artifact(
        path: artifactURL.path,
        relativePath: "artifacts/final.pdf",
        byteCount: Int64(Data("pdf".utf8).count)
      )
    ]
    store.jobs = [job]

    let step = AgentPlanStep(
      capabilityID: "latex_workbench.compile",
      summary: "Compile report.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let plan = AgentPlan(
      title: "Secret sk-secret-workflow-summary plan",
      rationale: "Produce final report.",
      steps: [step],
      source: .local
    )

    let summaryPath = try #require(store.writeWorkflowSummary(
      plan: plan,
      enabledSteps: [step],
      jobIDs: [job.id],
      status: "Workflow finished.",
      startedAt: Date(timeIntervalSince1970: 1_000),
      finishedAt: Date(timeIntervalSince1970: 1_100)
    ))
    let markdown = try String(contentsOfFile: summaryPath, encoding: .utf8)

    #expect(store.lastWorkflowSummaryPath == summaryPath)
    #expect(markdown.contains("Read-Only Inputs"))
    #expect(markdown.contains("PDF Deliverables"))
    #expect(markdown.contains("Original input paths are not modified"))
    #expect(markdown.contains("artifacts/final.pdf"))
    #expect(!markdown.contains("sk-secret-workflow-summary"))
    #expect(markdown.contains("[REDACTED]"))
  }

  @Test
  @MainActor
  func exportSupportBundleWritesRedactedStateAndMarkdown() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Support-Bundle-\(UUID().uuidString)", isDirectory: true)
    let secret = "sk-secret-support-bundle"
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
    let workflowSummaryURL = outputRoot.appendingPathComponent("workflow_summary.md")
    try "Summary \(secret)".write(to: workflowSummaryURL, atomically: true, encoding: .utf8)

    let capability = CapabilityEntry(
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
    let step = AgentPlanStep(
      capabilityID: capability.id,
      summary: "Profile a table with \(secret).",
      rawArguments: "--token \(secret)",
      usesInputs: true,
      usesPreviousOutput: false
    )
    var job = JobRecord(capability: capability, runDirectory: outputRoot.appendingPathComponent("\(secret)-run").path)
    job.status = .failed
    job.exitCode = 2
    job.requestInputPaths = ["/tmp/\(secret)/input.csv"]
    job.requestRawArguments = "--token \(secret)"
    job.command = "python tool --token \(secret)"
    job.stdout = #"{"status": "blocked", "note": "missing \(secret)"}"#
    job.stderr = "stderr \(secret)"
    job.message = "message \(secret)"
    job.artifacts = [
      Artifact(
        path: outputRoot.appendingPathComponent("\(secret)-artifact.csv").path,
        relativePath: "\(secret)-artifact.csv",
        byteCount: 5
      )
    ]

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.outputRootPath = outputRoot.path
    store.capabilities = [capability]
    store.openAIAPIKey = secret
    store.aiProvider = .openAI
    store.cloudAttachmentContextMode = .filenamesOnly
    store.agentStatusMessage = "Failed with \(secret)"
    store.inputPaths = ["/tmp/\(secret)/input.csv"]
    store.environmentStatus = EnvironmentStatus(
      status: "failed",
      skillRoot: "/tmp/\(secret)/skill",
      datanalysisPython: nil,
      datanalysisRoot: nil,
      details: "details \(secret)",
      warnings: ["warning \(secret)"],
      refreshedAt: Date()
    )
    store.ollamaSetupStatus = OllamaSetupStatus(
      cliPath: "/tmp/\(secret)/ollama",
      serverReachable: false,
      installedModels: [],
      targetModel: "qwen3:4b-instruct",
      message: "message \(secret)",
      checkedAt: Date()
    )
    store.aiConnectionStatuses[.openAI] = AIConnectionStatus(
      state: .invalidKey,
      message: "invalid \(secret)",
      checkedAt: Date()
    )
    store.jobs = [job]
    store.agentPlan = AgentPlan(
      title: "Plan \(secret)",
      rationale: "Rationale \(secret)",
      steps: [step],
      source: .local
    )
    store.agentPlanStepExecutions[step.id] = AgentPlanStepExecution(
      stepID: step.id,
      capabilityID: capability.id,
      jobID: job.id,
      status: .failed,
      runDirectory: job.runDirectory,
      finishedAt: Date()
    )
    store.agentChatMessages.append(AgentChatMessage(role: .user, text: "Prompt \(secret)"))
    store.lastWorkflowSummaryPath = workflowSummaryURL.path

    let bundlePath = try #require(store.exportSupportBundle(revealInFinder: false))
    let bundleURL = URL(fileURLWithPath: bundlePath)
    let state = try String(
      contentsOf: bundleURL.appendingPathComponent("state.json"),
      encoding: .utf8
    )
    let markdown = try String(
      contentsOf: bundleURL.appendingPathComponent("support_bundle.md"),
      encoding: .utf8
    )
    let copiedSummary = try String(
      contentsOf: bundleURL.appendingPathComponent("latest_workflow_summary.md"),
      encoding: .utf8
    )

    #expect(FileManager.default.fileExists(atPath: bundleURL.appendingPathComponent("latest_workflow_summary.md").path))
    #expect(state.contains("Scientific Workbench"))
    #expect(markdown.contains("Scientific Workbench Support Bundle"))
    #expect(state.contains(#""setupRecoveryState""#))
    #expect(state.contains(#""cloudAttachmentContextMode" : "filenamesOnly""#))
    #expect(markdown.contains("Setup Recovery"))
    #expect(markdown.contains("Cloud attachment context: Filenames only"))
    #expect(state.contains("[REDACTED]"))
    #expect(markdown.contains("[REDACTED]"))
    #expect(copiedSummary.contains("[REDACTED]"))
    #expect(!state.contains(secret))
    #expect(!markdown.contains(secret))
    #expect(!copiedSummary.contains(secret))
    #expect(store.agentStatusMessage.contains("Exported support bundle"))
  }

}

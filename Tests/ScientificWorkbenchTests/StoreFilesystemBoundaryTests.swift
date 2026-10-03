import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func existingHistoryLoadsWithoutWriteConsentAndSurvivesTheNextJob() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-History-Consent-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: root) }
    let output = root.appendingPathComponent("Documents")
    let historyURL = output.appendingPathComponent(".scientificworkbench/jobs.json")
    let stateURL = output.appendingPathComponent(".scientificworkbench/agent_state.json")
    var previousJob = JobRecord(capability: sampleCapability(), runDirectory: output.appendingPathComponent("old-run").path)
    previousJob.status = .succeeded
    try JobHistoryStore().persist(jobs: [previousJob], to: historyURL)
    let plan = AgentPlan(
      title: "Pending work", rationale: "Retain persisted evidence.",
      steps: [AgentPlanStep(capabilityID: "profile_table", summary: "Review table.", rawArguments: "", usesInputs: true, usesPreviousOutput: false)],
      source: .local, createdAt: Date(timeIntervalSince1970: 1_000)
    )
    try AgentStateStore().persist(
      snapshot: AgentStateSnapshot(agentPlan: plan, stepExecutions: [], lastWorkflowSummaryPath: nil, agentStatusMessage: "Pending work"),
      to: stateURL
    )
    let historyBefore = try Data(contentsOf: historyURL)
    let stateBefore = try Data(contentsOf: stateURL)
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    defaults.set(output.path, forKey: "outputRootPath")
    let store = WorkbenchStore(
      loadSecrets: false, defaults: defaults,
      filesystemSafetyPolicy: FilesystemSafetyPolicy(homeDirectory: root)
    )
    #expect(!store.outputRootRiskApproved)
    #expect(store.jobs.map(\.id) == [previousJob.id])
    #expect(store.agentPlan == plan)
    #expect(try Data(contentsOf: historyURL) == historyBefore)
    #expect(try Data(contentsOf: stateURL) == stateBefore)

    store.outputRootRiskApproved = true
    store.skillRootPath = root.appendingPathComponent("missing-skill").path
    let newJob = await store.run(capability: sampleCapability(), rawArguments: "", inputPathsOverride: [])
    #expect(newJob?.status == .blocked)
    let saved = try #require(try JobHistoryStore().load(from: historyURL))
    #expect(saved.count == 2)
    #expect(saved.contains { $0.id == previousJob.id })
  }

  @Test
  @MainActor
  func unsafeOutputRootBlocksGuidedStagingBeforeFilesystemMutation() async throws {
    let sourceRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Guided-Source-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: sourceRoot, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: sourceRoot) }
    let source = sourceRoot.appendingPathComponent("original.docx")
    try Data("fixture".utf8).write(to: source, options: [.atomic])

    let unsafeRoot = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".ssh/Scientific-Workbench-Guided-\(UUID().uuidString)", isDirectory: true)
    #expect(!FileManager.default.fileExists(atPath: unsafeRoot.path))

    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = unsafeRoot.path
    store.inputPaths = [source.path]
    store.capabilities = [documentInventoryCapability()]

    await store.reviewDOCXStyles()

    #expect(!FileManager.default.fileExists(atPath: unsafeRoot.path))
    #expect(store.jobs.isEmpty)
    #expect(store.documentStyleReview == nil)
    #expect(store.documentStyleError?.contains("Unsafe output root") == true)
  }

  @Test
  @MainActor
  func guidedRunPreparesArtifactParentAfterOutputSafetyCheck() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Guided-Artifacts-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.outputRootPath = root.appendingPathComponent("runs", isDirectory: true).path
    store.skillRootPath = root.appendingPathComponent("missing-skill", isDirectory: true).path

    let job = await store.runGuided(capability: sampleCapability(), inputPathsOverride: []) { runURL in
      [runURL.appendingPathComponent("artifacts/result.csv").path]
    }

    let runDirectory = try #require(job?.runDirectory)
    var isDirectory: ObjCBool = false
    #expect(FileManager.default.fileExists(
      atPath: URL(fileURLWithPath: runDirectory).appendingPathComponent("artifacts").path,
      isDirectory: &isDirectory
    ))
    #expect(isDirectory.boolValue)
    #expect(job?.status == .blocked)
  }

  @Test
  @MainActor
  func unsafeOutputRootBlocksConfigurationExport() {
    let unsafeRoot = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".ssh/Scientific-Workbench-Config-\(UUID().uuidString)", isDirectory: true)
    let destination = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Blocked-Config-\(UUID().uuidString).json")
    defer { try? FileManager.default.removeItem(at: destination) }

    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = unsafeRoot.path

    let exported = store.exportConfiguration(to: destination.path, revealInFinder: false)

    #expect(exported == nil)
    #expect(!FileManager.default.fileExists(atPath: destination.path))
    #expect(store.agentStatusMessage.contains("Unsafe output root"))
  }

  @Test
  @MainActor
  func configurationExportCannotEscapeTheConfiguredOutputRoot() {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Config-Boundary-\(UUID().uuidString)", isDirectory: true)
    let outputRoot = root.appendingPathComponent("output", isDirectory: true)
    let outside = root.appendingPathComponent("outside/config.json")
    defer { try? FileManager.default.removeItem(at: root) }

    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = outputRoot.path

    let exported = store.exportConfiguration(to: outside.path, revealInFinder: false)

    #expect(exported == nil)
    #expect(!FileManager.default.fileExists(atPath: outside.path))
    #expect(store.agentStatusMessage.contains("inside the configured output root"))
  }

  @Test
  @MainActor
  func configurationExportRefusesToOverwriteExistingEvidence() throws {
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Config-No-Overwrite-\(UUID().uuidString)", isDirectory: true)
    let destination = outputRoot.appendingPathComponent("config.json")
    defer { try? FileManager.default.removeItem(at: outputRoot) }
    try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
    try Data("historical configuration\n".utf8).write(to: destination, options: [.atomic])

    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = outputRoot.path

    let exported = store.exportConfiguration(to: destination.path, revealInFinder: false)

    #expect(exported == nil)
    #expect(try String(contentsOf: destination, encoding: .utf8) == "historical configuration\n")
    #expect(store.agentStatusMessage.contains("will not be overwritten"))
  }

  @Test
  @MainActor
  func unrestrictedPersistedCodexModeIsMigratedToReadOnly() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    defaults.set("danger-full-access", forKey: "codexSandboxMode")

    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )

    #expect(store.codexSandboxMode == "read-only")
    store.codexSandboxMode = "danger-full-access"
    store.persistSettings()
    #expect(store.codexSandboxMode == "read-only")
    #expect(defaults.string(forKey: "codexSandboxMode") == "read-only")
  }

  @Test
  @MainActor
  func higherRiskOutputApprovalExpiresWhenAttachedInputsChange() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Desktop", isDirectory: true)
      .path
    store.inputPaths = ["/tmp/first-input.csv"]
    store.outputRootRiskApproved = true

    #expect(store.outputRootRiskApproved)
    store.addInputPath("/tmp/second-input.csv")
    #expect(!store.outputRootRiskApproved)
  }

  @Test
  @MainActor
  func higherRiskOutputApprovalCannotBeReusedForDifferentRunInputs() async {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Desktop", isDirectory: true)
      .path
    store.inputPaths = ["/tmp/approved-input.csv"]
    store.outputRootRiskApproved = true

    let result = await store.run(
      capability: sampleCapability(),
      rawArguments: "",
      inputPathsOverride: ["/tmp/different-input.csv"],
      runDirectoryOverride: "/tmp/Scientific-Workbench-Approval-Scope-\(UUID().uuidString)"
    )

    #expect(result == nil)
    #expect(store.agentStatusMessage.contains("confirm the path in Settings"))
  }

  @Test
  @MainActor
  func cancelControlCoversCodexBridgeAndOllamaPullOperations() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )

    store.isRunningCodexBridge = true
    #expect(store.canCancelActiveRun)
    store.isRunningCodexBridge = false
    store.isPullingOllamaModel = true
    #expect(store.canCancelActiveRun)
  }

  private func documentInventoryCapability() -> CapabilityEntry {
    CapabilityEntry(
      id: "office_roundtrip.docx-style-inventory",
      label: "DOCX style inventory",
      script: "fixtures/office_roundtrip.py",
      visibleBlock: "documents",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inventory DOCX styles without modifying the original."
    )
  }
}

import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func jobHistoryMigrationRecoversValidRecordsAndPreservesExactOriginal() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Job-Recovery-\(UUID().uuidString)", isDirectory: true)
    let stateDirectory = root.appendingPathComponent(".scientificworkbench", isDirectory: true)
    let historyURL = stateDirectory.appendingPathComponent("jobs.json")
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: stateDirectory, withIntermediateDirectories: true)
    defaults.set(root.path, forKey: "outputRootPath")

    let runDirectory = root.appendingPathComponent("run", isDirectory: true)
    let artifactURL = runDirectory.appendingPathComponent("result.csv")
    try FileManager.default.createDirectory(at: runDirectory, withIntermediateDirectories: true)
    try Data("test-result\n".utf8).write(to: artifactURL)

    var job = JobRecord(
      capability: sampleCapability(),
      runDirectory: runDirectory.path,
      createdAt: Date(timeIntervalSince1970: 1_000)
    )
    job.status = .running
    let duplicateArtifact = Artifact(
      id: UUID(),
      path: artifactURL.path,
      relativePath: "result.csv",
      byteCount: 12
    )
    job.artifacts = [duplicateArtifact, duplicateArtifact]
    let duplicateAction = JobNextAction(label: "Review", kind: "open", priority: "high")
    job.nextActions = [duplicateAction, duplicateAction]
    let encodedJob = try persistenceJSONObject(job)
    let original = try JSONSerialization.data(
      withJSONObject: [
        "version": 1,
        "generatedAt": "2026-09-21T12:00:00Z",
        "jobs": [encodedJob, encodedJob, ["id": "not-a-job"]],
      ],
      options: [.prettyPrinted, .sortedKeys]
    )
    try original.write(to: historyURL)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    let recovered = try #require(store.jobs.first)
    #expect(store.jobs.count == 1)
    #expect(recovered.id == job.id)
    #expect(recovered.status == .cancelled)
    #expect(recovered.artifacts.count == 1)
    #expect(recovered.nextActions.count == 1)
    #expect(store.persistenceRecoveryNotice?.contains("migrated schema 1 to 2") == true)
    #expect(store.persistenceRecoveryNotice?.contains("discarded 1 invalid record") == true)
    #expect(store.persistenceRecoveryNotice?.contains("duplicate identifier") == true)

    let archivePath = try #require(store.lastPersistenceRecoveryArchivePath)
    #expect(try Data(contentsOf: URL(fileURLWithPath: archivePath)) == original)
    let activeObject = try #require(
      JSONSerialization.jsonObject(with: Data(contentsOf: historyURL)) as? [String: Any]
    )
    #expect(activeObject["version"] as? Int == JobHistoryStore.currentVersion)
    #expect((activeObject["jobs"] as? [Any])?.count == 1)
  }

  @Test
  @MainActor
  func agentStateMigrationDeduplicatesStepIDsWithoutCrashAndPreservesOriginal() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Agent-Recovery-\(UUID().uuidString)", isDirectory: true)
    let stateDirectory = root.appendingPathComponent(".scientificworkbench", isDirectory: true)
    let stateURL = stateDirectory.appendingPathComponent("agent_state.json")
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: stateDirectory, withIntermediateDirectories: true)
    defaults.set(root.path, forKey: "outputRootPath")

    let duplicateStepID = UUID()
    let firstStep = AgentPlanStep(
      id: duplicateStepID,
      capabilityID: "profile_table",
      summary: "Profile the attached table.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let duplicateStep = AgentPlanStep(
      id: duplicateStepID,
      capabilityID: "profile_table",
      summary: "Duplicate persisted step.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let plan = AgentPlan(
      title: "Recovered plan",
      rationale: "Exercise duplicate persisted identifiers.",
      steps: [firstStep, duplicateStep],
      source: .local,
      createdAt: Date(timeIntervalSince1970: 1_000)
    )
    let earlier = AgentPlanStepExecution(
      stepID: duplicateStepID,
      capabilityID: "profile_table",
      jobID: UUID(),
      status: .succeeded,
      runDirectory: root.appendingPathComponent("earlier").path,
      finishedAt: Date(timeIntervalSince1970: 1_100)
    )
    let later = AgentPlanStepExecution(
      stepID: duplicateStepID,
      capabilityID: "profile_table",
      jobID: UUID(),
      status: .failed,
      runDirectory: root.appendingPathComponent("later").path,
      finishedAt: Date(timeIntervalSince1970: 1_200)
    )
    let original = try JSONSerialization.data(
      withJSONObject: [
        "version": 1,
        "generatedAt": "2026-09-21T12:00:00Z",
        "agentPlan": try persistenceJSONObject(plan),
        "stepExecutions": [
          try persistenceJSONObject(earlier),
          try persistenceJSONObject(later),
          ["id": "not-an-execution"],
        ],
        "lastWorkflowSummaryPath": NSNull(),
        "agentStatusMessage": "Restore this workflow safely.",
      ],
      options: [.prettyPrinted, .sortedKeys]
    )
    try original.write(to: stateURL)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    #expect(store.agentPlan?.steps.count == 1)
    #expect(store.agentPlanStepExecutions.count == 1)
    #expect(store.agentPlanStepExecutions[duplicateStepID]?.status == .failed)
    #expect(store.agentStatusMessage == "Restore this workflow safely.")
    #expect(store.persistenceRecoveryNotice?.contains("migrated schema 1 to 2") == true)
    #expect(store.persistenceRecoveryNotice?.contains("discarded 1 invalid record") == true)
    #expect(store.persistenceRecoveryNotice?.contains("duplicate identifier") == true)

    let archivePath = try #require(store.lastPersistenceRecoveryArchivePath)
    #expect(try Data(contentsOf: URL(fileURLWithPath: archivePath)) == original)
    let activeObject = try #require(
      JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as? [String: Any]
    )
    #expect(activeObject["version"] as? Int == AgentStateStore.currentVersion)
    #expect((activeObject["stepExecutions"] as? [Any])?.count == 1)
  }

  @Test
  @MainActor
  func unreadableJobHistoryIsQuarantinedBeforeCleanStateIsWritten() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Corrupt-History-\(UUID().uuidString)", isDirectory: true)
    let stateDirectory = root.appendingPathComponent(".scientificworkbench", isDirectory: true)
    let historyURL = stateDirectory.appendingPathComponent("jobs.json")
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let original = Data("{ definitely not JSON".utf8)
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: stateDirectory, withIntermediateDirectories: true)
    try original.write(to: historyURL)
    defaults.set(root.path, forKey: "outputRootPath")

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    #expect(store.jobs.isEmpty)
    #expect(store.persistenceRecoveryNotice?.contains("exact original was preserved") == true)
    let archivePath = try #require(store.lastPersistenceRecoveryArchivePath)
    #expect(try Data(contentsOf: URL(fileURLWithPath: archivePath)) == original)
    let activeObject = try #require(
      JSONSerialization.jsonObject(with: Data(contentsOf: historyURL)) as? [String: Any]
    )
    #expect(activeObject["version"] as? Int == JobHistoryStore.currentVersion)
    #expect((activeObject["jobs"] as? [Any])?.isEmpty == true)
  }

  @Test
  @MainActor
  func importedV1PlanDeduplicatesStepsWhileFutureSchemaRemainsUntouched() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Imported-Plan-Migration-\(UUID().uuidString)", isDirectory: true)
    let inputURL = root.appendingPathComponent("input.csv")
    let legacyURL = root.appendingPathComponent("legacy-plan.json")
    let futureURL = root.appendingPathComponent("future-plan.json")
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "x,y\n1,2\n".write(to: inputURL, atomically: true, encoding: .utf8)
    defaults.set(root.path, forKey: "outputRootPath")

    let stepID = UUID()
    let first = AgentPlanStep(
      id: stepID,
      capabilityID: "profile_table",
      summary: "Profile the table.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let duplicate = AgentPlanStep(
      id: stepID,
      capabilityID: "profile_table",
      summary: "Duplicate step.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let plan = AgentPlan(
      title: "Legacy exported plan",
      rationale: "Migration test.",
      steps: [first, duplicate],
      source: .local
    )
    let legacyPayload = ExportedAgentPlanPayload(
      version: 1,
      generatedAt: Date(timeIntervalSince1970: 1_000),
      outputRootPath: root.path,
      inputPaths: [inputURL.path],
      aiProvider: .ollama,
      aiModel: "qwen3:4b-instruct",
      mode: .workflow,
      autoRun: false,
      plan: plan
    )
    let legacyData = try JSONEncoder.scientificWorkbench.encode(legacyPayload)
    try legacyData.write(to: legacyURL)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.capabilities = [sampleCapability()]
    let imported = try #require(store.importAgentPlan(from: legacyURL.path))

    #expect(imported.steps.count == 1)
    #expect(store.agentStatusMessage.contains("Migrated plan schema 1 to 2"))
    #expect(store.agentStatusMessage.contains("Removed 1 duplicate step identifier"))
    #expect(try Data(contentsOf: legacyURL) == legacyData)

    var futureObject = try #require(
      JSONSerialization.jsonObject(with: legacyData) as? [String: Any]
    )
    futureObject["version"] = ExportedAgentPlanPayload.currentVersion + 1
    let futureData = try JSONSerialization.data(
      withJSONObject: futureObject,
      options: [.prettyPrinted, .sortedKeys]
    )
    try futureData.write(to: futureURL)
    let planBeforeFutureImport = store.agentPlan

    #expect(store.importAgentPlan(from: futureURL.path) == nil)
    #expect(store.agentPlan == planBeforeFutureImport)
    #expect(store.agentStatusMessage.contains("unsupported schema version"))
    #expect(try Data(contentsOf: futureURL) == futureData)
  }

  @Test
  @MainActor
  func futureJobHistorySchemaIsRejectedAndLeftUntouched() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Future-History-\(UUID().uuidString)", isDirectory: true)
    let stateDirectory = root.appendingPathComponent(".scientificworkbench", isDirectory: true)
    let historyURL = stateDirectory.appendingPathComponent("jobs.json")
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: stateDirectory, withIntermediateDirectories: true)
    defaults.set(root.path, forKey: "outputRootPath")
    let original = try JSONSerialization.data(
      withJSONObject: [
        "version": JobHistoryStore.currentVersion + 1,
        "generatedAt": "2026-09-21T12:00:00Z",
        "jobs": [],
      ],
      options: [.prettyPrinted, .sortedKeys]
    )
    try original.write(to: historyURL)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    #expect(store.jobs.isEmpty)
    #expect(store.registryError?.contains("unsupported schema version") == true)
    #expect(store.persistenceRecoveryNotice == nil)
    #expect(try Data(contentsOf: historyURL) == original)
    #expect(!FileManager.default.fileExists(
      atPath: stateDirectory.appendingPathComponent("recovery", isDirectory: true).path
    ))
  }
}

private func persistenceJSONObject<T: Encodable>(_ value: T) throws -> Any {
  let data = try JSONEncoder.scientificWorkbench.encode(value)
  return try JSONSerialization.jsonObject(with: data)
}

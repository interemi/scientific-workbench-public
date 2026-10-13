import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func newWorkflowArchivesAndRestoresDraftWithoutChangingOriginalsOrEvidence() throws {
    let root = try makeScenarioFixture(name: "new-workflow", files: ["inputs/table.csv": "x,y\n1,2\n"])
    defer { try? FileManager.default.removeItem(at: root) }
    let input = root.appendingPathComponent("inputs/table.csv")
    let original = try Data(contentsOf: input)
    let output = root.appendingPathComponent("output")
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-New-Workflow-\(UUID())")!
    defaults.set(output.path, forKey: "outputRootPath")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let capability = sampleCapability()
    store.capabilities = [capability]
    store.inputPaths = [input.path]
    store.agentPrompt = "Inspect synthetic table."
    store.setCapabilityArgumentDraft("--delimiter ','", for: capability.id)
    store.selectedCapabilityID = capability.id
    let step = AgentPlanStep(capabilityID: capability.id, summary: "Profile table",
      rawArguments: "", usesInputs: true, usesPreviousOutput: false)
    let plan = AgentPlan(title: "Saved draft", rationale: "Preserve context", steps: [step], source: .local)
    store.agentPlan = plan
    var job = JobRecord(capability: capability, runDirectory: output.appendingPathComponent("prior-run").path)
    job.status = .succeeded
    store.jobs = [job]
    store.selectedJobID = job.id
    store.agentPlanStepExecutions[step.id] = AgentPlanStepExecution(stepID: step.id,
      capabilityID: capability.id, jobID: job.id, status: .succeeded,
      runDirectory: job.runDirectory, finishedAt: Date())
    let summary = root.appendingPathComponent("prior-summary.md")
    try "Prior evidence\n".write(to: summary, atomically: true, encoding: .utf8)
    store.lastWorkflowSummaryPath = summary.path
    let summaryBytes = try Data(contentsOf: summary)
    store.agentAutoRun = true

    #expect(store.beginNewWorkflow())
    let backup = try #require(store.previousWorkflowDraft)
    let archive = try Data(contentsOf: URL(fileURLWithPath: backup.archivePath))
    let decoded = try JSONDecoder.scientificWorkbench.decode(WorkflowDraftCheckpoint.self, from: archive)
    #expect(decoded.version == 1)
    #expect(decoded.plan?.id == plan.id)
    #expect(decoded.stepExecutions.first?.jobID == job.id)
    #expect(decoded.inputPaths == [input.path])
    #expect(store.inputPaths.isEmpty && store.agentPlan == nil)
    #expect(store.agentPrompt.isEmpty && store.capabilityArgumentDrafts.isEmpty)
    #expect(store.selectedSection == .home)
    #expect(!store.agentAutoRun)
    #expect(store.jobs == [job])

    store.agentPrompt = "Another draft worth keeping."
    #expect(store.restorePreviousWorkflowDraft())
    #expect(store.agentPlan?.id == plan.id)
    #expect(store.agentPlanStepExecutions[step.id]?.jobID == job.id)
    #expect(store.inputPaths == [input.path])
    #expect(store.agentPrompt == "Inspect synthetic table.")
    #expect(store.capabilityArgumentDraft(for: capability.id) == "--delimiter ','")
    #expect(store.selectedJobID == job.id)
    #expect(store.lastWorkflowSummaryPath == summary.path)
    #expect(!store.agentAutoRun && !store.outputRootRiskApproved)
    #expect(store.jobs == [job])
    #expect(store.previousWorkflowDraft?.checkpoint.prompt == "Another draft worth keeping.")
    #expect(try Data(contentsOf: input) == original)
    #expect(try Data(contentsOf: summary) == summaryBytes)
    #expect(try Data(contentsOf: URL(fileURLWithPath: backup.archivePath)) == archive)
  }

  @Test
  @MainActor
  func newWorkflowLeavesDraftInPlaceWhenArchiveCannotBeWrittenOrAnOperationIsActive() throws {
    let root = try makeScenarioFixture(name: "archive-failure", files: ["output/Workflow Drafts": "Keep this file"])
    defer { try? FileManager.default.removeItem(at: root) }
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-New-Workflow-Fail-\(UUID())")!
    defaults.set(root.appendingPathComponent("output").path, forKey: "outputRootPath")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.agentPrompt = "Keep this draft."
    store.inputPaths = [root.appendingPathComponent("input.csv").path]
    let originalInputs = store.inputPaths
    store.isPlanningAgentWorkflow = true
    #expect(!store.beginNewWorkflow())
    #expect(store.agentPrompt == "Keep this draft.")
    store.isPlanningAgentWorkflow = false
    #expect(!store.beginNewWorkflow())
    #expect(store.inputPaths == originalInputs)
    #expect(store.agentPrompt == "Keep this draft.")
    #expect(store.previousWorkflowDraft == nil)
    #expect(store.workflowNavigationNotice?.contains("No context was cleared") == true)
    #expect(try String(contentsOf: root.appendingPathComponent("output/Workflow Drafts"), encoding: .utf8) == "Keep this file")
  }

  @Test
  @MainActor
  func draftRestoreClearsSuccessCheckpointsWhenInputsAreMissingAndRejectsAnotherOutputRoot() throws {
    let root = try makeScenarioFixture(name: "missing-draft-input", files: ["input.csv": "x\n1\n"])
    defer { try? FileManager.default.removeItem(at: root) }
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Draft-Missing-\(UUID())")!
    let output = root.appendingPathComponent("output")
    defaults.set(output.path, forKey: "outputRootPath")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let capability = sampleCapability()
    store.capabilities = [capability]
    let missing = root.appendingPathComponent("unavailable.csv").path
    store.inputPaths = [missing]
    let step = AgentPlanStep(capabilityID: capability.id, summary: "Inspect missing file",
      rawArguments: "", usesInputs: true, usesPreviousOutput: false)
    store.agentPlan = AgentPlan(title: "Missing input", rationale: "Review", steps: [step], source: .local)
    store.agentPlanStepExecutions[step.id] = AgentPlanStepExecution(stepID: step.id,
      capabilityID: capability.id, jobID: UUID(), status: .succeeded,
      runDirectory: output.appendingPathComponent("prior").path, finishedAt: Date())
    #expect(store.beginNewWorkflow())
    store.outputRootPath = root.appendingPathComponent("another-output").path
    #expect(!store.restorePreviousWorkflowDraft())
    #expect(store.agentPlan == nil)
    store.outputRootPath = output.path
    #expect(store.restorePreviousWorkflowDraft())
    #expect(store.agentPlan != nil)
    #expect(store.inputPaths.isEmpty && store.agentPlanStepExecutions.isEmpty)
    #expect(store.agentStatusMessage.contains("1 missing input"))
    #expect(!store.agentAutoRun)
  }

  @Test
  func workflowDraftArchiveRedactsSecretsRejectsOverwriteAndDirectoryRedirect() throws {
    let root = try makeScenarioFixture(name: "draft-redaction", files: [:])
    defer { try? FileManager.default.removeItem(at: root) }
    let secret = "synthetic-secret"
    let checkpoint = WorkflowDraftCheckpoint(outputRootPath: root.appendingPathComponent("output").path,
      inputPaths: ["/synthetic/\(secret).csv"], prompt: secret, plan: nil, stepExecutions: [],
      summaryPath: secret, selectedCapabilityID: nil, selectedJobID: nil,
      argumentDrafts: ["profile_table": secret], messages: [AgentChatMessage(role: .user, text: secret)])
    let service = WorkflowDraftArchiveService()
    let redact: (String) -> String = { $0.replacingOccurrences(of: secret, with: "[REDACTED]") }
    let url = try service.write(checkpoint: checkpoint, redact: redact)
    let bytes = try Data(contentsOf: url)
    #expect(!String(decoding: bytes, as: UTF8.self).contains(secret))
    #expect(String(decoding: bytes, as: UTF8.self).contains("[REDACTED]"))
    #expect(throws: (any Error).self) { try service.write(checkpoint: checkpoint, redact: redact) }
    #expect(try Data(contentsOf: url) == bytes)
    let permissions = try FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? NSNumber
    #expect(permissions?.intValue == 0o600)

    let otherRoot = root.appendingPathComponent("redirected")
    let outside = root.appendingPathComponent("outside")
    try FileManager.default.createDirectory(at: otherRoot, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)
    try FileManager.default.createSymbolicLink(at: otherRoot.appendingPathComponent("Workflow Drafts"), withDestinationURL: outside)
    var redirected = checkpoint
    redirected.outputRootPath = otherRoot.path
    #expect(throws: (any Error).self) { try service.write(checkpoint: redirected, redact: redact) }
    #expect(try FileManager.default.contentsOfDirectory(atPath: outside.path).isEmpty)
  }
}

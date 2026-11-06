import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func workflowSummaryLinksRepeatedCapabilitiesByStepAndJobID() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("swb-summary-\(UUID())")
    defer { try? FileManager.default.removeItem(at: root) }
    let capability = sampleCapability()
    let steps = ["First input", "Second input"].map {
      AgentPlanStep(capabilityID: capability.id, summary: $0, rawArguments: "", usesInputs: true, usesPreviousOutput: false)
    }
    let plan = AgentPlan(title: "Repeated capability", rationale: "Two different outcomes", steps: steps, source: .local)
    var first = JobRecord(capability: capability, runDirectory: root.appendingPathComponent("first").path)
    first.status = .succeeded
    var second = JobRecord(capability: capability, runDirectory: root.appendingPathComponent("second").path)
    second.status = .blocked
    let executions = zip(steps, [first, second]).map { step, job in
      AgentPlanStepExecution(stepID: step.id, capabilityID: capability.id, jobID: job.id,
        status: job.status, runDirectory: job.runDirectory, finishedAt: nil)
    }
    let request = WorkflowSummaryRequest(plan: plan, enabledSteps: steps, jobs: [second, first],
      jobIDs: [first.id, second.id], inputPaths: [], outputRootPath: root.path, status: "Stopped",
      startedAt: Date(), finishedAt: Date(), stepExecutions: executions)
    let url = try WorkflowSummaryService().write(request: request, redact: { $0 })
    let markdown = try String(contentsOf: url, encoding: .utf8)
    let enabled = try #require(markdown.components(separatedBy: "## Enabled Steps\n").last?
      .components(separatedBy: "## Jobs").first)
    #expect(enabled.contains("1. `\(capability.id)` - Succeeded"))
    #expect(enabled.contains("2. `\(capability.id)` - Blocked"))
    #expect(enabled.contains("Step ID: `\(steps[0].id.uuidString)`\n   - Job ID: `\(first.id.uuidString)`"))
    #expect(enabled.contains("Step ID: `\(steps[1].id.uuidString)`\n   - Job ID: `\(second.id.uuidString)`"))
    #expect(markdown.contains("Plan ID: `\(plan.id.uuidString)`"))
  }

  @Test
  func workflowSummaryDoesNotGuessAssociationFromCapabilityOrStaleExecution() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("swb-summary-unlinked-\(UUID())")
    defer { try? FileManager.default.removeItem(at: root) }
    let capability = sampleCapability()
    let step = AgentPlanStep(capabilityID: capability.id, summary: "Input", rawArguments: "", usesInputs: true, usesPreviousOutput: false)
    let plan = AgentPlan(title: "Unlinked", rationale: "Association unavailable", steps: [step], source: .local)
    var job = JobRecord(capability: capability, runDirectory: root.appendingPathComponent("run").path)
    job.status = .succeeded
    let stale = AgentPlanStepExecution(stepID: step.id, capabilityID: capability.id,
      jobID: job.id, status: .succeeded, runDirectory: root.appendingPathComponent("other-run").path, finishedAt: nil)
    for executions in [[], [stale]] {
      let request = WorkflowSummaryRequest(plan: plan, enabledSteps: [step], jobs: [job],
        jobIDs: [job.id], inputPaths: [], outputRootPath: root.path, status: "Review",
        startedAt: Date(), finishedAt: Date(), stepExecutions: executions)
      let url = try WorkflowSummaryService().write(request: request, redact: { $0 })
      let markdown = try String(contentsOf: url, encoding: .utf8)
      #expect(markdown.contains("1. `\(capability.id)` - No linked job"))
      #expect(!markdown.contains("1. `\(capability.id)` - Succeeded"))
    }
  }

  @Test
  func workflowSummaryPreservesPriorSummaryAndRedactsNewEvidence() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("swb-summary-preserve-\(UUID())")
    defer { try? FileManager.default.removeItem(at: root) }
    let plan = AgentPlan(title: "synthetic-secret", rationale: "Review", steps: [], source: .local)
    let request = WorkflowSummaryRequest(plan: plan, enabledSteps: [], jobs: [], jobIDs: [],
      inputPaths: ["/input/synthetic-secret.csv"], outputRootPath: root.path, status: "Cancelled",
      startedAt: Date(), finishedAt: Date())
    let redact: (String) -> String = { $0.replacingOccurrences(of: "synthetic-secret", with: "[REDACTED]") }
    let first = try WorkflowSummaryService().write(request: request, redact: redact)
    let original = try Data(contentsOf: first)
    let second = try WorkflowSummaryService().write(request: request, redact: redact)
    #expect(first != second)
    #expect(try Data(contentsOf: first) == original)
    let text = try String(contentsOf: second, encoding: .utf8)
    #expect(!text.contains("synthetic-secret"))
    #expect(text.contains("[REDACTED]"))
    #expect(text.contains("No jobs were started"))
  }
}

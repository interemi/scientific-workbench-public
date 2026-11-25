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

  @Test
  func workflowSummaryCitesOnlyUsableRecordedMeasurementBytes() async throws {
    let root = try makeScenarioFixture(name: "workflow-measurement-evidence", files: [:])
    defer { try? FileManager.default.removeItem(at: root) }
    let capability = CapabilityEntry(
      id: "photometric_solution", label: "Photometry", script: "scripts/photometric_solution.py", visibleBlock: "astronomy",
      kind: "supporting_tool", supportLevel: "stable", platform: "portable",
      requiresDatanalysis: true, preflightMode: "none", smokeTier: "core", shortDescription: "Synthetic evidence."
    )
    let step = AgentPlanStep(capabilityID: capability.id, summary: "Fit", rawArguments: "", usesInputs: true, usesPreviousOutput: false)
    let plan = AgentPlan(title: "Photometric fit", rationale: "Measure a synthetic field", steps: [step], source: .local)
    let validSummary = """
      {
        "tool": "photometric_solution", "app_status": "WARNING", "status": "warning",
        "results": {
          "measurement_summary": {
            "method": "Weighted least squares",
            "measurements": [{"label": "Zero point", "value": 21.75, "unit": "mag", "uncertainty": 0.125}],
            "diagnostics": [{"label": "Samples used", "value": 16, "unit": "count"}],
            "assumptions": ["The input standard magnitudes are independent."]
          }
        },
        "qa": {"status": "warning", "findings": ["Review the residuals."]}
      }
      """
    let cases: [(name: String, initially: String, replacement: String?, failure: String?)] = [
      ("recorded", validSummary, validSummary, nil),
      ("changed", validSummary, validSummary.replacingOccurrences(of: "21.75", with: "88.25"),
       "does not match a recorded output hash"),
      ("deleted", validSummary, nil, "missing or unreadable"),
      ("corrupt", "{ incomplete", "{ incomplete", "did not contain usable measurements"),
      ("rejected", validSummary.replacingOccurrences(of: #""app_status": "WARNING""#, with: #""app_status": "FAIL""#),
       validSummary.replacingOccurrences(of: #""app_status": "WARNING""#, with: #""app_status": "FAIL""#),
       "did not contain usable measurements"),
    ]
    for (name, initial, replacement, failure) in cases {
      let run = root.appendingPathComponent(name)
      try FileManager.default.createDirectory(at: run, withIntermediateDirectories: false)
      let source = run.appendingPathComponent("summary.json")
      try Data(initial.utf8).write(to: source)
      var job = JobRecord(capability: capability, runDirectory: run.path)
      job.status = .succeeded
      job.artifacts = [Artifact(path: source.path, relativePath: "summary.json", byteCount: Int64(initial.utf8.count))]
      let capture = await RunProvenanceService().captureStart(
        request: RunRequest(capabilityID: capability.id, inputPaths: [], outputDirectory: run.path, rawArguments: ""),
        capability: capability, skillRoot: root.path, outputRootConfirmationUsed: false, secrets: []
      )
      let receipt = try RunProvenanceService().write(start: capture, job: job)
      job.artifacts.append(receipt)
      if let replacement {
        if replacement != initial { try Data(replacement.utf8).write(to: source, options: .atomic) }
      } else {
        try FileManager.default.removeItem(at: source)
      }
      let execution = AgentPlanStepExecution(stepID: step.id, capabilityID: capability.id,
        jobID: job.id, status: job.status, runDirectory: run.path, finishedAt: nil)
      let request = WorkflowSummaryRequest(plan: plan, enabledSteps: [step], jobs: [job], jobIDs: [job.id],
        inputPaths: [], outputRootPath: root.path, status: "Finished", startedAt: Date(), finishedAt: Date(),
        stepExecutions: [execution])
      let report = try WorkflowSummaryService().write(request: request, redact: { $0 })
      let text = try String(contentsOf: report, encoding: .utf8)

      if let failure {
        #expect(text.contains("Evidence unavailable"))
        #expect(text.contains(failure))
        #expect(!text.contains("Zero point"))
        #expect(!text.contains("21.75"))
        #expect(!text.contains("88.25"))
      } else {
        #expect(text.contains("Zero point — 21.75 ± 0.125 mag"))
        #expect(text.contains("summary.json#/results/measurement_summary/measurements/0"))
        #expect(text.contains("summary.json#/results/measurement_summary/diagnostics/0"))
        #expect(text.contains("Tool QA — warning"))
        #expect(text.contains("Source summary.json with SHA-256"))
        #expect(!text.contains("Evidence unavailable"))
      }
    }
  }
}

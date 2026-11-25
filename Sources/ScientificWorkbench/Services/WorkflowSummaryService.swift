import Foundation

struct WorkflowSummaryRequest {
  var plan: AgentPlan
  var enabledSteps: [AgentPlanStep]
  var jobs: [JobRecord]
  var jobIDs: [UUID]
  var inputPaths: [String]
  var outputRootPath: String
  var status: String
  var startedAt: Date
  var finishedAt: Date
  var stepExecutions: [AgentPlanStepExecution] = []
  var workflowExecutionID: UUID?
}

struct WorkflowSummaryService {
  func write(
    request: WorkflowSummaryRequest,
    redact: (String) -> String
  ) throws -> URL {
    let workflowJobs = request.jobIDs.compactMap { id in
      request.jobs.first { $0.id == id }
    }
    let summariesURL = URL(fileURLWithPath: request.outputRootPath)
      .appendingPathComponent("Workflow Summaries", isDirectory: true)
    let fileURL = summariesURL
      .appendingPathComponent(
        "\(DateFormatters.runFolder.string(from: request.startedAt))_\(UUID().uuidString.lowercased())_workflow_summary.md"
      )

    let markdown = markdown(
      request: request,
      workflowJobs: workflowJobs,
      redact: redact
    )

    try FileManager.default.createDirectory(at: summariesURL, withIntermediateDirectories: true)
    try markdown.write(to: fileURL, atomically: true, encoding: .utf8)
    return fileURL
  }

  private func markdown(
    request: WorkflowSummaryRequest,
    workflowJobs: [JobRecord],
    redact: (String) -> String
  ) -> String {
    let duration = DateFormatters.duration.string(
      from: request.finishedAt.timeIntervalSince(request.startedAt)
    ) ?? "-"
    let inputLines = request.inputPaths.isEmpty
      ? "- None attached."
      : request.inputPaths.map { "- `\(redact($0))` (read-only)" }.joined(separator: "\n")
    let linkedJobs: [JobRecord?] = request.enabledSteps.map { step in
      let executions = request.stepExecutions.filter {
        $0.stepID == step.id && $0.capabilityID == step.capabilityID
      }
      guard executions.count == 1, let execution = executions.first else { return nil }
      return workflowJobs.first {
        $0.id == execution.jobID && $0.capabilityID == step.capabilityID
          && $0.runDirectory == execution.runDirectory
      }
    }
    let stepLines = zip(request.enabledSteps, linkedJobs).enumerated().map { index, pair in
      let (step, matchingJob) = pair
      let jobStatus = matchingJob?.status.title ?? "No linked job (not run or association unavailable)"
      let jobID = matchingJob?.id.uuidString ?? "Unavailable"
      return "\(index + 1). `\(redact(step.capabilityID))` - \(jobStatus)\n"
        + "   - Step ID: `\(step.id.uuidString)`\n   - Job ID: `\(jobID)`"
    }.joined(separator: "\n")
    let jobLines = workflowJobs.isEmpty
      ? "- No jobs were started."
      : workflowJobs.map { job in
        let exitCode = job.exitCode.map(String.init) ?? "-"
        return "- `\(redact(job.capabilityLabel))`: \(job.status.title), exit \(exitCode), "
          + "job ID `\(job.id.uuidString)`, run folder `\(redact(job.runDirectory))`. "
          + "Inspect this job in Jobs for its captured logs and command."
      }.joined(separator: "\n")
    let artifactLines = workflowJobs
      .flatMap { job in
        job.artifacts.map { artifact in
          "- `\(redact(artifact.relativePath))` from `\(redact(job.capabilityLabel))`, job ID `\(job.id.uuidString)`"
        }
      }
      .prefix(40)
      .joined(separator: "\n")
    let artifactSection = artifactLines.isEmpty ? "- No artifacts indexed." : artifactLines
    let finalPDFs = workflowJobs
      .flatMap(\.artifacts)
      .filter { $0.url.pathExtension.localizedLowercase == "pdf" }
      .map { "- `\(redact($0.path))`" }
      .joined(separator: "\n")
    let finalPDFSection = finalPDFs.isEmpty ? "- No PDF deliverable was indexed." : finalPDFs
    let measurementSection = measurementEvidence(for: linkedJobs.compactMap { $0 }, redact: redact)

    return """
    # Scientific Workbench Workflow Summary

    Workflow Run ID: \(request.workflowExecutionID.map { "`\($0.uuidString)`" } ?? "Not recorded")
    Status: \(redact(request.status))
    Started: \(ISO8601DateFormatter().string(from: request.startedAt))
    Finished: \(ISO8601DateFormatter().string(from: request.finishedAt))
    Duration: \(duration)

    ## Plan

    Title: \(redact(request.plan.title))
    Plan ID: `\(request.plan.id.uuidString)`
    Source: \(request.plan.source.title)

    Planning rationale

    \(redact(request.plan.rationale))

    ## Read-Only Inputs

    \(inputLines)

    Scientific Workbench treats original inputs as read-only. Configured output root captured for this workflow:

    `\(redact(request.outputRootPath))`

    ## Enabled Steps

    \(stepLines)

    ## Jobs

    \(jobLines)

    ## Indexed Artifacts

    \(artifactSection)

    ## Measurements from Run Artifacts

    \(measurementSection)

    ## PDF Deliverables

    \(finalPDFSection)

    ## Safety Note

    Original input paths are not modified by the app by default. Capabilities that need writable legacy state create separate workspaces or output folders outside the attached input folders.
    """
  }

  private func measurementEvidence(for jobs: [JobRecord], redact: (String) -> String) -> String {
    let eligible = jobs.filter { ScientificMeasurementSummary.supports($0.capabilityID) }
    guard !eligible.isEmpty else { return "No linked job has a supported measurement summary." }
    let service = RunMeasurementEvidenceService()
    let limit = 12
    var lines: [String] = []
    for job in eligible.prefix(limit) {
      lines.append("### Job `\(job.id.uuidString)`\n")
      switch service.read(for: job) {
      case .failure(let issue):
        lines.append("Evidence unavailable. \(issue.reason)")
      case .success(let evidence):
        let summary = evidence.summary
        let source = escapedText(evidence.source, redact: redact)
        lines.append("Source \(source) with SHA-256 `\(evidence.sha256)`.\n")
        lines.append("- Method — \(escapedText(summary.method, redact: redact)).")
        if summary.evidenceOutcome == .warning { lines.append("- The tool reported warnings.") }
        lines.append("- Tool QA — \(escapedText(summary.quality.status, redact: redact)).")
        lines += summary.quality.findings.prefix(limit).map { "- QA finding — \(escapedText($0, redact: redact))" }
        lines += summary.assumptions.prefix(limit).map { "- Assumption — \(escapedText($0, redact: redact))" }
        for (field, quantities) in [("measurements", summary.measurements), ("diagnostics", summary.diagnostics)] {
          for (index, quantity) in quantities.prefix(limit).enumerated() {
            let label = escapedText(quantity.label, redact: redact)
            let unit = escapedText(quantity.unit, redact: redact)
            let uncertainty = quantity.uncertainty.map { " ± \($0)" } ?? ""
            let pointer = "/results/measurement_summary/\(field)/\(index)"
            lines.append("- \(label) — \(quantity.value)\(uncertainty) \(unit) (\(source)#\(pointer)).")
          }
        }
        let counts = [summary.quality.findings.count, summary.assumptions.count,
                      summary.measurements.count, summary.diagnostics.count]
        if counts.contains(where: { $0 > limit }) {
          lines.append("The source contains additional entries. Each list shows up to \(limit).")
        }
      }
      lines.append("")
    }
    if eligible.count > limit {
      lines.append("This section covers the first \(limit) linked jobs with supported measurement summaries.")
    }
    return lines.joined(separator: "\n")
  }

  private func escapedText(_ value: String, redact: (String) -> String) -> String {
    let flattened = redact(value).split(whereSeparator: \.isWhitespace).joined(separator: " ")
    return flattened.map { "\\`*_[]<>#|".contains($0) ? "\\\($0)" : String($0) }.joined()
  }
}

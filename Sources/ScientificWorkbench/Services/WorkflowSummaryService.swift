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
    let stepLines = request.enabledSteps.enumerated().map { index, step in
      let matchingJob = workflowJobs.first { $0.capabilityID == step.capabilityID }
      let jobStatus = matchingJob?.status.title ?? "Not run"
      return "\(index + 1). `\(redact(step.capabilityID))` - \(jobStatus)"
    }.joined(separator: "\n")
    let jobLines = workflowJobs.isEmpty
      ? "- No jobs were started."
      : workflowJobs.map { job in
        let exitCode = job.exitCode.map(String.init) ?? "-"
        return "- `\(redact(job.capabilityLabel))`: \(job.status.title), exit \(exitCode), run folder `\(redact(job.runDirectory))`"
      }.joined(separator: "\n")
    let artifactLines = workflowJobs
      .flatMap { job in
        job.artifacts.map { artifact in
          "- `\(redact(artifact.relativePath))` from `\(redact(job.capabilityLabel))`"
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

    return """
    # Scientific Workbench Workflow Summary

    Status: \(redact(request.status))
    Started: \(ISO8601DateFormatter().string(from: request.startedAt))
    Finished: \(ISO8601DateFormatter().string(from: request.finishedAt))
    Duration: \(duration)

    ## Plan

    Title: \(redact(request.plan.title))
    Source: \(request.plan.source.title)

    \(redact(request.plan.rationale))

    ## Read-Only Inputs

    \(inputLines)

    Scientific Workbench treats original inputs as read-only. Outputs for this workflow were written under:

    `\(redact(request.outputRootPath))`

    ## Enabled Steps

    \(stepLines)

    ## Jobs

    \(jobLines)

    ## Indexed Artifacts

    \(artifactSection)

    ## PDF Deliverables

    \(finalPDFSection)

    ## Safety Note

    Original input paths are not modified by the app by default. Capabilities that need writable legacy state create separate workspaces or output folders outside the attached input folders.
    """
  }
}

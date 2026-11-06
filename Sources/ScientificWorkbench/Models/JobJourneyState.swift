import Foundation

struct JobJourneyState {
  let runStage: String
  let jobStage: String
  let resultStage: String
  let currentStep: String?
  let lastActivityAt: Date
  let guidance: String

  init(
    job: JobRecord,
    plan: AgentPlan?,
    stepExecutions: [AgentPlanStep.ID: AgentPlanStepExecution],
    isRunningWorkflow: Bool,
    isCancellationRequested: Bool
  ) {
    runStage = "Request accepted"
    lastActivityAt = job.finishedAt ?? job.startedAt ?? job.createdAt

    switch job.status {
    case .queued:
      jobStage = "Preparing command and output folder"
      resultStage = "Pending"
      guidance = "The job has not started its external process yet. You can inspect its separate run folder."
    case .running:
      jobStage = isCancellationRequested ? "Stopping external process" : "External process running"
      resultStage = "Pending"
      guidance = isCancellationRequested
        ? "Cancellation is in progress. Any partial files stay in the run folder; captured logs are retained when the process stops."
        : "Internal tool progress is unavailable. Jobs will show the final logs and artifacts when the process stops; partial files may already be in the run folder."
    case .succeeded:
      jobStage = job.displaySeverity == "warning" ? "Completed with warnings" : "Completed"
      resultStage = "\(job.artifacts.count) artifact\(job.artifacts.count == 1 ? "" : "s") found"
      guidance = "Open Results to inspect artifacts and evidence. A completed process is not scientific approval."
    case .failed, .blocked, .timedOut, .cancelled:
      jobStage = job.status.title
      resultStage = "\(job.artifacts.count) retained artifact\(job.artifacts.count == 1 ? "" : "s")"
      guidance = "Review the error, recovery advice, logs, and partial files before retrying. This run folder remains available."
    }

    let enabledSteps = plan?.steps.filter(\.isEnabled) ?? []
    if let index = enabledSteps.firstIndex(where: { step in
      stepExecutions[step.id]?.jobID == job.id
    }) {
      currentStep = "Workflow step \(index + 1) of \(enabledSteps.count): \(enabledSteps[index].summary)"
    } else if isRunningWorkflow,
              job.status == .running,
              let index = enabledSteps.indices.first(where: { stepIndex in
                let step = enabledSteps[stepIndex]
                guard step.capabilityID == job.capabilityID,
                      stepExecutions[step.id] == nil else { return false }
                return enabledSteps[..<stepIndex].allSatisfy {
                  stepExecutions[$0.id]?.status == .succeeded
                }
              }) {
      currentStep = "Workflow step \(index + 1) of \(enabledSteps.count): \(enabledSteps[index].summary)"
    } else {
      currentStep = nil
    }
  }
}

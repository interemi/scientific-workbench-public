import Foundation

struct WorkflowRecoveryService {
  func state(
    plan: AgentPlan?,
    stepExecutions: [AgentPlanStep.ID: AgentPlanStepExecution],
    jobs: [JobRecord],
    isRunningWorkflow: Bool
  ) -> WorkflowRecoveryState? {
    guard let plan else { return nil }
    let enabledSteps = plan.steps.enumerated().filter { $0.element.isEnabled }
    guard !enabledSteps.isEmpty else { return nil }

    var completedCount = 0
    var resumeEnabledIndex: Int?
    var stoppedExecution: AgentPlanStepExecution?

    for (enabledIndex, indexedStep) in enabledSteps.enumerated() {
      let step = indexedStep.element
      guard let execution = stepExecutions[step.id] else {
        if completedCount > 0 {
          resumeEnabledIndex = enabledIndex
        }
        break
      }

      if execution.status == .succeeded {
        completedCount += 1
      } else {
        resumeEnabledIndex = enabledIndex
        stoppedExecution = execution
        break
      }
    }

    guard let resumeEnabledIndex, resumeEnabledIndex < enabledSteps.count else { return nil }
    guard completedCount > 0 || stoppedExecution != nil else { return nil }

    let resumeStep = enabledSteps[resumeEnabledIndex].element
    let stoppedJob = stoppedExecution.flatMap { execution in
      jobs.first { $0.id == execution.jobID }
    }
    let advice = stoppedJob?.recoveryAdvice ?? [
      "Review the plan before continuing.",
      "Run Dry Run if inputs, paths, or capability arguments have changed."
    ]

    return WorkflowRecoveryState(
      id: plan.id,
      completedCount: completedCount,
      totalCount: enabledSteps.count,
      resumeStepIndex: resumeEnabledIndex + 1,
      resumeStepCapabilityID: resumeStep.capabilityID,
      resumeStepSummary: resumeStep.summary,
      stoppedStatus: stoppedExecution?.status,
      stoppedJobID: stoppedExecution?.jobID,
      stoppedJobLabel: stoppedJob?.capabilityLabel,
      recoveryAdvice: advice,
      canResume: canResume(
        plan: plan,
        stepExecutions: stepExecutions,
        isRunningWorkflow: isRunningWorkflow
      )
    )
  }

  func canResume(
    plan: AgentPlan?,
    stepExecutions: [AgentPlanStep.ID: AgentPlanStepExecution],
    isRunningWorkflow: Bool
  ) -> Bool {
    guard !isRunningWorkflow else { return false }
    let enabledSteps = plan?.steps.filter(\.isEnabled) ?? []
    guard !enabledSteps.isEmpty else { return false }
    let hasSuccessfulStep = enabledSteps.contains { stepExecutions[$0.id]?.status == .succeeded }
    let hasIncompleteStep = enabledSteps.contains { stepExecutions[$0.id]?.status != .succeeded }
    return hasSuccessfulStep && hasIncompleteStep
  }
}

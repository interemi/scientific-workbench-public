import Foundation

@MainActor
struct WorkflowExecutionCoordinator {
  struct Request {
    var plan: AgentPlan
    var capabilities: [CapabilityEntry]
    var inputPaths: [String]
    var existingStepExecutions: [AgentPlanStep.ID: AgentPlanStepExecution]
    var resumeFromPreviousSuccesses: Bool
    var allowRestrictedLocalAutomationSteps = false
  }

  struct StepRunRequest {
    var capability: CapabilityEntry
    var rawArguments: String
    var inputPaths: [String]
    var runDirectory: String
  }

  struct Callbacks {
    var isCancellationRequested: @MainActor () -> Bool
    var setCancellationRequested: @MainActor (Bool) -> Void
    var setRunningWorkflow: @MainActor (Bool) -> Void
    var setStatusMessage: @MainActor (String) -> Void
    var makeRunDirectory: @MainActor (CapabilityEntry) -> String
    var resolveRawArguments: @MainActor (String, String?, String?, [String: String]) -> String
    var runStep: @MainActor (StepRunRequest) async -> JobRecord?
    var recordStepExecution: @MainActor (AgentPlanStep.ID, AgentPlanStepExecution) -> Void
    var setSelectedJobID: @MainActor (JobRecord.ID) -> Void
    var writeWorkflowSummary: @MainActor ([AgentPlanStep], [JobRecord.ID], String, Date, Date) -> Void
    var persistAgentState: @MainActor () -> Void
  }

  @discardableResult
  func run(request: Request, callbacks: Callbacks) async -> String {
    let enabledSteps = request.plan.steps.enumerated().filter { $0.element.isEnabled }
    var previousRunDirectory: String?
    var completedRunDirectories: [String: String] = [:]
    var workflowJobIDs: [UUID] = []
    var completedCount = 0
    let workflowStartedAt = Date()
    let enabledPlanSteps = enabledSteps.map { $0.element }
    var startEnabledIndex = 0

    if request.resumeFromPreviousSuccesses {
      for (enabledIndex, indexedStep) in enabledSteps.enumerated() {
        let originalStepIndex = indexedStep.offset
        let step = indexedStep.element
        guard let execution = request.existingStepExecutions[step.id],
              execution.status == .succeeded else {
          startEnabledIndex = enabledIndex
          break
        }
        previousRunDirectory = execution.runDirectory
        completedRunDirectories[step.capabilityID] = execution.runDirectory
        completedRunDirectories["step\(originalStepIndex + 1)"] = execution.runDirectory
        workflowJobIDs.append(execution.jobID)
        completedCount += 1
        startEnabledIndex = enabledIndex + 1
      }

      if startEnabledIndex >= enabledSteps.count {
        let message = "Workflow already completed: \(completedCount)/\(enabledSteps.count) enabled step\(enabledSteps.count == 1 ? "" : "s") completed."
        callbacks.setStatusMessage(message)
        callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
        callbacks.setRunningWorkflow(false)
        callbacks.setCancellationRequested(false)
        callbacks.persistAgentState()
        return message
      }
    }

    for enabledIndex in startEnabledIndex..<enabledSteps.count {
      let indexedStep = enabledSteps[enabledIndex]
      let stepIndex = indexedStep.offset
      let step = indexedStep.element
      if callbacks.isCancellationRequested() {
        let message = "Workflow cancelled after \(completedCount)/\(enabledSteps.count) successful step\(enabledSteps.count == 1 ? "" : "s")."
        callbacks.setStatusMessage(message)
        callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
        callbacks.setRunningWorkflow(false)
        callbacks.setCancellationRequested(false)
        callbacks.persistAgentState()
        return message
      }

      guard let capability = request.capabilities.first(where: { $0.id == step.capabilityID }) else {
        let message = "Workflow stopped: unknown capability \(step.capabilityID)."
        callbacks.setStatusMessage(message)
        callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
        callbacks.setRunningWorkflow(false)
        callbacks.setCancellationRequested(false)
        callbacks.persistAgentState()
        return message
      }

      let explicitlyApprovedLocalAutomationStep =
        request.allowRestrictedLocalAutomationSteps &&
        request.plan.source == .local &&
        capability.requiresPlannerConfirmation &&
        !capability.isMaintainerOnly
      guard capability.appReadiness.isPlannerVisible || explicitlyApprovedLocalAutomationStep else {
        let message = "Workflow stopped: \(capability.label) is not available to normal workflow planning."
        callbacks.setStatusMessage(message)
        callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
        callbacks.setRunningWorkflow(false)
        callbacks.setCancellationRequested(false)
        callbacks.persistAgentState()
        return message
      }

      var stepInputs = step.usesInputs ? request.inputPaths : []
      if step.usesPreviousOutput, let previousRunDirectory,
         !stepInputs.contains(previousRunDirectory) {
        stepInputs.append(previousRunDirectory)
      }
      for referencedRunDirectory in WorkflowPlaceholderValidator.referencedRunDirectories(
        in: step.rawArguments,
        completedRunDirectories: completedRunDirectories
      ) where !stepInputs.contains(referencedRunDirectory) {
        stepInputs.append(referencedRunDirectory)
      }

      let plannedRunDirectory = callbacks.makeRunDirectory(capability)
      let rawArguments = callbacks.resolveRawArguments(
        step.rawArguments,
        plannedRunDirectory,
        previousRunDirectory,
        completedRunDirectories
      )
      let unresolvedTokens = WorkflowPlaceholderValidator.unresolvedTokens(in: rawArguments)
      if !unresolvedTokens.isEmpty {
        let message = "Workflow stopped before \(capability.label): unresolved placeholders \(unresolvedTokens.joined(separator: ", "))."
        callbacks.setStatusMessage(message)
        callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
        callbacks.setRunningWorkflow(false)
        callbacks.setCancellationRequested(false)
        callbacks.persistAgentState()
        return message
      }

      callbacks.setStatusMessage("Running \(capability.label)...")
      guard let job = await callbacks.runStep(
        StepRunRequest(
          capability: capability,
          rawArguments: rawArguments,
          inputPaths: stepInputs,
          runDirectory: plannedRunDirectory
        )
      ) else {
        let message = "Could not start \(capability.label)."
        callbacks.setStatusMessage(message)
        callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
        callbacks.setRunningWorkflow(false)
        callbacks.setCancellationRequested(false)
        callbacks.persistAgentState()
        return message
      }

      workflowJobIDs.append(job.id)
      previousRunDirectory = job.runDirectory
      completedRunDirectories[step.capabilityID] = job.runDirectory
      completedRunDirectories["step\(stepIndex + 1)"] = job.runDirectory
      callbacks.recordStepExecution(
        step.id,
        AgentPlanStepExecution(
          stepID: step.id,
          capabilityID: step.capabilityID,
          jobID: job.id,
          status: job.status,
          runDirectory: job.runDirectory,
          finishedAt: job.finishedAt
        )
      )
      if job.status != .succeeded {
        let message = "Workflow stopped at \(capability.label): \(job.status.title). Completed \(completedCount)/\(enabledSteps.count) enabled step\(enabledSteps.count == 1 ? "" : "s")."
        callbacks.setStatusMessage(message)
        callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
        callbacks.setRunningWorkflow(false)
        if job.status == .cancelled {
          callbacks.setCancellationRequested(false)
        }
        callbacks.setSelectedJobID(job.id)
        callbacks.persistAgentState()
        return message
      }
      completedCount += 1
      callbacks.persistAgentState()
    }

    let message = "Workflow finished: \(completedCount)/\(enabledSteps.count) enabled step\(enabledSteps.count == 1 ? "" : "s") completed."
    callbacks.setStatusMessage(message)
    callbacks.writeWorkflowSummary(enabledPlanSteps, workflowJobIDs, message, workflowStartedAt, Date())
    callbacks.setRunningWorkflow(false)
    callbacks.setCancellationRequested(false)
    callbacks.persistAgentState()
    return message
  }
}

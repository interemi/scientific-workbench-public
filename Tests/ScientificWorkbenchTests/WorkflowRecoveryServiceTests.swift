import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func workflowRecoveryServiceReportsResumeAfterSuccessfulStep() throws {
    let service = WorkflowRecoveryService()
    let environment = environmentCapability()
    let table = sampleCapability()
    let firstStep = AgentPlanStep(
      capabilityID: environment.id,
      summary: "Check environment.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let nextStep = AgentPlanStep(
      capabilityID: table.id,
      summary: "Profile table.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let plan = AgentPlan(
      title: "Recoverable workflow",
      rationale: "One step finished.",
      steps: [firstStep, nextStep],
      source: .local
    )
    let execution = AgentPlanStepExecution(
      stepID: firstStep.id,
      capabilityID: environment.id,
      jobID: UUID(),
      status: .succeeded,
      runDirectory: "/runs/step1",
      finishedAt: Date(timeIntervalSince1970: 1)
    )

    let recovery = try #require(service.state(
      plan: plan,
      stepExecutions: [firstStep.id: execution],
      jobs: [],
      isRunningWorkflow: false
    ))

    #expect(recovery.completedCount == 1)
    #expect(recovery.totalCount == 2)
    #expect(recovery.resumeStepIndex == 2)
    #expect(recovery.resumeStepCapabilityID == table.id)
    #expect(recovery.resumeStepSummary == "Profile table.")
    #expect(recovery.stoppedStatus == nil)
    #expect(recovery.canResume == true)
    #expect(recovery.recoveryAdvice == [
      "Review the plan before continuing.",
      "Run Dry Run if inputs, paths, or capability arguments have changed."
    ])
  }

  @Test
  func workflowRecoveryServiceUsesStoppedJobAdvice() throws {
    let service = WorkflowRecoveryService()
    let environment = environmentCapability()
    let table = sampleCapability()
    let firstStep = AgentPlanStep(
      capabilityID: environment.id,
      summary: "Check environment.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let blockedStep = AgentPlanStep(
      capabilityID: table.id,
      summary: "Profile table.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let plan = AgentPlan(
      title: "Blocked workflow",
      rationale: "A blocked job should explain the next action.",
      steps: [firstStep, blockedStep],
      source: .local
    )
    var blockedJob = JobRecord(capability: table, runDirectory: "/runs/profile")
    blockedJob.status = .blocked
    blockedJob.requestInputPaths = []
    blockedJob.message = "This guided run needs at least one input file or folder."
    let executions = [
      firstStep.id: AgentPlanStepExecution(
        stepID: firstStep.id,
        capabilityID: environment.id,
        jobID: UUID(),
        status: .succeeded,
        runDirectory: "/runs/env",
        finishedAt: Date(timeIntervalSince1970: 1)
      ),
      blockedStep.id: AgentPlanStepExecution(
        stepID: blockedStep.id,
        capabilityID: table.id,
        jobID: blockedJob.id,
        status: .blocked,
        runDirectory: "/runs/profile",
        finishedAt: Date(timeIntervalSince1970: 2)
      )
    ]

    let recovery = try #require(service.state(
      plan: plan,
      stepExecutions: executions,
      jobs: [blockedJob],
      isRunningWorkflow: false
    ))

    #expect(recovery.completedCount == 1)
    #expect(recovery.resumeStepCapabilityID == table.id)
    #expect(recovery.stoppedStatus == .blocked)
    #expect(recovery.stoppedJobID == blockedJob.id)
    #expect(recovery.stoppedJobLabel == table.label)
    #expect(recovery.recoveryAdvice.contains("Attach the required files or folders, then run Dry Run before retrying."))
  }

  @Test
  func workflowRecoveryServiceDoesNotResumeCompletedOrRunningWorkflow() {
    let service = WorkflowRecoveryService()
    let environment = environmentCapability()
    let step = AgentPlanStep(
      capabilityID: environment.id,
      summary: "Check environment.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let plan = AgentPlan(
      title: "Done",
      rationale: "Already complete.",
      steps: [step],
      source: .local
    )
    let execution = AgentPlanStepExecution(
      stepID: step.id,
      capabilityID: environment.id,
      jobID: UUID(),
      status: .succeeded,
      runDirectory: "/runs/env",
      finishedAt: Date(timeIntervalSince1970: 1)
    )

    #expect(service.state(
      plan: plan,
      stepExecutions: [step.id: execution],
      jobs: [],
      isRunningWorkflow: false
    ) == nil)
    #expect(service.canResume(
      plan: plan,
      stepExecutions: [step.id: execution],
      isRunningWorkflow: true
    ) == false)
  }
}

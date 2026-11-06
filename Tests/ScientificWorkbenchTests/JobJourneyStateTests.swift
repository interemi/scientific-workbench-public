import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func runningJobJourneyFindsCurrentRepeatedCapabilityStepWithoutInventingToolProgress() throws {
    let capability = sampleCapability()
    let first = AgentPlanStep(
      capabilityID: capability.id,
      summary: "Inspect the first copy.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let second = AgentPlanStep(
      capabilityID: capability.id,
      summary: "Inspect the second copy.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let plan = AgentPlan(
      title: "Repeated capability",
      rationale: "Each run has separate evidence.",
      steps: [first, second],
      source: .local
    )
    let priorJobID = UUID()
    let executions: [AgentPlanStep.ID: AgentPlanStepExecution] = [
      first.id: AgentPlanStepExecution(
        stepID: first.id,
        capabilityID: capability.id,
        jobID: priorJobID,
        status: .succeeded,
        runDirectory: "/runs/first",
        finishedAt: Date(timeIntervalSince1970: 10)
      )
    ]
    var job = JobRecord(capability: capability, runDirectory: "/runs/second")
    job.status = .running
    job.startedAt = Date(timeIntervalSince1970: 20)

    let journey = JobJourneyState(
      job: job,
      plan: plan,
      stepExecutions: executions,
      isRunningWorkflow: true,
      isCancellationRequested: false
    )

    #expect(journey.currentStep == "Workflow step 2 of 2: Inspect the second copy.")
    #expect(journey.lastActivityAt == job.startedAt)
    #expect(journey.jobStage == "External process running")
    #expect(journey.guidance.contains("Internal tool progress is unavailable"))
  }

  @Test
  func cancelledJobJourneyKeepsItsRetainedArtifactsAndFinishedActivity() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/runs/cancelled")
    job.status = .cancelled
    job.startedAt = Date(timeIntervalSince1970: 20)
    job.finishedAt = Date(timeIntervalSince1970: 25)
    job.artifacts = [Artifact(
      path: "/runs/cancelled/stdout.txt",
      relativePath: "stdout.txt",
      byteCount: 12,
      artifactType: "log_txt"
    )]

    let journey = JobJourneyState(
      job: job,
      plan: nil,
      stepExecutions: [:],
      isRunningWorkflow: false,
      isCancellationRequested: false
    )

    #expect(journey.jobStage == "Cancelled")
    #expect(journey.resultStage == "1 retained artifact")
    #expect(journey.lastActivityAt == job.finishedAt)
    #expect(journey.guidance.contains("before retrying"))
  }
}

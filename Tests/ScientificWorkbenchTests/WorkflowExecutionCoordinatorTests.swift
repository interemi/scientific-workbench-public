import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func workflowExecutionCoordinatorResumesAndStopsOnFailure() async throws {
    let coordinator = WorkflowExecutionCoordinator()
    let environment = environmentCapability()
    let table = sampleCapability()
    let firstStep = AgentPlanStep(
      capabilityID: environment.id,
      summary: "Check environment.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let failedStep = AgentPlanStep(
      capabilityID: table.id,
      summary: "Profile original inputs with previous output.",
      rawArguments: "{summaryJson:step1}",
      usesInputs: true,
      usesPreviousOutput: true
    )
    let finalStep = AgentPlanStep(
      capabilityID: environment.id,
      summary: "Confirm completion.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: true
    )
    let plan = AgentPlan(
      title: "Coordinator resume",
      rationale: "Resume should skip successful steps and stop on failure.",
      steps: [firstStep, failedStep, finalStep],
      source: .local
    )
    let completedJobID = UUID()
    let completedExecution = AgentPlanStepExecution(
      stepID: firstStep.id,
      capabilityID: environment.id,
      jobID: completedJobID,
      status: .succeeded,
      runDirectory: "/runs/step1",
      finishedAt: Date(timeIntervalSince1970: 1)
    )

    var statusMessages: [String] = []
    var runRequests: [WorkflowExecutionCoordinator.StepRunRequest] = []
    var resolverPreviousRunDirectory: String?
    var resolverCompletedRunDirectories: [String: String] = [:]
    var stepExecutions: [AgentPlanStep.ID: AgentPlanStepExecution] = [:]
    var selectedJobID: UUID?
    var summaries: [(jobIDs: [UUID], status: String)] = []
    var runningStates: [Bool] = []
    var cancellationStates: [Bool] = []
    var persistCount = 0

    let result = await coordinator.run(
      request: WorkflowExecutionCoordinator.Request(
        plan: plan,
        capabilities: [environment, table],
        inputPaths: ["/inputs/table.csv"],
        existingStepExecutions: [firstStep.id: completedExecution],
        resumeFromPreviousSuccesses: true
      ),
      callbacks: WorkflowExecutionCoordinator.Callbacks(
        isCancellationRequested: { false },
        setCancellationRequested: { cancellationStates.append($0) },
        setRunningWorkflow: { runningStates.append($0) },
        setStatusMessage: { statusMessages.append($0) },
        makeRunDirectory: { "/runs/\($0.id.replacingOccurrences(of: ".", with: "_"))" },
        resolveRawArguments: { rawArguments, _, previousRunDirectory, completedRunDirectories in
          resolverPreviousRunDirectory = previousRunDirectory
          resolverCompletedRunDirectories = completedRunDirectories
          return rawArguments.replacingOccurrences(
            of: "{previousRunDirectory}",
            with: previousRunDirectory ?? ""
          ).replacingOccurrences(
            of: "{summaryJson:step1}",
            with: "/runs/step1/summary.json"
          )
        },
        runStep: { request in
          runRequests.append(request)
          var job = JobRecord(capability: request.capability, runDirectory: request.runDirectory)
          job.requestInputPaths = request.inputPaths
          job.requestRawArguments = request.rawArguments
          job.status = .failed
          job.exitCode = 2
          job.finishedAt = Date(timeIntervalSince1970: 2)
          return job
        },
        recordStepExecution: { stepID, execution in
          stepExecutions[stepID] = execution
        },
        setSelectedJobID: { selectedJobID = $0 },
        writeWorkflowSummary: { _, jobIDs, status, _, _ in
          summaries.append((jobIDs, status))
        },
        persistAgentState: { persistCount += 1 }
      )
    )

    #expect(result == "Workflow stopped at profile_table.py: Failed. Completed 1/3 enabled steps.")
    #expect(statusMessages == [
      "Running profile_table.py...",
      "Workflow stopped at profile_table.py: Failed. Completed 1/3 enabled steps."
    ])
    #expect(runRequests.count == 1)
    let request = try #require(runRequests.first)
    #expect(request.capability.id == table.id)
    #expect(request.inputPaths == ["/inputs/table.csv", "/runs/step1"])
    #expect(request.rawArguments.contains("/runs/step1"))
    #expect(resolverPreviousRunDirectory == "/runs/step1")
    #expect(resolverCompletedRunDirectories[environment.id] == "/runs/step1")
    #expect(resolverCompletedRunDirectories["step1"] == "/runs/step1")
    #expect(stepExecutions[failedStep.id]?.status == .failed)
    #expect(stepExecutions[finalStep.id] == nil)
    #expect(summaries.count == 1)
    #expect(summaries.first?.jobIDs.first == completedJobID)
    #expect(summaries.first?.status == result)
    #expect(selectedJobID == stepExecutions[failedStep.id]?.jobID)
    #expect(runningStates == [false])
    #expect(cancellationStates.isEmpty)
    #expect(persistCount == 1)
  }

  @Test
  @MainActor
  func workflowExecutionCoordinatorCancelsBeforeRunningNextStep() async {
    let coordinator = WorkflowExecutionCoordinator()
    let environment = environmentCapability()
    let table = sampleCapability()
    let plan = AgentPlan(
      title: "Coordinator cancellation",
      rationale: "Cancellation should stop before launching a step.",
      steps: [
        AgentPlanStep(
          capabilityID: environment.id,
          summary: "Check environment.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: table.id,
          summary: "Profile table.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        )
      ],
      source: .local
    )
    var didRunStep = false
    var statusMessages: [String] = []
    var runningStates: [Bool] = []
    var cancellationStates: [Bool] = []
    var summaryStatus: String?
    var persistCount = 0

    let result = await coordinator.run(
      request: WorkflowExecutionCoordinator.Request(
        plan: plan,
        capabilities: [environment, table],
        inputPaths: ["/inputs/table.csv"],
        existingStepExecutions: [:],
        resumeFromPreviousSuccesses: false
      ),
      callbacks: WorkflowExecutionCoordinator.Callbacks(
        isCancellationRequested: { true },
        setCancellationRequested: { cancellationStates.append($0) },
        setRunningWorkflow: { runningStates.append($0) },
        setStatusMessage: { statusMessages.append($0) },
        makeRunDirectory: { _ in "/runs/unused" },
        resolveRawArguments: { rawArguments, _, _, _ in rawArguments },
        runStep: { _ in
          didRunStep = true
          return nil
        },
        recordStepExecution: { _, _ in },
        setSelectedJobID: { _ in },
        writeWorkflowSummary: { _, _, status, _, _ in summaryStatus = status },
        persistAgentState: { persistCount += 1 }
      )
    )

    #expect(result == "Workflow cancelled after 0/2 successful steps.")
    #expect(statusMessages == ["Workflow cancelled after 0/2 successful steps."])
    #expect(!didRunStep)
    #expect(summaryStatus == result)
    #expect(runningStates == [false])
    #expect(cancellationStates == [false])
    #expect(persistCount == 1)
  }

  @Test
  @MainActor
  func workflowExecutionCoordinatorAuthorizesOnlyExplicitNamedDependencies() async throws {
    let coordinator = WorkflowExecutionCoordinator()
    let environment = environmentCapability()
    let table = sampleCapability()
    let fits = expertFITSCapability()
    let plan = AgentPlan(
      title: "Named dependency authorization",
      rationale: "A non-adjacent completed run referenced by placeholders is a traced input.",
      steps: [
        AgentPlanStep(
          capabilityID: environment.id,
          summary: "Create the referenced run.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: table.id,
          summary: "Create an unrelated immediate previous run.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: fits.id,
          summary: "Consume only the explicitly named first run.",
          rawArguments: "{runDirectory:step1} {artifactsDir:\(environment.id)} {summaryJson:step1} {manifestJson:\(environment.id)} /runs/profile_table",
          usesInputs: false,
          usesPreviousOutput: false
        )
      ],
      source: .local
    )
    var runRequests: [WorkflowExecutionCoordinator.StepRunRequest] = []

    let result = await coordinator.run(
      request: WorkflowExecutionCoordinator.Request(
        plan: plan,
        capabilities: [environment, table, fits],
        inputPaths: [],
        existingStepExecutions: [:],
        resumeFromPreviousSuccesses: false
      ),
      callbacks: WorkflowExecutionCoordinator.Callbacks(
        isCancellationRequested: { false },
        setCancellationRequested: { _ in },
        setRunningWorkflow: { _ in },
        setStatusMessage: { _ in },
        makeRunDirectory: { "/runs/\($0.id)" },
        resolveRawArguments: { rawArguments, _, _, completedRunDirectories in
          completedRunDirectories.reduce(rawArguments) { resolved, entry in
            let (identifier, runDirectory) = entry
            return resolved
              .replacingOccurrences(of: "{runDirectory:\(identifier)}", with: runDirectory)
              .replacingOccurrences(
                of: "{artifactsDir:\(identifier)}",
                with: "\(runDirectory)/artifacts"
              )
              .replacingOccurrences(
                of: "{summaryJson:\(identifier)}",
                with: "\(runDirectory)/summary.json"
              )
              .replacingOccurrences(
                of: "{manifestJson:\(identifier)}",
                with: "\(runDirectory)/manifest.json"
              )
          }
        },
        runStep: { request in
          runRequests.append(request)
          var job = JobRecord(capability: request.capability, runDirectory: request.runDirectory)
          job.status = .succeeded
          job.exitCode = 0
          job.finishedAt = Date()
          return job
        },
        recordStepExecution: { _, _ in },
        setSelectedJobID: { _ in },
        writeWorkflowSummary: { _, _, _, _, _ in },
        persistAgentState: {}
      )
    )

    #expect(result == "Workflow finished: 3/3 enabled steps completed.")
    #expect(runRequests.count == 3)
    let dependentRequest = try #require(runRequests.last)
    #expect(dependentRequest.inputPaths == ["/runs/datanalysis_env.status"])
    #expect(!dependentRequest.inputPaths.contains("/runs/profile_table"))
    #expect(WorkflowPlaceholderValidator.unresolvedTokens(in: dependentRequest.rawArguments).isEmpty)
  }

  @Test
  @MainActor
  func workflowExecutionCoordinatorBlocksUnresolvedPlaceholdersBeforeRun() async {
    let coordinator = WorkflowExecutionCoordinator()
    let capability = sampleCapability()
    let plan = AgentPlan(
      title: "Unresolved dependency",
      rationale: "The command must not start.",
      steps: [
        AgentPlanStep(
          capabilityID: capability.id,
          summary: "Use a missing artifact.",
          rawArguments: "--source {summaryJson:missing_step}",
          usesInputs: false,
          usesPreviousOutput: false
        )
      ],
      source: .skillRouter
    )
    var didRunStep = false
    var statusMessages: [String] = []

    let result = await coordinator.run(
      request: WorkflowExecutionCoordinator.Request(
        plan: plan,
        capabilities: [capability],
        inputPaths: [],
        existingStepExecutions: [:],
        resumeFromPreviousSuccesses: false
      ),
      callbacks: WorkflowExecutionCoordinator.Callbacks(
        isCancellationRequested: { false },
        setCancellationRequested: { _ in },
        setRunningWorkflow: { _ in },
        setStatusMessage: { statusMessages.append($0) },
        makeRunDirectory: { _ in "/runs/profile" },
        resolveRawArguments: { rawArguments, _, _, _ in rawArguments },
        runStep: { _ in
          didRunStep = true
          return nil
        },
        recordStepExecution: { _, _ in },
        setSelectedJobID: { _ in },
        writeWorkflowSummary: { _, _, _, _, _ in },
        persistAgentState: {}
      )
    )

    #expect(!didRunStep)
    #expect(result.contains("unresolved placeholders {summaryJson:missing_step}"))
    #expect(statusMessages == [result])
  }

  @Test
  @MainActor
  func workflowExecutionCoordinatorRejectsNonPlannerVisibleCapabilityBeforeRun() async {
    let coordinator = WorkflowExecutionCoordinator()
    let maintainer = maintainerCapability()
    let plan = AgentPlan(
      title: "Injected maintainer plan",
      rationale: "A malformed or stale plan must fail closed.",
      steps: [
        AgentPlanStep(
          capabilityID: maintainer.id,
          summary: "Run a maintainer gate.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: false,
          isEnabled: true
        )
      ],
      source: .skillRouter
    )
    var didCreateRunDirectory = false
    var didRunStep = false
    var statusMessages: [String] = []
    var summaryStatus: String?

    let result = await coordinator.run(
      request: WorkflowExecutionCoordinator.Request(
        plan: plan,
        capabilities: [maintainer],
        inputPaths: [],
        existingStepExecutions: [:],
        resumeFromPreviousSuccesses: false
      ),
      callbacks: WorkflowExecutionCoordinator.Callbacks(
        isCancellationRequested: { false },
        setCancellationRequested: { _ in },
        setRunningWorkflow: { _ in },
        setStatusMessage: { statusMessages.append($0) },
        makeRunDirectory: { _ in
          didCreateRunDirectory = true
          return "/runs/forbidden"
        },
        resolveRawArguments: { rawArguments, _, _, _ in rawArguments },
        runStep: { _ in
          didRunStep = true
          return nil
        },
        recordStepExecution: { _, _ in },
        setSelectedJobID: { _ in },
        writeWorkflowSummary: { _, _, status, _, _ in summaryStatus = status },
        persistAgentState: {}
      )
    )

    #expect(!didCreateRunDirectory)
    #expect(!didRunStep)
    #expect(result.contains("is not available to normal workflow planning"))
    #expect(statusMessages == [result])
    #expect(summaryStatus == result)
  }

  @Test
  @MainActor
  func workflowExecutionCoordinatorAllowsExplicitRestrictedLocalAutomationOnly() async {
    let coordinator = WorkflowExecutionCoordinator()
    let legacy = legacyCLIOnlyCapability()
    let step = AgentPlanStep(
      capabilityID: legacy.id,
      summary: "Run the reviewed legacy preflight.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false,
      isEnabled: true
    )
    let plan = AgentPlan(
      title: "Reviewed local legacy automation",
      rationale: "The launch caller explicitly approved restricted local steps.",
      steps: [step],
      source: .local
    )
    var didRunStep = false

    let result = await coordinator.run(
      request: WorkflowExecutionCoordinator.Request(
        plan: plan,
        capabilities: [legacy],
        inputPaths: [],
        existingStepExecutions: [:],
        resumeFromPreviousSuccesses: false,
        allowRestrictedLocalAutomationSteps: true
      ),
      callbacks: WorkflowExecutionCoordinator.Callbacks(
        isCancellationRequested: { false },
        setCancellationRequested: { _ in },
        setRunningWorkflow: { _ in },
        setStatusMessage: { _ in },
        makeRunDirectory: { _ in "/runs/reviewed-legacy" },
        resolveRawArguments: { rawArguments, _, _, _ in rawArguments },
        runStep: { request in
          didRunStep = true
          var job = JobRecord(capability: request.capability, runDirectory: request.runDirectory)
          job.status = .succeeded
          job.exitCode = 0
          job.finishedAt = Date()
          return job
        },
        recordStepExecution: { _, _ in },
        setSelectedJobID: { _ in },
        writeWorkflowSummary: { _, _, _, _, _ in },
        persistAgentState: {}
      )
    )

    #expect(didRunStep)
    #expect(result == "Workflow finished: 1/1 enabled step completed.")
  }
}

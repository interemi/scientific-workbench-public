import Foundation

enum SkillWorkflowRouterError: LocalizedError {
  case missingRouter(String)
  case processFailed(Int32, String)
  case invalidPayload(String)
  case releaseBlocked(String)

  var errorDescription: String? {
    switch self {
    case .missingRouter(let path):
      return "Could not find scientific_workflow_router.py at \(path)."
    case .processFailed(let exitCode, let message):
      return "The skill workflow router exited with \(exitCode): \(message)"
    case .invalidPayload(let message):
      return "The skill workflow router returned invalid JSON: \(message)"
    case .releaseBlocked(let status):
      return "The skill workflow router returned release-blocking status \(status)."
    }
  }

  var isReleaseBlocking: Bool {
    if case .releaseBlocked = self { return true }
    return false
  }
}

private struct SkillWorkflowRouterEnvelope: Decodable {
  var status: String
  var appStatus: String?
  var inputKind: String
  var recommendedCapabilities: [SkillWorkflowRouterRecommendation]
  var safetyNotes: [String]
  var warnings: [String]?

  enum CodingKeys: String, CodingKey {
    case status
    case appStatus = "app_status"
    case inputKind = "input_kind"
    case recommendedCapabilities = "recommended_capabilities"
    case safetyNotes = "safety_notes"
    case warnings
  }
}

private struct SkillWorkflowRouterRecommendation: Decodable {
  var capabilityID: String
  var reason: String
  var appReadiness: CapabilityAppReadiness?
  var workflowMode: CapabilityWorkflowMode?
  var requiresConfirmation: Bool?
  var usesInputs: Bool?
  var usesPreviousOutput: Bool?
  var appRawArguments: String?

  enum CodingKeys: String, CodingKey {
    case capabilityID = "capability_id"
    case reason
    case appReadiness = "app_readiness"
    case workflowMode = "workflow_mode"
    case requiresConfirmation = "requires_confirmation"
    case usesInputs = "uses_inputs"
    case usesPreviousOutput = "uses_previous_output"
    case appRawArguments = "app_raw_arguments"
  }
}

struct SkillWorkflowRouterClient: Sendable {
  typealias CommandRunner = @Sendable (ProcessCommand) async throws -> ProcessResult

  private let runCommand: CommandRunner

  init(runner: ProcessRunner = ProcessRunner()) {
    runCommand = { command in
      try await runner.run(command)
    }
  }

  init(runCommand: @escaping CommandRunner) {
    self.runCommand = runCommand
  }

  func plan(
    prompt: String,
    inputPaths: [String],
    capabilities: [CapabilityEntry],
    skillRoot: String,
    pythonExecutable: String
  ) async throws -> AgentPlan {
    let routerPath = URL(fileURLWithPath: skillRoot)
      .appendingPathComponent("scripts/scientific_workflow_router.py")
      .path
    guard FileManager.default.fileExists(atPath: routerPath) else {
      throw SkillWorkflowRouterError.missingRouter(routerPath)
    }

    var envelopes: [SkillWorkflowRouterEnvelope] = []
    for inputPath in inputPaths {
      let command = ProcessCommand(
        executable: pythonExecutable.isEmpty ? DefaultPaths.systemPython : pythonExecutable,
        arguments: [routerPath, "plan", inputPath, "--task", prompt],
        workingDirectory: skillRoot,
        timeoutSeconds: 30,
        environmentPolicy: .restricted,
        environmentOverrides: SkillPythonEnvironment.overrides(forSkillRoot: skillRoot)
      )
      let result = try await runCommand(command)
      guard result.exitCode == 0 else {
        let message = [result.stderr, result.stdout]
          .first { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
          ?? "No diagnostic output."
        throw SkillWorkflowRouterError.processFailed(result.exitCode, message)
      }
      guard let envelope = JSONOutputExtractor.decodeLast(
        SkillWorkflowRouterEnvelope.self,
        from: result.stdout
      ) else {
        throw SkillWorkflowRouterError.invalidPayload("No complete workflow-router JSON object was found.")
      }
      envelopes.append(envelope)
    }

    let blockingStatuses: Set<String> = ["FAIL", "FAILED", "ERROR", "ROTO"]
    let reportedBlockingStatuses = envelopes
      .flatMap { [$0.status, $0.appStatus].compactMap(\.self) }
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
      .filter { blockingStatuses.contains($0) }
    if !reportedBlockingStatuses.isEmpty {
      throw SkillWorkflowRouterError.releaseBlocked(
        Array(Set(reportedBlockingStatuses)).sorted().joined(separator: ", ")
      )
    }

    let knownCapabilities = Dictionary(uniqueKeysWithValues: capabilities.plannerVisible.map { ($0.id, $0) })
    var steps: [AgentPlanStep] = []
    var seenCapabilityIDs = Set<String>()

    func appendStep(
      capabilityID: String,
      summary: String,
      rawArguments: String,
      usesInputs: Bool,
      usesPreviousOutput: Bool,
      requiresConfirmation: Bool,
      appReadiness: CapabilityAppReadiness
    ) {
      guard let capability = knownCapabilities[capabilityID],
            capability.appReadiness.isPlannerVisible else { return }
      guard seenCapabilityIDs.insert(capabilityID).inserted else { return }
      let confirmation = requiresConfirmation
        ? " Review this \(capability.workflowMode.rawValue) / \(appReadiness.rawValue) step and enable it explicitly."
        : ""
      steps.append(
        AgentPlanStep(
          capabilityID: capabilityID,
          summary: summary + confirmation,
          rawArguments: rawArguments,
          usesInputs: usesInputs,
          usesPreviousOutput: usesPreviousOutput,
          isEnabled: !requiresConfirmation
        )
      )
    }

    if envelopes.contains(where: { !$0.recommendedCapabilities.isEmpty }) {
      appendStep(
        capabilityID: "datanalysis_env.status",
        summary: "Check the skill execution environment before running the planned workflow.",
        rawArguments: "",
        usesInputs: false,
        usesPreviousOutput: false,
        requiresConfirmation: false,
        appReadiness: knownCapabilities["datanalysis_env.status"]?.appReadiness ?? .appReady
      )
    }

    for recommendation in envelopes.flatMap(\.recommendedCapabilities) {
      guard let capability = knownCapabilities[recommendation.capabilityID] else { continue }
      guard capability.appReadiness.isPlannerVisible else { continue }
      let reportedMode = recommendation.workflowMode ?? capability.workflowMode
      let reportedReadiness = recommendation.appReadiness ?? capability.appReadiness
      let appReadiness = capability.appReadiness.allowsAutomaticEnablement
        ? reportedReadiness
        : capability.appReadiness
      appendStep(
        capabilityID: recommendation.capabilityID,
        summary: recommendation.reason,
        rawArguments: recommendation.appRawArguments ?? "",
        usesInputs: recommendation.usesInputs ?? (capability.guidedRunRequirement != .noInput),
        usesPreviousOutput: recommendation.usesPreviousOutput ?? false,
        requiresConfirmation: (recommendation.requiresConfirmation ?? false) ||
          reportedMode.requiresExplicitConfirmation ||
          capability.requiresPlannerConfirmation ||
          !appReadiness.allowsAutomaticEnablement,
        appReadiness: appReadiness
      )
    }

    let inputKinds = Set(envelopes.map(\.inputKind))
    if inputPaths.count > 1, inputKinds.count > 1, knownCapabilities["cross_domain_data_workbench"] != nil {
      appendStep(
        capabilityID: "cross_domain_data_workbench",
        summary: "Combine the independently routed inputs into one traceable mixed-data handoff.",
        rawArguments: "",
        usesInputs: true,
        usesPreviousOutput: false,
        requiresConfirmation: knownCapabilities["cross_domain_data_workbench"]!.requiresPlannerConfirmation,
        appReadiness: knownCapabilities["cross_domain_data_workbench"]!.appReadiness
      )
    }

    let statuses = envelopes.map { $0.appStatus ?? $0.status }
    let notes = envelopes.flatMap(\.safetyNotes)
    let warnings = envelopes.flatMap { $0.warnings ?? [] }
    let readinessClasses = Set(
      envelopes
        .flatMap(\.recommendedCapabilities)
        .compactMap { knownCapabilities[$0.capabilityID]?.appReadiness }
        .map(\.rawValue)
    )
    let rationaleParts = [
      "Planned by scientific_workflow_router.py from the configured skill.",
      statuses.isEmpty ? nil : "Router statuses: \(statuses.joined(separator: ", ")).",
      readinessClasses.isEmpty ? nil : "App-readiness: \(readinessClasses.sorted().joined(separator: ", ")).",
      notes.isEmpty ? nil : notes.joined(separator: " "),
      warnings.isEmpty ? nil : "Warnings: \(warnings.joined(separator: " "))",
    ].compactMap(\.self)

    return AgentPlan(
      title: steps.isEmpty ? "Skill router blocked plan" : "Skill router workflow plan",
      rationale: rationaleParts.joined(separator: "\n"),
      steps: steps,
      source: .skillRouter
    )
  }
}

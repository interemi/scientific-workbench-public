import Foundation

enum LaunchTranscriptError: LocalizedError {
  case destinationAlreadyExists(String)

  var errorDescription: String? {
    switch self {
    case .destinationAlreadyExists(let path):
      return "The launch transcript already exists and will not be overwritten: \(path)"
    }
  }
}

struct LaunchTranscriptSnapshot {
  var generatedAt: Date
  var inputPaths: [String]
  var outputRootPath: String
  var agentMode: AgentRunMode
  var aiProvider: AIProvider
  var aiModel: String
  var aiBaseURL: String?
  var autoRun: Bool
  var status: String
  var setupChecklistItems: [SetupChecklistItem]
  var setupRecoveryState: SetupRecoveryState?
  var agentPlan: AgentPlan?
  var messages: [AgentChatMessage]
  var jobs: [JobRecord]
}

struct LaunchTranscriptService {
  func write(
    to path: String,
    snapshot: LaunchTranscriptSnapshot,
    redact: (String) -> String
  ) throws {
    let url = URL(fileURLWithPath: path)
    guard !FileManager.default.fileExists(atPath: url.path) else {
      throw LaunchTranscriptError.destinationAlreadyExists(url.path)
    }
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )

    let payload = LaunchTranscriptPayload(snapshot: snapshot, redact: redact)
    let data = try JSONEncoder.scientificWorkbench.encode(payload)
    try data.write(to: url)
  }
}

private struct ExplicitNullCodable<Value: Codable>: Codable {
  var value: Value?

  init(_ value: Value?) {
    self.value = value
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    value = container.decodeNil() ? nil : try container.decode(Value.self)
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    if let value {
      try container.encode(value)
    } else {
      try container.encodeNil()
    }
  }
}

private struct LaunchTranscriptPayload: Codable {
  var generatedAt: Date
  var inputPaths: [String]
  var outputRoot: String
  var agentMode: String
  var aiProvider: String
  var aiModel: String
  var aiBaseURL: ExplicitNullCodable<String>
  var autoRun: Bool
  var status: String
  var setupChecklist: [LaunchTranscriptChecklistItemPayload]
  var setupRecovery: ExplicitNullCodable<LaunchTranscriptSetupRecoveryPayload>
  var agentPlan: ExplicitNullCodable<LaunchTranscriptPlanPayload>
  var messages: [LaunchTranscriptMessagePayload]
  var jobs: [LaunchTranscriptJobPayload]

  init(snapshot: LaunchTranscriptSnapshot, redact: (String) -> String) {
    generatedAt = snapshot.generatedAt
    inputPaths = snapshot.inputPaths.map(redact)
    outputRoot = redact(snapshot.outputRootPath)
    agentMode = snapshot.agentMode.rawValue
    aiProvider = snapshot.aiProvider.rawValue
    aiModel = snapshot.aiModel
    aiBaseURL = ExplicitNullCodable(snapshot.aiBaseURL)
    autoRun = snapshot.autoRun
    status = redact(snapshot.status)
    setupChecklist = snapshot.setupChecklistItems.map { LaunchTranscriptChecklistItemPayload(item: $0, redact: redact) }
    setupRecovery = ExplicitNullCodable(snapshot.setupRecoveryState.map { LaunchTranscriptSetupRecoveryPayload(recovery: $0, redact: redact) })
    agentPlan = ExplicitNullCodable(snapshot.agentPlan.map { LaunchTranscriptPlanPayload(plan: $0, redact: redact) })
    messages = snapshot.messages.map { LaunchTranscriptMessagePayload(message: $0, redact: redact) }
    jobs = snapshot.jobs.map { LaunchTranscriptJobPayload(job: $0, redact: redact) }
  }

  private enum CodingKeys: String, CodingKey {
    case generatedAt = "generated_at"
    case inputPaths = "input_paths"
    case outputRoot = "output_root"
    case agentMode = "agent_mode"
    case aiProvider = "ai_provider"
    case aiModel = "ai_model"
    case aiBaseURL = "ai_base_url"
    case autoRun = "auto_run"
    case status
    case setupChecklist = "setup_checklist"
    case setupRecovery = "setup_recovery"
    case agentPlan = "agent_plan"
    case messages
    case jobs
  }
}

private struct LaunchTranscriptChecklistItemPayload: Codable {
  var id: String
  var title: String
  var detail: String
  var state: String
  var badge: String
  var isRequired: Bool

  init(item: SetupChecklistItem, redact: (String) -> String) {
    id = item.id
    title = redact(item.title)
    detail = redact(item.detail)
    state = item.state.rawValue
    badge = item.state.badgeTitle
    isRequired = item.isRequired
  }

  private enum CodingKeys: String, CodingKey {
    case id
    case title
    case detail
    case state
    case badge
    case isRequired = "is_required"
  }
}

private struct LaunchTranscriptSetupRecoveryPayload: Codable {
  var title: String
  var detail: String
  var badge: String
  var blockingItemIDs: [String]
  var recommendedActions: [String]

  init(recovery: SetupRecoveryState, redact: (String) -> String) {
    title = redact(recovery.title)
    detail = redact(recovery.detail)
    badge = recovery.badgeTitle
    blockingItemIDs = recovery.blockingItemIDs.map(redact)
    recommendedActions = recovery.recommendedActions.map(redact)
  }

  private enum CodingKeys: String, CodingKey {
    case title
    case detail
    case badge
    case blockingItemIDs = "blocking_item_ids"
    case recommendedActions = "recommended_actions"
  }
}

private struct LaunchTranscriptPlanPayload: Codable {
  var id: UUID
  var title: String
  var rationale: String
  var source: String
  var createdAt: Date
  var estimate: LaunchTranscriptPlanEstimatePayload
  var steps: [LaunchTranscriptPlanStepPayload]

  init(plan: AgentPlan, redact: (String) -> String) {
    let planEstimate = AgentPlanEstimate.estimate(plan: plan)
    id = plan.id
    title = redact(plan.title)
    rationale = redact(plan.rationale)
    source = plan.source.rawValue
    createdAt = plan.createdAt
    estimate = LaunchTranscriptPlanEstimatePayload(estimate: planEstimate)
    steps = plan.steps.map { LaunchTranscriptPlanStepPayload(step: $0, redact: redact) }
  }

  private enum CodingKeys: String, CodingKey {
    case id
    case title
    case rationale
    case source
    case createdAt = "created_at"
    case estimate
    case steps
  }
}

private struct LaunchTranscriptPlanEstimatePayload: Codable {
  var enabledStepCount: Int
  var minSeconds: Int
  var maxSeconds: Int
  var runtimeText: String
  var costNote: String
  var caution: ExplicitNullCodable<String>

  init(estimate: AgentPlanEstimate) {
    enabledStepCount = estimate.enabledStepCount
    minSeconds = estimate.minSeconds
    maxSeconds = estimate.maxSeconds
    runtimeText = estimate.runtimeText
    costNote = estimate.costNote
    caution = ExplicitNullCodable(estimate.caution)
  }

  private enum CodingKeys: String, CodingKey {
    case enabledStepCount = "enabled_step_count"
    case minSeconds = "min_seconds"
    case maxSeconds = "max_seconds"
    case runtimeText = "runtime_text"
    case costNote = "cost_note"
    case caution
  }
}

private struct LaunchTranscriptPlanStepPayload: Codable {
  var id: UUID
  var capabilityID: String
  var summary: String
  var rawArguments: String
  var usesInputs: Bool
  var usesPreviousOutput: Bool
  var isEnabled: Bool

  init(step: AgentPlanStep, redact: (String) -> String) {
    id = step.id
    capabilityID = step.capabilityID
    summary = redact(step.summary)
    rawArguments = redact(step.rawArguments)
    usesInputs = step.usesInputs
    usesPreviousOutput = step.usesPreviousOutput
    isEnabled = step.isEnabled
  }

  private enum CodingKeys: String, CodingKey {
    case id
    case capabilityID = "capability_id"
    case summary
    case rawArguments = "raw_arguments"
    case usesInputs = "uses_inputs"
    case usesPreviousOutput = "uses_previous_output"
    case isEnabled = "is_enabled"
  }
}

private struct LaunchTranscriptMessagePayload: Codable {
  var role: String
  var text: String
  var createdAt: Date

  init(message: AgentChatMessage, redact: (String) -> String) {
    role = message.role.rawValue
    text = redact(message.text)
    createdAt = message.createdAt
  }

  private enum CodingKeys: String, CodingKey {
    case role
    case text
    case createdAt = "created_at"
  }
}

private struct LaunchTranscriptJobPayload: Codable {
  var id: UUID
  var capabilityID: String
  var capabilityLabel: String
  var status: String
  var runDirectory: String
  var createdAt: Date
  var startedAt: ExplicitNullCodable<Date>
  var finishedAt: ExplicitNullCodable<Date>
  var exitCode: ExplicitNullCodable<Int>
  var parsedTool: ExplicitNullCodable<String>
  var parsedStatus: ExplicitNullCodable<String>
  var message: ExplicitNullCodable<String>
  var artifactCount: Int
  var artifacts: [LaunchTranscriptArtifactPayload]
  var recoveryAdvice: [String]

  init(job: JobRecord, redact: (String) -> String) {
    id = job.id
    capabilityID = job.capabilityID
    capabilityLabel = job.capabilityLabel
    status = job.status.rawValue
    runDirectory = redact(job.runDirectory)
    createdAt = job.createdAt
    startedAt = ExplicitNullCodable(job.startedAt)
    finishedAt = ExplicitNullCodable(job.finishedAt)
    exitCode = ExplicitNullCodable(job.exitCode.map(Int.init))
    parsedTool = ExplicitNullCodable(job.parsedTool)
    parsedStatus = ExplicitNullCodable(job.parsedStatus)
    message = ExplicitNullCodable(job.message.map(redact))
    artifactCount = job.artifacts.count
    artifacts = job.artifacts.map { LaunchTranscriptArtifactPayload(artifact: $0, redact: redact) }
    recoveryAdvice = job.recoveryAdvice.map(redact)
  }

  private enum CodingKeys: String, CodingKey {
    case id
    case capabilityID = "capability_id"
    case capabilityLabel = "capability_label"
    case status
    case runDirectory = "run_directory"
    case createdAt = "created_at"
    case startedAt = "started_at"
    case finishedAt = "finished_at"
    case exitCode = "exit_code"
    case parsedTool = "parsed_tool"
    case parsedStatus = "parsed_status"
    case message
    case artifactCount = "artifact_count"
    case artifacts
    case recoveryAdvice = "recovery_advice"
  }
}

private struct LaunchTranscriptArtifactPayload: Codable {
  var relativePath: String
  var path: String
  var byteCount: Int

  init(artifact: Artifact, redact: (String) -> String) {
    relativePath = artifact.relativePath
    path = redact(artifact.path)
    byteCount = Int(artifact.byteCount)
  }

  private enum CodingKeys: String, CodingKey {
    case relativePath = "relative_path"
    case path
    case byteCount = "byte_count"
  }
}

import Foundation

enum AgentChatRole: String, Codable, Sendable {
  case assistant
  case user
  case system
}

enum AgentRunMode: String, CaseIterable, Identifiable, Codable, Sendable {
  case auto
  case chat
  case workflow
  case codex

  var id: String { rawValue }

  var title: String {
    switch self {
    case .auto: return "Auto"
    case .chat: return "Chat"
    case .workflow: return "Workflow"
    case .codex: return "Codex"
    }
  }
}

enum AIProvider: String, CaseIterable, Identifiable, Codable, Sendable {
  case ollama
  case openAI
  case grok
  case gemini

  var id: String { rawValue }

  var title: String {
    switch self {
    case .ollama: return "Ollama"
    case .openAI: return "OpenAI"
    case .grok: return "Grok"
    case .gemini: return "Gemini"
    }
  }

  var defaultModel: String {
    switch self {
    case .ollama: return "qwen3:4b-instruct"
    case .openAI: return "gpt-5.2"
    case .grok: return "grok-4.3"
    case .gemini: return "gemini-3.5-flash-lite"
    }
  }

  var requiresAPIKey: Bool {
    switch self {
    case .ollama: return false
    case .openAI, .grok, .gemini: return true
    }
  }

  var defaultBaseURL: String? {
    switch self {
    case .ollama: return "http://localhost:11434"
    case .openAI, .grok, .gemini: return nil
    }
  }

  var connectionKind: String {
    switch self {
    case .ollama: return "Local, no API key"
    case .openAI, .grok, .gemini: return "Cloud API key"
    }
  }
}

enum CloudAttachmentContextMode: String, CaseIterable, Identifiable, Codable, Sendable {
  case previews
  case filenamesOnly
  case none

  var id: String { rawValue }

  var title: String {
    switch self {
    case .previews: return "Text previews"
    case .filenamesOnly: return "Filenames only"
    case .none: return "No attachment context"
    }
  }

  var boundaryTitle: String {
    switch self {
    case .previews: return "text previews"
    case .filenamesOnly: return "filenames only"
    case .none: return "no attachment context"
    }
  }

  var detail: String {
    switch self {
    case .previews:
      return "Cloud providers may receive attached file names plus short text previews from supported files."
    case .filenamesOnly:
      return "Cloud providers receive attached file or folder names only. File contents and directory listings are withheld."
    case .none:
      return "Cloud providers receive no attachment names, paths, previews, or directory listings."
    }
  }
}

enum CloudRequestPurpose: String, Hashable, Sendable {
  case chat
  case workflowPlanning

  var title: String {
    switch self {
    case .chat: return "Chat response"
    case .workflowPlanning: return "Workflow planning"
    }
  }
}

enum CloudDataCategory: String, Identifiable, Hashable, Sendable {
  case currentMessage
  case recentConversation
  case attachmentCount
  case attachmentFilenames
  case attachmentPreviews
  case workflowRecoveryStatus
  case workflowRecoveryFilenames
  case workflowRecoveryExcerpts
  case capabilityCatalog
  case deterministicRouterPlan

  var id: String { rawValue }

  var title: String {
    switch self {
    case .currentMessage: return "Current message"
    case .recentConversation: return "Recent conversation"
    case .attachmentCount: return "Attachment count only"
    case .attachmentFilenames: return "Attachment filenames"
    case .attachmentPreviews: return "Attachment previews"
    case .workflowRecoveryStatus: return "Workflow recovery status"
    case .workflowRecoveryFilenames: return "Recovery filenames"
    case .workflowRecoveryExcerpts: return "Recovery text and log excerpts"
    case .capabilityCatalog: return "Available capability catalog"
    case .deterministicRouterPlan: return "Deterministic router plan"
    }
  }

  var detail: String {
    switch self {
    case .currentMessage:
      return "The message you are sending now."
    case .recentConversation:
      return "Up to the 12 most recent chat messages."
    case .attachmentCount:
      return "Only how many items are selected; no names, paths, listings, or contents."
    case .attachmentFilenames:
      return "Last path components only; absolute paths are withheld."
    case .attachmentPreviews:
      return "Short supported-text previews or immediate directory listings, with absolute paths withheld."
    case .workflowRecoveryStatus:
      return "Step counts, resume position, completion state, and exit status."
    case .workflowRecoveryFilenames:
      return "Run-folder and summary filenames only; absolute paths are withheld."
    case .workflowRecoveryExcerpts:
      return "Short job messages, advice, stdout, and stderr excerpts, with absolute paths withheld."
    case .capabilityCatalog:
      return "IDs and descriptions of the installed capabilities available to the planner."
    case .deterministicRouterPlan:
      return "The locally generated safety-baseline plan used to constrain cloud planning."
    }
  }

  var systemImage: String {
    switch self {
    case .currentMessage: return "text.bubble"
    case .recentConversation: return "bubble.left.and.bubble.right"
    case .attachmentCount: return "number"
    case .attachmentFilenames: return "doc"
    case .attachmentPreviews: return "doc.text.magnifyingglass"
    case .workflowRecoveryStatus: return "arrow.clockwise.circle"
    case .workflowRecoveryFilenames: return "folder"
    case .workflowRecoveryExcerpts: return "text.alignleft"
    case .capabilityCatalog: return "square.grid.2x2"
    case .deterministicRouterPlan: return "list.bullet.clipboard"
    }
  }
}

enum CloudConsentApprovalScope: String, CaseIterable, Identifiable, Hashable, Sendable {
  case requestOnly
  case appSession

  var id: String { rawValue }

  var title: String {
    switch self {
    case .requestOnly: return "This request only"
    case .appSession: return "Remember for this app session"
    }
  }

  var detail: String {
    switch self {
    case .requestOnly:
      return "Scientific Workbench will ask again before the next cloud request."
    case .appSession:
      return "Approves these categories, not the current values, for this provider, model, purpose, and privacy mode until the app closes. Future prompts, history, or inputs may differ; a change to provider, model, purpose, privacy mode, or category list requires another review."
    }
  }
}

enum CloudConsentInputKind: String, Hashable, Sendable {
  case missing
  case file
  case directory
}

struct CloudConsentHistoryItem: Hashable, Sendable {
  var role: AgentChatRole
  var text: String
}

struct CloudConsentInputFingerprint: Hashable, Sendable {
  var canonicalPath: String
  var presentedName: String
  var kind: CloudConsentInputKind
  var byteCount: Int64?
  var modificationTime: TimeInterval?
  var previewBytes: Data?
  var directoryPreviewEntries: [String]
}

struct CloudConsentCapabilityFingerprint: Hashable, Sendable {
  var id: String
  var label: String
  var visibleBlock: String
  var shortDescription: String
  var guidedRequirement: String
  var appReadiness: String
  var workflowMode: String
}

struct CloudConsentFingerprint: Hashable, Sendable {
  var provider: AIProvider
  var model: String
  var purpose: CloudRequestPurpose
  var prompt: String
  var history: [CloudConsentHistoryItem]
  var inputs: [CloudConsentInputFingerprint]
  var attachmentContextMode: CloudAttachmentContextMode
  var categories: [CloudDataCategory]
  var workflowRecoveryContext: String?
  var capabilityCatalog: [CloudConsentCapabilityFingerprint]

  static let empty = CloudConsentFingerprint(
    provider: .openAI,
    model: "",
    purpose: .chat,
    prompt: "",
    history: [],
    inputs: [],
    attachmentContextMode: .none,
    categories: [],
    workflowRecoveryContext: nil,
    capabilityCatalog: []
  )
}

struct CloudConsentSessionScope: Hashable, Sendable {
  var provider: AIProvider
  var model: String
  var purpose: CloudRequestPurpose
  var attachmentContextMode: CloudAttachmentContextMode
  var categories: [CloudDataCategory]
}

struct CloudConsentRequest: Identifiable, Hashable, Sendable {
  let id: UUID
  var provider: AIProvider
  var model: String
  var purpose: CloudRequestPurpose
  var categories: [CloudDataCategory]
  var attachmentContextMode: CloudAttachmentContextMode
  var fingerprint: CloudConsentFingerprint

  var sessionScope: CloudConsentSessionScope {
    CloudConsentSessionScope(
      provider: provider,
      model: model,
      purpose: purpose,
      attachmentContextMode: attachmentContextMode,
      categories: categories
    )
  }

  init(
    id: UUID = UUID(),
    provider: AIProvider,
    model: String,
    purpose: CloudRequestPurpose,
    categories: [CloudDataCategory],
    attachmentContextMode: CloudAttachmentContextMode,
    fingerprint: CloudConsentFingerprint = .empty
  ) {
    self.id = id
    self.provider = provider
    self.model = model
    self.purpose = purpose
    self.categories = categories
    self.attachmentContextMode = attachmentContextMode
    self.fingerprint = fingerprint
  }
}

enum AIConnectionState: String, Codable, Sendable {
  case unknown
  case missingKey
  case testing
  case connected
  case invalidKey
  case quotaOrRateLimit
  case modelUnavailable
  case networkIssue
  case timedOut
  case failed

  var badgeTitle: String {
    switch self {
    case .unknown: return "unknown"
    case .missingKey: return "missing key"
    case .testing: return "testing"
    case .connected: return "connected"
    case .invalidKey: return "invalid key"
    case .quotaOrRateLimit: return "quota/rate"
    case .modelUnavailable: return "model unavailable"
    case .networkIssue: return "network"
    case .timedOut: return "timeout"
    case .failed: return "failed"
    }
  }
}

struct AIConnectionStatus: Hashable, Codable, Sendable {
  var state: AIConnectionState = .unknown
  var message: String = "Not tested yet."
  var checkedAt: Date?

  static let unknown = AIConnectionStatus()
}

struct AgentChatMessage: Identifiable, Hashable, Codable, Sendable {
  let id: UUID
  var role: AgentChatRole
  var text: String
  var createdAt: Date

  init(id: UUID = UUID(), role: AgentChatRole, text: String, createdAt: Date = Date()) {
    self.id = id
    self.role = role
    self.text = text
    self.createdAt = createdAt
  }
}

enum AgentPlanSource: String, Codable, Sendable {
  case local
  case skillRouter
  case ollama
  case openAI
  case grok
  case gemini

  var title: String {
    switch self {
    case .local: return "Local planner"
    case .skillRouter: return "Skill router"
    case .ollama: return "Ollama"
    case .openAI: return "OpenAI"
    case .grok: return "Grok"
    case .gemini: return "Gemini"
    }
  }

  init(provider: AIProvider) {
    switch provider {
    case .ollama: self = .ollama
    case .openAI: self = .openAI
    case .grok: self = .grok
    case .gemini: self = .gemini
    }
  }
}

struct AgentPlan: Identifiable, Hashable, Codable, Sendable {
  let id: UUID
  var title: String
  var rationale: String
  var steps: [AgentPlanStep]
  var source: AgentPlanSource
  var createdAt: Date

  init(
    id: UUID = UUID(),
    title: String,
    rationale: String,
    steps: [AgentPlanStep],
    source: AgentPlanSource,
    createdAt: Date = Date()
  ) {
    self.id = id
    self.title = title
    self.rationale = rationale
    self.steps = steps
    self.source = source
    self.createdAt = createdAt
  }
}

struct AgentPlanStep: Identifiable, Hashable, Codable, Sendable {
  let id: UUID
  var capabilityID: String
  var summary: String
  var rawArguments: String
  var usesInputs: Bool
  var usesPreviousOutput: Bool
  var isEnabled: Bool

  init(
    id: UUID = UUID(),
    capabilityID: String,
    summary: String,
    rawArguments: String,
    usesInputs: Bool,
    usesPreviousOutput: Bool,
    isEnabled: Bool = true
  ) {
    self.id = id
    self.capabilityID = capabilityID
    self.summary = summary
    self.rawArguments = rawArguments
    self.usesInputs = usesInputs
    self.usesPreviousOutput = usesPreviousOutput
    self.isEnabled = isEnabled
  }
}

struct AgentPlanStepExecution: Identifiable, Hashable, Codable, Sendable {
  let id: UUID
  var stepID: AgentPlanStep.ID
  var capabilityID: String
  var jobID: JobRecord.ID
  var status: JobStatus
  var runDirectory: String
  var finishedAt: Date?

  init(
    id: UUID = UUID(),
    stepID: AgentPlanStep.ID,
    capabilityID: String,
    jobID: JobRecord.ID,
    status: JobStatus,
    runDirectory: String,
    finishedAt: Date?
  ) {
    self.id = id
    self.stepID = stepID
    self.capabilityID = capabilityID
    self.jobID = jobID
    self.status = status
    self.runDirectory = runDirectory
    self.finishedAt = finishedAt
  }
}

struct WorkflowRecoveryState: Identifiable, Codable, Hashable, Sendable {
  var id: UUID
  var completedCount: Int
  var totalCount: Int
  var resumeStepIndex: Int
  var resumeStepCapabilityID: String
  var resumeStepSummary: String
  var stoppedStatus: JobStatus?
  var stoppedJobID: UUID?
  var stoppedJobLabel: String?
  var recoveryAdvice: [String]
  var canResume: Bool

  var title: String {
    if let stoppedJobLabel, let stoppedStatus {
      return "Workflow stopped at \(stoppedJobLabel): \(stoppedStatus.title)"
    }
    return "Workflow can continue from step \(resumeStepIndex)"
  }

  var detail: String {
    "Completed \(completedCount)/\(totalCount) enabled steps. Next recoverable step: \(resumeStepSummary)"
  }

  var badgeTitle: String {
    stoppedStatus?.rawValue ?? "resume"
  }
}

struct AgentPlanEstimate: Hashable, Sendable {
  var enabledStepCount: Int
  var minSeconds: Int
  var maxSeconds: Int
  var costNote: String
  var caution: String?

  var runtimeText: String {
    guard enabledStepCount > 0 else { return "No enabled steps" }
    if minSeconds == maxSeconds {
      return "Estimated runtime: \(Self.format(seconds: minSeconds))"
    }
    return "Estimated runtime: \(Self.format(seconds: minSeconds))-\(Self.format(seconds: maxSeconds))"
  }

  static func estimate(plan: AgentPlan) -> AgentPlanEstimate {
    let enabledSteps = plan.steps.filter(\.isEnabled)
    let ranges = enabledSteps.map(runtimeRange(for:))
    let minSeconds = ranges.reduce(0) { $0 + $1.min }
    let maxSeconds = ranges.reduce(0) { $0 + $1.max }
    return AgentPlanEstimate(
      enabledStepCount: enabledSteps.count,
      minSeconds: minSeconds,
      maxSeconds: maxSeconds,
      costNote: costNote(for: plan.source),
      caution: caution(forMaxSeconds: maxSeconds, stepCount: enabledSteps.count)
    )
  }

  private static func runtimeRange(for step: AgentPlanStep) -> (min: Int, max: Int) {
    switch step.capabilityID {
    case "datanalysis_env.status":
      return (2, 10)
    case "datanalysis_healthcheck", "env_doctor":
      return (5, 30)
    case "profile_table", "inspect_fits", "inspect_data_container":
      return (5, 45)
    case "document_intake_workbench":
      return (15, 180)
    case "cross_domain_data_workbench":
      return (30, 240)
    case "echelle_multispec_inventory":
      return (20, 180)
    case "legacy_spectroscopy_envcheck":
      return (5, 45)
    case "fxcor_iraf_workbench.prepare-session", "istarmod_workbench.inspect-tree", "istarmod_workbench.prepare-copy":
      return (20, 180)
    case "fxcor_iraf_workbench.run-auto":
      return (120, 900)
    case "legacy_rv_coursework_workbench.analyze", "legacy_external_reference_check", "li6708_equivalent_width_workbench.measure":
      return (30, 300)
    case "legacy_spectroscopy_report_builder.scaffold", "legacy_spectroscopy_report_builder.populate":
      return (15, 180)
    case "latex_workbench.review", "latex_workbench.compile":
      return (20, 240)
    default:
      return step.rawArguments.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        ? (15, 180)
        : (30, 300)
    }
  }

  private static func costNote(for source: AgentPlanSource) -> String {
    switch source {
    case .local, .skillRouter:
      return "Local planning and local execution; no cloud API cost."
    case .ollama:
      return "Ollama local planning and local execution; no cloud API cost."
    case .openAI:
      return "Planning may use OpenAI API quota; execution remains local."
    case .grok:
      return "Planning may use Grok/xAI API quota; execution remains local."
    case .gemini:
      return "Planning may use Gemini API quota; execution remains local."
    }
  }

  private static func caution(forMaxSeconds maxSeconds: Int, stepCount: Int) -> String? {
    if stepCount == 0 {
      return "Enable at least one step before running."
    }
    if maxSeconds >= 600 {
      return "Long workflow: use Dry Run first and expect external-tool variance."
    }
    if stepCount >= 6 {
      return "Multi-step workflow: review dependencies before auto-run."
    }
    return nil
  }

  private static func format(seconds: Int) -> String {
    if seconds < 60 {
      return "\(seconds)s"
    }
    let minutes = Int(ceil(Double(seconds) / 60.0))
    if minutes < 60 {
      return "\(minutes)min"
    }
    let hours = minutes / 60
    let remainder = minutes % 60
    return remainder == 0 ? "\(hours)h" : "\(hours)h \(remainder)min"
  }
}

struct AgentPlanPayload: Decodable {
  var title: String?
  var rationale: String?
  var steps: [AgentPlanStepPayload]
}

struct AgentPlanStepPayload: Decodable {
  var capabilityID: String?
  var capability_id: String?
  var summary: String?
  var rawArguments: String?
  var raw_arguments: String?
  var usesInputs: Bool?
  var uses_inputs: Bool?
  var usesPreviousOutput: Bool?
  var uses_previous_output: Bool?
  var isEnabled: Bool?
  var is_enabled: Bool?

  var normalizedCapabilityID: String? {
    capabilityID ?? capability_id
  }

  var normalizedRawArguments: String {
    rawArguments ?? raw_arguments ?? ""
  }

  var normalizedUsesInputs: Bool {
    usesInputs ?? uses_inputs ?? true
  }

  var normalizedUsesPreviousOutput: Bool {
    usesPreviousOutput ?? uses_previous_output ?? false
  }

  var normalizedIsEnabled: Bool {
    isEnabled ?? is_enabled ?? true
  }
}

struct ExportedAgentPlanPayload: Codable, Sendable {
  static let currentVersion = 2

  var version: Int
  var generatedAt: Date
  var outputRootPath: String
  var inputPaths: [String]
  var aiProvider: AIProvider
  var aiModel: String
  var mode: AgentRunMode
  var autoRun: Bool
  var plan: AgentPlan
}

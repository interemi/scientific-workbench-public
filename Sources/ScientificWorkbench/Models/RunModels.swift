import Foundation

enum AppSection: String, CaseIterable, Codable, Identifiable, Sendable {
  case agent
  case home
  case capabilities
  case jobs
  case results
  case maintenance
  case settings

  var id: String { rawValue }

  var title: String {
    switch self {
    case .agent: return "Chat"
    case .home: return "Dashboard"
    case .capabilities: return "Capabilities"
    case .jobs: return "Jobs"
    case .results: return "Results"
    case .maintenance: return "Maintenance"
    case .settings: return "Settings"
    }
  }

  var detail: String {
    switch self {
    case .agent: return "Ask, attach, run"
    case .home: return "Readiness overview"
    case .capabilities: return "Browse tools"
    case .jobs: return "Queue, logs, and status"
    case .results: return "Artifacts and previews"
    case .maintenance: return "Advanced gates"
    case .settings: return "Setup and paths"
    }
  }

  var iconName: String {
    switch self {
    case .agent: return "sparkles"
    case .home: return "gauge"
    case .capabilities: return "square.grid.2x2"
    case .jobs: return "list.bullet.rectangle"
    case .results: return "doc.richtext"
    case .maintenance: return "wrench.and.screwdriver"
    case .settings: return "gearshape"
    }
  }
}

enum SetupChecklistState: String, Codable, Hashable, Sendable {
  case ready
  case action
  case optional

  var badgeTitle: String {
    switch self {
    case .ready: return "ok"
    case .action: return "action"
    case .optional: return "optional"
    }
  }
}

struct SetupChecklistItem: Identifiable, Codable, Hashable, Sendable {
  let id: String
  var title: String
  var detail: String
  var state: SetupChecklistState
  var systemImage: String
  var isRequired: Bool
}

struct SetupRecoveryState: Codable, Hashable, Sendable {
  var title: String
  var detail: String
  var blockingItemIDs: [String]
  var recommendedActions: [String]

  var badgeTitle: String {
    blockingItemIDs.isEmpty ? "ok" : "action"
  }
}

struct RunRequest: Identifiable, Hashable, Sendable {
  let id: UUID
  let capabilityID: String
  let inputPaths: [String]
  let outputDirectory: String
  let rawArguments: String
  let createdAt: Date

  init(
    id: UUID = UUID(),
    capabilityID: String,
    inputPaths: [String],
    outputDirectory: String,
    rawArguments: String,
    createdAt: Date = Date()
  ) {
    self.id = id
    self.capabilityID = capabilityID
    self.inputPaths = inputPaths
    self.outputDirectory = outputDirectory
    self.rawArguments = rawArguments
    self.createdAt = createdAt
  }
}

enum JobStatus: String, CaseIterable, Codable, Sendable {
  case queued
  case running
  case succeeded
  case failed
  case blocked
  case cancelled
  case timedOut = "timeout"

  var title: String {
    switch self {
    case .queued: return "Queued"
    case .running: return "Running"
    case .succeeded: return "Succeeded"
    case .failed: return "Failed"
    case .blocked: return "Blocked"
    case .cancelled: return "Cancelled"
    case .timedOut: return "Timed Out"
    }
  }

  static func resolved(
    exitCode: Int32,
    envelopeStatus: String?,
    appStatus: String?
  ) -> JobStatus {
    let normalized = [appStatus, envelopeStatus]
      .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
    let blockedStatuses: Set<String> = ["BLOCKED_CONTROLADO", "BLOCKED"]
    let failureStatuses: Set<String> = ["FAIL", "FAILED", "ERROR", "ROTO"]
    if !failureStatuses.isDisjoint(with: normalized) {
      return .failed
    }
    if !blockedStatuses.isDisjoint(with: normalized) {
      return .blocked
    }
    return exitCode == 0 ? .succeeded : .failed
  }
}

struct JobStructuredError: Codable, Hashable, Sendable {
  var kind: String
  var message: String
  var recoveryHint: String?
}

struct JobNextAction: Codable, Hashable, Sendable, Identifiable {
  var label: String
  var kind: String?
  var priority: String?

  var id: String {
    [label, kind, priority].compactMap(\.self).joined(separator: "|")
  }
}

struct Artifact: Identifiable, Hashable, Codable, Sendable {
  let id: UUID
  let path: String
  let relativePath: String
  let byteCount: Int64
  var artifactType: String?
  var label: String?
  var primary: Bool?

  init(
    id: UUID = UUID(),
    path: String,
    relativePath: String,
    byteCount: Int64,
    artifactType: String? = nil,
    label: String? = nil,
    primary: Bool? = nil
  ) {
    self.id = id
    self.path = path
    self.relativePath = relativePath
    self.byteCount = byteCount
    self.artifactType = artifactType
    self.label = label
    self.primary = primary
  }

  var url: URL {
    URL(fileURLWithPath: path)
  }
}

struct JobRecord: Identifiable, Hashable, Codable, Sendable {
  let id: UUID
  let capabilityID: String
  let capabilityLabel: String
  var requestInputPaths: [String]
  var requestRawArguments: String
  var retryOfJobID: UUID?
  var status: JobStatus
  var command: String
  var stdout: String
  var stderr: String
  var exitCode: Int32?
  var runDirectory: String
  var artifacts: [Artifact]
  var parsedTool: String?
  var parsedStatus: String?
  var message: String?
  var contractVersion: String?
  var appStatus: String?
  var shortSummary: String?
  var severity: String?
  var originalModified: String?
  var warnings: [String]
  var structuredErrors: [JobStructuredError]
  var nextActions: [JobNextAction]
  var previewArtifactTypes: [String]
  var tags: [String]
  let createdAt: Date
  var startedAt: Date?
  var finishedAt: Date?

  init(capability: CapabilityEntry, runDirectory: String, createdAt: Date = Date()) {
    id = UUID()
    capabilityID = capability.id
    capabilityLabel = capability.label
    requestInputPaths = []
    requestRawArguments = ""
    retryOfJobID = nil
    status = .queued
    command = ""
    stdout = ""
    stderr = ""
    exitCode = nil
    self.runDirectory = runDirectory
    artifacts = []
    parsedTool = nil
    parsedStatus = nil
    message = nil
    contractVersion = nil
    appStatus = nil
    shortSummary = nil
    severity = nil
    originalModified = nil
    warnings = []
    structuredErrors = []
    nextActions = []
    previewArtifactTypes = []
    tags = []
    self.createdAt = createdAt
    startedAt = nil
    finishedAt = nil
  }

  var durationText: String {
    guard let startedAt, let finishedAt else { return "-" }
    return DateFormatters.duration.string(from: finishedAt.timeIntervalSince(startedAt)) ?? "-"
  }

  var displaySeverity: String {
    guard status == .succeeded else { return status.rawValue }
    let structuredStatuses = [severity, appStatus, parsedStatus]
      .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
    if !warnings.isEmpty || structuredStatuses.contains("WARNING") || structuredStatuses.contains("WARN") {
      return "warning"
    }
    return status.rawValue
  }

  var recoveryAdvice: [String] {
    switch status {
    case .succeeded, .queued, .running:
      return []
    case .cancelled:
      return [
        "The run was cancelled before completion.",
        "Retry the job if the inputs and external tools are still in the expected state."
      ]
    case .timedOut:
      return timedOutRecoveryAdvice
    case .blocked:
      return blockedRecoveryAdvice
    case .failed:
      return failedRecoveryAdvice
    }
  }

  private var blockedRecoveryAdvice: [String] {
    let text = [message, stderr, stdout, parsedStatus].compactMap(\.self).joined(separator: "\n").localizedLowercase
    if text.contains("needs at least one input") || (text.contains("input") && requestInputPaths.isEmpty) {
      return [
        "This job needs input paths that were not available.",
        "Attach the required files or folders, then run Dry Run before retrying."
      ]
    }
    if text.contains("capability is not available") || text.contains("could not resolve tool") {
      return [
        "The requested capability is missing from the current registry.",
        "Reload the registry and confirm the installed scientific-data-analysis skill is the expected version."
      ]
    }
    return [
      "The job was blocked before execution could complete.",
      "Read the structured stdout/stderr, fix the missing precondition, then retry."
    ]
  }

  private var failedRecoveryAdvice: [String] {
    let text = [message, stderr, stdout, parsedStatus].compactMap(\.self).joined(separator: "\n").localizedLowercase
    if parsedStatus == "blocked" || text.contains("\"status\": \"blocked\"") {
      return [
        "The process ran, but the tool reported a blocked structured status.",
        "Use the tool notes in stdout to fix the precondition; retrying unchanged may fail again."
      ]
    }
    if text.contains("timed out") || text.contains("timeout") || text.contains("did not finish within") {
      return timedOutRecoveryAdvice
    }
    if text.contains("permission") || text.contains("operation not permitted") {
      return [
        "The job hit a permission problem.",
        "Check file access, output folder permissions, and whether macOS privacy prompts need approval."
      ]
    }
    if let exitCode {
      return [
        "The process exited with code \(exitCode).",
        "Inspect stderr/stdout, then retry only after the cause is understood."
      ]
    }
    return [
      "The job failed without a specific recovery pattern.",
      "Inspect stdout/stderr and retry only if the underlying precondition has changed."
    ]
  }

  private var timedOutRecoveryAdvice: [String] {
    [
      "The job reached the configured capability timeout.",
      "Increase Capability timeout in Settings for legitimately long tools; otherwise inspect logs or reduce inputs before retrying."
    ]
  }

  enum CodingKeys: String, CodingKey {
    case id
    case capabilityID
    case capabilityLabel
    case requestInputPaths
    case requestRawArguments
    case retryOfJobID
    case status
    case command
    case stdout
    case stderr
    case exitCode
    case runDirectory
    case artifacts
    case parsedTool
    case parsedStatus
    case message
    case contractVersion
    case appStatus
    case shortSummary
    case severity
    case originalModified
    case warnings
    case structuredErrors
    case nextActions
    case previewArtifactTypes
    case tags
    case createdAt
    case startedAt
    case finishedAt
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(UUID.self, forKey: .id)
    capabilityID = try container.decode(String.self, forKey: .capabilityID)
    capabilityLabel = try container.decode(String.self, forKey: .capabilityLabel)
    requestInputPaths = try container.decodeIfPresent([String].self, forKey: .requestInputPaths) ?? []
    requestRawArguments = try container.decodeIfPresent(String.self, forKey: .requestRawArguments) ?? ""
    retryOfJobID = try container.decodeIfPresent(UUID.self, forKey: .retryOfJobID)
    status = try container.decode(JobStatus.self, forKey: .status)
    command = try container.decodeIfPresent(String.self, forKey: .command) ?? ""
    stdout = try container.decodeIfPresent(String.self, forKey: .stdout) ?? ""
    stderr = try container.decodeIfPresent(String.self, forKey: .stderr) ?? ""
    exitCode = try container.decodeIfPresent(Int32.self, forKey: .exitCode)
    runDirectory = try container.decode(String.self, forKey: .runDirectory)
    artifacts = try container.decodeIfPresent([Artifact].self, forKey: .artifacts) ?? []
    parsedTool = try container.decodeIfPresent(String.self, forKey: .parsedTool)
    parsedStatus = try container.decodeIfPresent(String.self, forKey: .parsedStatus)
    message = try container.decodeIfPresent(String.self, forKey: .message)
    contractVersion = try container.decodeIfPresent(String.self, forKey: .contractVersion)
    appStatus = try container.decodeIfPresent(String.self, forKey: .appStatus)
    shortSummary = try container.decodeIfPresent(String.self, forKey: .shortSummary)
    severity = try container.decodeIfPresent(String.self, forKey: .severity)
    originalModified = try container.decodeIfPresent(String.self, forKey: .originalModified)
    warnings = try container.decodeIfPresent([String].self, forKey: .warnings) ?? []
    structuredErrors = try container.decodeIfPresent([JobStructuredError].self, forKey: .structuredErrors) ?? []
    nextActions = try container.decodeIfPresent([JobNextAction].self, forKey: .nextActions) ?? []
    previewArtifactTypes = try container.decodeIfPresent([String].self, forKey: .previewArtifactTypes) ?? []
    tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
    createdAt = try container.decode(Date.self, forKey: .createdAt)
    startedAt = try container.decodeIfPresent(Date.self, forKey: .startedAt)
    finishedAt = try container.decodeIfPresent(Date.self, forKey: .finishedAt)
  }
}

struct EnvironmentStatus: Codable, Hashable, Sendable {
  var status: String
  var skillRoot: String
  var datanalysisPython: String?
  var datanalysisRoot: String?
  var details: String
  var warnings: [String]
  var refreshedAt: Date?

  static func unknown(skillRoot: String) -> EnvironmentStatus {
    EnvironmentStatus(
      status: "unknown",
      skillRoot: skillRoot,
      datanalysisPython: nil,
      datanalysisRoot: nil,
      details: "Not checked yet.",
      warnings: [],
      refreshedAt: nil
    )
  }
}

struct ProcessCommand: Equatable, Sendable {
  let executable: String
  let arguments: [String]
  let workingDirectory: String?
  var timeoutSeconds: TimeInterval? = nil
  var environmentPolicy: ProcessEnvironmentPolicy = .restricted
  var environmentOverrides: [String: String] = [:]
  var redirectStandardInputToNull = false

  var pretty: String {
    ([executable] + arguments).map(ShellWords.quote).joined(separator: " ")
  }
}

struct ProcessResult: Equatable, Sendable {
  let exitCode: Int32
  let stdout: String
  let stderr: String
  let startedAt: Date
  let finishedAt: Date
  let stdoutTotalBytes: Int
  let stderrTotalBytes: Int
  let stdoutWasTruncated: Bool
  let stderrWasTruncated: Bool

  init(
    exitCode: Int32,
    stdout: String,
    stderr: String,
    startedAt: Date,
    finishedAt: Date,
    stdoutTotalBytes: Int? = nil,
    stderrTotalBytes: Int? = nil,
    stdoutWasTruncated: Bool = false,
    stderrWasTruncated: Bool = false
  ) {
    self.exitCode = exitCode
    self.stdout = stdout
    self.stderr = stderr
    self.startedAt = startedAt
    self.finishedAt = finishedAt
    self.stdoutTotalBytes = stdoutTotalBytes ?? stdout.utf8.count
    self.stderrTotalBytes = stderrTotalBytes ?? stderr.utf8.count
    self.stdoutWasTruncated = stdoutWasTruncated
    self.stderrWasTruncated = stderrWasTruncated
  }
}

extension JSONEncoder {
  static var scientificWorkbench: JSONEncoder {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    return encoder
  }
}

extension JSONDecoder {
  static var scientificWorkbench: JSONDecoder {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return decoder
  }
}

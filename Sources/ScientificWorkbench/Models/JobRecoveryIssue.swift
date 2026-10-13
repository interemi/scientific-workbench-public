import Foundation

enum SettingsRecoverySection: Hashable {
  case environment
  case paths
  case behavior
  case optionalBackends
  case localAI
  case connections
}

enum JobRecoveryIssue: String, Sendable {
  case missingInput
  case outputConflict
  case permissionDenied
  case diskSpace
  case optionalBackend
  case pythonEnvironment
  case timedOut
  case network
  case modelUnavailable

  static func detect(in job: JobRecord) -> Self? {
    guard job.status == .blocked || job.status == .failed || job.status == .timedOut else {
      return nil
    }
    if job.status == .timedOut {
      return .timedOut
    }

    let kinds = Set(job.structuredErrors.map { $0.kind.localizedLowercase })
    let evidence = ([job.message, job.stderr] + job.structuredErrors.map(\.message))
      .compactMap { $0 }
      .joined(separator: "\n")
      .localizedLowercase

    if kinds.contains("output_conflict") || evidence.contains("output already exists")
        || evidence.contains("output target exists") || evidence.contains("parent is not a directory") {
      return .outputConflict
    }
    if kinds.contains("permission_denied") || evidence.contains("permission denied")
        || evidence.contains("permissionerror") || evidence.contains("operation not permitted") {
      return .permissionDenied
    }
    if evidence.contains("no space left on device") || evidence.contains("enospc")
        || evidence.contains("disk full") {
      return .diskSpace
    }
    if kinds.contains("missing_optional_backend") || kinds.contains("missing_pdf_backend")
        || evidence.contains("optional backend unavailable") {
      return .optionalBackend
    }
    if kinds.contains("dependency_error") || evidence.contains("modulenotfounderror")
        || evidence.contains("no module named") || evidence.contains("python executable")
        || evidence.contains("datanalysis environment") {
      return .pythonEnvironment
    }
    if kinds.contains("network_error") || evidence.contains("could not connect to ollama") {
      return .network
    }
    if kinds.contains("model_unavailable") || evidence.contains("ollama model was not found") {
      return .modelUnavailable
    }
    if kinds.contains("timeout") || evidence.contains("timed out") {
      return .timedOut
    }
    if kinds.contains("missing_input") || evidence.contains("needs at least one input") {
      return .missingInput
    }
    return nil
  }

  var title: String {
    switch self {
    case .missingInput: return "Required input is missing"
    case .outputConflict: return "Output destination is occupied"
    case .permissionDenied: return "File access was denied"
    case .diskSpace: return "Available disk space may be insufficient"
    case .optionalBackend: return "An optional backend is unavailable"
    case .pythonEnvironment: return "The Python environment needs attention"
    case .timedOut: return "The run exceeded its time limit"
    case .network: return "The AI connection needs attention"
    case .modelUnavailable: return "The selected local model is unavailable"
    }
  }

  var guidance: String {
    switch self {
    case .missingInput:
      return "Attach the required input to a new run and inspect Dry Run before starting it."
    case .outputConflict:
      return "Choose a new output destination for the next run. Keep the existing output and inspect the command before retrying."
    case .permissionDenied:
      return "Review the input and output paths, macOS file access, and the original error before starting a new run."
    case .diskSpace:
      return "Check free space on the volume used by the output root. Preserve existing runs; select another output root if needed."
    case .optionalBackend:
      return "Inspect the backend named in the error and its setup instructions. Optional tools are not installed automatically."
    case .pythonEnvironment:
      return "Check the selected Python and scientific-data environment. Rechecking only diagnoses readiness; it does not install packages."
    case .timedOut:
      return "Inspect the logs and input size. Increase the capability timeout only if this work is expected to take longer."
    case .network:
      return "Check the configured endpoint and connection in Settings before sending another request."
    case .modelUnavailable:
      return "Choose an installed Ollama model or continue with the deterministic local workflow. Downloading a model needs your action."
    }
  }

  var actionLabel: String {
    switch self {
    case .missingInput: return "Prepare New Run"
    case .outputConflict: return "Prepare New Output"
    case .permissionDenied: return "Review Paths"
    case .diskSpace: return "Review Output Root"
    case .optionalBackend: return "Review Backend Setup"
    case .pythonEnvironment: return "Review Python Setup"
    case .timedOut: return "Review Timeout"
    case .network: return "Review AI Connection"
    case .modelUnavailable: return "Review Local Model"
    }
  }

  var opensCapability: Bool {
    self == .missingInput || self == .outputConflict
  }

  var offersFilesystemRecheck: Bool {
    self == .missingInput || self == .outputConflict
      || self == .permissionDenied || self == .diskSpace
  }

  func offersLocalAIRecheck(for job: JobRecord) -> Bool {
    guard self == .network || self == .modelUnavailable else { return false }
    let messages = [job.message, job.stderr] + job.structuredErrors.map(\.message)
    return messages.compactMap { $0 }.contains {
      $0.localizedCaseInsensitiveContains("ollama")
    }
  }

  func settingsSection(for job: JobRecord) -> SettingsRecoverySection? {
    switch self {
    case .missingInput, .outputConflict:
      return nil
    case .permissionDenied, .diskSpace:
      return .paths
    case .optionalBackend:
      return .optionalBackends
    case .pythonEnvironment:
      return .environment
    case .timedOut:
      return .behavior
    case .network, .modelUnavailable:
      return offersLocalAIRecheck(for: job) ? .localAI : .connections
    }
  }
}

extension JobRecord {
  var recoveryIssue: JobRecoveryIssue? {
    JobRecoveryIssue.detect(in: self)
  }
}

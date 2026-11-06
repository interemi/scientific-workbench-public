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

  func title(for job: JobRecord) -> String {
    switch self {
    case .missingInput: return "Required input is missing"
    case .outputConflict: return "Output destination is occupied"
    case .permissionDenied: return "File access was denied"
    case .diskSpace: return "Available disk space may be insufficient"
    case .optionalBackend: return "An optional backend is unavailable"
    case .pythonEnvironment: return "The Python environment needs attention"
    case .timedOut: return "The run exceeded its time limit"
    case .network:
      return usesAIConnectionSettings(for: job)
        ? "The AI connection needs attention"
        : "The capability's network connection needs attention"
    case .modelUnavailable:
      if offersLocalAIRecheck(for: job) {
        return "The selected local model is unavailable"
      }
      return usesAIConnectionSettings(for: job)
        ? "The selected AI model is unavailable"
        : "A model required by this capability is unavailable"
    }
  }

  func guidance(for job: JobRecord) -> String {
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
      return "Inspect the backend named in the error and its capability preflight. Optional tools are not installed automatically."
    case .pythonEnvironment:
      return "Check the selected Python and scientific-data environment. Rechecking only diagnoses readiness; it does not install packages."
    case .timedOut:
      return "Inspect the logs and input size. Increase the capability timeout only if this work is expected to take longer."
    case .network:
      if offersLocalAIRecheck(for: job) {
        return "Check the current Ollama endpoint in Local AI Setup before sending another request."
      }
      return usesAIConnectionSettings(for: job)
        ? "Identify the provider from the original error or your notes before testing a current connection. The provider used by this historical job was not saved separately."
        : "Inspect any endpoint named in the job error and the capability's connection requirements before starting a new run."
    case .modelUnavailable:
      if offersLocalAIRecheck(for: job) {
        return "Choose an installed Ollama model or continue with the deterministic local workflow. Downloading a model needs your action."
      }
      return usesAIConnectionSettings(for: job)
        ? "Review any model named in the error and test the intended current provider. This job does not retain a separate provider selection."
        : "Inspect any model named in the job error and the capability setup before starting a new run."
    }
  }

  func actionLabel(for job: JobRecord) -> String {
    switch self {
    case .missingInput: return "Prepare New Run"
    case .outputConflict: return "Prepare New Output"
    case .permissionDenied: return "Review Paths"
    case .diskSpace: return "Review Output Root"
    case .optionalBackend:
      return isAstronomyBackend(for: job) ? "Review Backend Setup" : "Review Capability Setup"
    case .pythonEnvironment: return "Review Python Setup"
    case .timedOut: return "Review Timeout"
    case .network:
      return usesAIConnectionSettings(for: job) ? "Review AI Connection" : "Review Capability Setup"
    case .modelUnavailable:
      if offersLocalAIRecheck(for: job) { return "Review Local Model" }
      return usesAIConnectionSettings(for: job) ? "Review AI Model" : "Review Capability Setup"
    }
  }

  func opensCapability(for job: JobRecord) -> Bool {
    self == .missingInput || self == .outputConflict
      || (self == .optionalBackend && !isAstronomyBackend(for: job))
      || ((self == .network || self == .modelUnavailable) && !usesAIConnectionSettings(for: job))
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
      return isAstronomyBackend(for: job) ? .optionalBackends : nil
    case .pythonEnvironment:
      return .environment
    case .timedOut:
      return .behavior
    case .network, .modelUnavailable:
      guard usesAIConnectionSettings(for: job) else { return nil }
      return offersLocalAIRecheck(for: job) ? .localAI : .connections
    }
  }

  private func isAstronomyBackend(for job: JobRecord) -> Bool {
    job.capabilityID == "stilts_workbench" || job.capabilityID == "apt_workbench"
  }

  private func usesAIConnectionSettings(for job: JobRecord) -> Bool {
    if offersLocalAIRecheck(for: job) { return true }
    let messages = [job.message, job.stderr] + job.structuredErrors.map(\.message)
    let evidence = messages.compactMap { $0 }.joined(separator: "\n")
    return ["cloud provider", "openai", "grok", "gemini"].contains {
      evidence.localizedCaseInsensitiveContains($0)
    }
  }
}

extension JobRecord {
  var recoveryIssue: JobRecoveryIssue? {
    JobRecoveryIssue.detect(in: self)
  }
}

import Foundation

struct OllamaModelProfile: Identifiable, CaseIterable, Hashable, Sendable {
  let id: String
  let title: String
  let model: String
  let diskEstimate: String
  let memoryGuidance: String
  let bestFor: String
  let isRecommended: Bool

  var pickerTitle: String {
    isRecommended ? "\(title) (Recommended)" : title
  }

  var detailText: String {
    "\(model) · \(diskEstimate). \(memoryGuidance) Best for: \(bestFor)"
  }

  static let compact = OllamaModelProfile(
    id: "compact",
    title: "Compact",
    model: "qwen3:1.7b",
    diskEstimate: "about 1.4 GB",
    memoryGuidance: "Fastest and lightest on this Mac.",
    bestFor: "short chat, quick routing, and low battery/RAM pressure",
    isRecommended: false
  )

  static let balanced = OllamaModelProfile(
    id: "balanced",
    title: "Balanced",
    model: "qwen3:4b-instruct",
    diskEstimate: "about 2.5 GB",
    memoryGuidance: "Comfortable on 16 GB RAM while improving Spanish, planning, and code-like reasoning.",
    bestFor: "the default Scientific Workbench experience",
    isRecommended: true
  )

  static let stronger = OllamaModelProfile(
    id: "stronger",
    title: "Stronger",
    model: "qwen3:8b",
    diskEstimate: "about 5 GB",
    memoryGuidance: "Better reasoning, but slower and heavier; close other heavy apps first.",
    bestFor: "harder planning and longer scientific explanations",
    isRecommended: false
  )

  static let allCases: [OllamaModelProfile] = [.compact, .balanced, .stronger]

  static var recommended: OllamaModelProfile { .balanced }

  static func matching(model rawModel: String) -> OllamaModelProfile? {
    let model = rawModel.trimmingCharacters(in: .whitespacesAndNewlines)
    return allCases.first { $0.model == model }
  }
}

struct OllamaSetupStatus: Codable, Hashable, Sendable {
  var cliPath: String?
  var serverReachable = false
  var installedModels: [String] = []
  var targetModel: String
  var message: String
  var checkedAt: Date?

  static func unknown(model: String) -> OllamaSetupStatus {
    OllamaSetupStatus(
      targetModel: model,
      message: "Local AI setup has not been checked yet.",
      checkedAt: nil
    )
  }

  var modelInstalled: Bool {
    installedModels.contains(targetModel)
  }

  func presentationState(
    isDownloading: Bool = false,
    isCancellationRequested: Bool = false
  ) -> OllamaPresentationState {
    if isDownloading {
      return isCancellationRequested ? .cancellingDownload : .downloadingModel
    }
    guard checkedAt != nil else { return .unchecked }
    if !serverReachable {
      return cliPath == nil ? .install : .startServer
    }
    if modelInstalled { return .ready }
    return cliPath == nil ? .downloadRequiresCLI : .downloadModel
  }

  var badgeTitle: String {
    presentationState().badgeTitle
  }

  var detailLines: [String] {
    guard checkedAt != nil else { return ["Local AI setup has not been checked."] }
    return [
      "CLI: \(cliPath ?? "not found")",
      "Server: \(serverReachable ? "running" : "not reachable")",
      "Model: \(modelInstalled ? "\(targetModel) installed" : "\(targetModel) not installed")"
    ]
  }
}

enum OllamaPresentationState: Equatable, Sendable {
  case unchecked
  case install
  case startServer
  case downloadRequiresCLI
  case downloadModel
  case downloadingModel
  case cancellingDownload
  case ready

  var badgeTitle: String {
    switch self {
    case .unchecked: return "check"
    case .install, .downloadRequiresCLI: return "install"
    case .startServer: return "open"
    case .downloadModel: return "pull"
    case .downloadingModel, .cancellingDownload: return "running"
    case .ready: return "ok"
    }
  }

  func title(model: String) -> String {
    switch self {
    case .unchecked: return "Ollama not checked"
    case .install: return "Ollama CLI and server unavailable"
    case .startServer: return "Ollama server unavailable"
    case .downloadRequiresCLI: return "Model missing; Ollama CLI unavailable"
    case .downloadModel: return "Ollama model missing"
    case .downloadingModel: return "Downloading \(model)"
    case .cancellingDownload: return "Stopping model download"
    case .ready: return "Ollama model found at last check"
    }
  }

  func guidance(model: String) -> String {
    switch self {
    case .unchecked:
      return "Check local AI setup. Deterministic planning and Core workflows remain available without Ollama."
    case .install:
      return "Install Ollama, then check again. Deterministic planning and Core workflows remain available."
    case .startServer:
      return "Open Ollama to start its local server, then check again. Core workflows remain available."
    case .downloadRequiresCLI:
      return "The local server is reachable, but \(model) is missing and the Ollama CLI is needed for in-app downloads. Install the CLI or use deterministic planning."
    case .downloadModel:
      return "Download \(model) for local AI chat and planning, or continue with deterministic planning and Core workflows."
    case .downloadingModel:
      return "Downloading \(model). A progress percentage is unavailable; you can cancel the download. Core workflows remain available."
    case .cancellingDownload:
      return "Stopping the model download. Wait for cancellation to finish before retrying."
    case .ready:
      return "The model was available at the last check. Test Local AI to verify the current connection before using AI chat."
    }
  }
}

struct OllamaCommandResult: Hashable, Sendable {
  var exitCode: Int32
  var stdout: String
  var stderr: String

  var succeeded: Bool {
    exitCode == 0
  }

  var userMessage: String {
    let text = [stdout, stderr]
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
      .joined(separator: "\n")
    return text.isEmpty ? "Command exited with \(exitCode)." : text
  }
}

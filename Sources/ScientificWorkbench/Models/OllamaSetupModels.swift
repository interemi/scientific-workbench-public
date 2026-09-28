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

  var badgeTitle: String {
    if cliPath == nil { return "install" }
    if !serverReachable { return "open" }
    if !modelInstalled { return "pull" }
    return "ok"
  }

  var detailLines: [String] {
    [
      "CLI: \(cliPath ?? "not found")",
      "Server: \(serverReachable ? "running" : "not reachable")",
      "Model: \(modelInstalled ? "\(targetModel) installed" : "\(targetModel) not installed")"
    ]
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

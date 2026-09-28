import Foundation

struct LaunchAutomationOptions: Equatable, Sendable {
  var inputPaths: [String] = []
  var prompt: String?
  var mode: AgentRunMode?
  var autoRun = false
  var outputRootPath: String?
  var codexSandboxMode: String?
  var aiProvider: AIProvider?
  var aiModel: String?
  var aiBaseURL: String?
  var forceLocalPlanner = false
  var enableRestrictedSteps = false
  var transcriptPath: String?
  var isolatedSession = false
  var exitAfterRun = false

  var shouldRun: Bool {
    prompt?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false || !inputPaths.isEmpty
  }

  static func parse(_ arguments: [String]) -> LaunchAutomationOptions {
    var options = LaunchAutomationOptions()
    var index = 1

    func value(after flag: String) -> String? {
      guard index + 1 < arguments.count else { return nil }
      index += 1
      return arguments[index]
    }

    while index < arguments.count {
      let argument = arguments[index]
      switch argument {
      case "--agent-input":
        if let path = value(after: argument) {
          options.inputPaths.append((path as NSString).expandingTildeInPath)
        }
      case "--agent-prompt":
        options.prompt = value(after: argument)
      case "--agent-mode":
        if let raw = value(after: argument), let mode = AgentRunMode(rawValue: raw) {
          options.mode = mode
        }
      case "--agent-auto-run":
        options.autoRun = true
      case "--agent-output-root":
        if let path = value(after: argument) {
          options.outputRootPath = (path as NSString).expandingTildeInPath
        }
      case "--agent-codex-sandbox":
        options.codexSandboxMode = value(after: argument)
      case "--agent-ai-provider":
        if let raw = value(after: argument), let provider = AIProvider(rawValue: raw) {
          options.aiProvider = provider
        }
      case "--agent-openai-model":
        options.aiProvider = .openAI
        options.aiModel = value(after: argument)
      case "--agent-ai-model":
        options.aiModel = value(after: argument)
      case "--agent-ai-base-url":
        options.aiBaseURL = value(after: argument)
      case "--agent-local-planner":
        options.forceLocalPlanner = true
      case "--agent-enable-restricted-steps":
        options.enableRestrictedSteps = true
      case "--agent-ollama-model":
        options.aiProvider = .ollama
        options.aiModel = value(after: argument)
      case "--agent-ollama-base-url":
        options.aiProvider = .ollama
        options.aiBaseURL = value(after: argument)
      case "--agent-transcript-json":
        if let path = value(after: argument) {
          options.transcriptPath = (path as NSString).expandingTildeInPath
        }
      case "--agent-isolated-session":
        options.isolatedSession = true
      case "--agent-exit-after-run":
        options.exitAfterRun = true
      default:
        break
      }
      index += 1
    }

    return options
  }
}

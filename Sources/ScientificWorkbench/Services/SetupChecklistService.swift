import Foundation

struct SetupChecklistContext {
  var environmentStatus: EnvironmentStatus
  var outputRootPath: String
  var userCapabilityCount: Int
  var ollamaModel: String
  var ollamaSetupStatus: OllamaSetupStatus
  var ollamaConnectionStatus: AIConnectionStatus
  var cloudProviderReadiness: [AIProvider: AIConnectionStatus]
  var configuredCloudProviders: Set<AIProvider>
  var codexExecutablePath: String
}

struct SetupChecklistService {
  func items(context: SetupChecklistContext) -> [SetupChecklistItem] {
    let environmentReady = context.environmentStatus.status == "ok"
    let outputRootExists = FileManager.default.fileExists(atPath: context.outputRootPath)
    let localAIReady = context.ollamaConnectionStatus.state == .connected ||
      (context.ollamaSetupStatus.serverReachable && context.ollamaSetupStatus.modelInstalled)
    let cloudReady = AIProvider.allCases
      .filter(\.requiresAPIKey)
      .contains { provider in
        context.configuredCloudProviders.contains(provider) &&
          context.cloudProviderReadiness[provider]?.state == .connected
      }
    let codexReady = CodexBridge(executablePath: context.codexExecutablePath).isAvailable

    return [
      SetupChecklistItem(
        id: "environment",
        title: "Scientific environment",
        detail: environmentReady
          ? "Python and the datanalysis wrapper are ready."
          : "Refresh the environment or check the Python path in Settings.",
        state: environmentReady ? .ready : .action,
        systemImage: "checkmark.seal",
        isRequired: true
      ),
      SetupChecklistItem(
        id: "capabilities",
        title: "Capabilities loaded",
        detail: context.userCapabilityCount == 0
          ? "Reload the registry so the app can see the installed skill tools."
          : "\(context.userCapabilityCount) user-facing tools are available.",
        state: context.userCapabilityCount == 0 ? .action : .ready,
        systemImage: "square.grid.2x2",
        isRequired: true
      ),
      SetupChecklistItem(
        id: "output_root",
        title: "Output folder",
        detail: outputRootExists
          ? outputRootDetail(for: context.outputRootPath)
          : "Choose or create an output folder before running workflows.",
        state: outputRootExists ? .ready : .action,
        systemImage: "folder",
        isRequired: true
      ),
      SetupChecklistItem(
        id: "local_ai",
        title: "Local AI",
        detail: localAIReady
          ? "\(context.ollamaModel) is available for no-key local planning/chat."
          : "Optional for AI chat/planning. Core workflows work without Ollama; to enable it, open Ollama, download \(context.ollamaModel), then run Test Local AI.",
        state: localAIReady ? .ready : .optional,
        systemImage: "desktopcomputer",
        isRequired: false
      ),
      SetupChecklistItem(
        id: "optional_cloud",
        title: "Optional cloud AI",
        detail: cloudReady
          ? "At least one cloud provider has been tested successfully."
          : "OpenAI, Grok, and Gemini stay optional; leave them empty to avoid paid API usage.",
        state: cloudReady ? .ready : .optional,
        systemImage: "network",
        isRequired: false
      ),
      SetupChecklistItem(
        id: "codex_bridge",
        title: "Codex bridge",
        detail: codexReady
          ? "Codex is available for coding-agent workflows."
          : "Optional: set the Codex executable if you want local coding-agent delegation.",
        state: codexReady ? .ready : .optional,
        systemImage: "terminal",
        isRequired: false
      )
    ]
  }

  func isReady(items: [SetupChecklistItem]) -> Bool {
    items
      .filter(\.isRequired)
      .allSatisfy { $0.state == .ready }
  }

  func recoveryState(items: [SetupChecklistItem]) -> SetupRecoveryState? {
    let blockers = items
      .filter { $0.isRequired && $0.state != .ready }
    guard !blockers.isEmpty else { return nil }

    let actions = blockers
      .flatMap(setupRecoveryActions)
      .reduce(into: [String]()) { uniqueActions, action in
        if !uniqueActions.contains(action) {
          uniqueActions.append(action)
        }
      }

    let names = blockers.map(\.title).joined(separator: ", ")
    return SetupRecoveryState(
      title: blockers.count == 1 ? "One setup item needs attention" : "\(blockers.count) setup items need attention",
      detail: "Fix before expecting reliable agent runs: \(names).",
      blockingItemIDs: blockers.map(\.id),
      recommendedActions: actions
    )
  }

  private func setupRecoveryActions(for item: SetupChecklistItem) -> [String] {
    switch item.id {
    case "environment":
      return [
        "Open Settings and verify Mother skill root and Python executable.",
        "Run Refresh Environment; if it still fails, inspect Environment Details.",
        "Export a Support Bundle if the Python/datanalysis error is unclear."
      ]
    case "capabilities":
      return [
        "Run Reload Registry so the app can see the installed skill tools.",
        "Verify Mother skill root points to the scientific-data-analysis skill folder.",
        "Export a Support Bundle if the registry stays empty."
      ]
    case "output_root":
      return [
        "Choose or create an output folder in Settings.",
        "Normal runs can use a readable folder name; legacy IRAF/fxcor runs are isolated into a no-space workspace when needed.",
        "Confirm the output folder is writable before running workflows."
      ]
    default:
      return [item.detail]
    }
  }

  private func outputRootDetail(for outputRootPath: String) -> String {
    let folderName = URL(fileURLWithPath: outputRootPath).lastPathComponent
    if LegacyWorkspacePolicy.shared.isLegacyCompatible(path: outputRootPath) {
      return "Runs will write under \(folderName)."
    }
    return "Normal runs write under \(folderName); legacy IRAF/fxcor uses a no-space workspace."
  }
}

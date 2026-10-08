import SwiftUI

struct AgentControlBar: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .firstTextBaseline) {
        VStack(alignment: .leading, spacing: 3) {
          Text("Scientific Workbench Chat")
            .font(.title2)
            .fontWeight(.semibold)
          Text(store.agentStatusMessage)
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(2)
        }
        Spacer()
        ProviderBadge(
          provider: store.aiProvider,
          status: store.connectionStatus(for: store.aiProvider),
          hasConfiguredKey: store.selectedAIIsConfigured,
          hasCodex: CodexBridge(executablePath: store.codexExecutablePath).isAvailable,
          ollamaState: ollamaState,
          ollamaModel: store.model(for: .ollama)
        )
      }

      HStack(spacing: 12) {
        Picker("Provider", selection: $store.aiProvider) {
          ForEach(AIProvider.allCases) { provider in
            Text(provider.title).tag(provider)
          }
        }
        .pickerStyle(.segmented)
        .frame(maxWidth: 360)
        .accessibilityIdentifier("agent.provider")

        StatusBadge(status: selectedProviderBadgeTitle)
          .accessibilityLabel("Selected provider connection status")
          .accessibilityValue(selectedProviderBadgeTitle)
          .help(store.aiProvider.requiresAPIKey
            ? store.connectionStatus(for: store.aiProvider).message
            : (store.isPullingOllamaModel || store.connectionStatus(for: .ollama).state == .unknown
              ? ollamaState.guidance(model: store.model(for: .ollama))
              : store.connectionStatus(for: .ollama).message))

        Button("Test") {
          Task { await store.testAIConnection() }
        }
        .disabled(store.connectionStatus(for: store.aiProvider).state == .testing)
        .accessibilityLabel("Test selected AI connection")
        .accessibilityHint("Tests the selected provider with the current model and credentials.")
        .accessibilityIdentifier("agent.test-provider")
        .help("Test the selected AI connection.")

        Button {
          store.chooseAgentPlanFile()
        } label: {
          Label("Import Plan", systemImage: "square.and.arrow.down.on.square")
        }
        .accessibilityIdentifier("agent.import-plan")
        .help("Import an exported Scientific Workbench plan for review and rerun.")

        Spacer()

        Button {
          store.selectedSection = .settings
        } label: {
          Label("Settings", systemImage: "gearshape")
        }
        .accessibilityIdentifier("agent.open-settings")
      }

      HStack(spacing: 12) {
        Picker("Mode", selection: $store.agentMode) {
          ForEach(AgentRunMode.allCases) { mode in
            Text(mode.title).tag(mode)
          }
        }
        .pickerStyle(.segmented)
        .frame(maxWidth: 360)
        .accessibilityIdentifier("agent.mode")

        Toggle("Auto-run", isOn: $store.agentAutoRun)
          .toggleStyle(.switch)
          .fixedSize()
          .accessibilityIdentifier("agent.auto-run")
          .help("Run the workflow immediately after planning. Leave off when you want to review the plan first.")

        if store.canCancelActiveRun {
          Button(role: .cancel) {
            store.cancelActiveRun()
          } label: {
            Label("Cancel", systemImage: "xmark.circle")
          }
          .disabled(store.isCancellationRequested)
          .accessibilityIdentifier("agent.cancel")
          .accessibilityHint("Requests cancellation of the active workflow or capability process tree.")
          .help("Cancel the active workflow or capability run.")
        }

        if store.lastWorkflowSummaryPath != nil {
          Button {
            store.openWorkflowSummary()
          } label: {
            Label("Open Summary", systemImage: "doc.text.magnifyingglass")
          }
          .accessibilityIdentifier("agent.open-summary")
          .help("Open the latest workflow summary.")
        }

        Spacer()
      }

      if store.agentAutoRun {
        Label(
          "Auto-run starts a new plan before manual scope review. Turn it off to inspect the steps and use Dry Run first.",
          systemImage: "exclamationmark.triangle"
        )
        .font(.caption)
        .foregroundStyle(.orange)
      }

      if store.aiProvider == .ollama, ollamaNeedsAttention {
        HStack(alignment: .top, spacing: 10) {
          Text(ollamaGuidance)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
          Button("Open Local AI Setup") { store.selectedSection = .settings }
            .font(.caption)
            .fixedSize()
        }
        .accessibilityIdentifier("agent.ollama-guidance")
      }
    }
    .padding(.horizontal, 36)
    .padding(.vertical, 16)
  }

  private var ollamaState: OllamaPresentationState {
    store.ollamaSetupStatus.presentationState(
      isDownloading: store.isPullingOllamaModel,
      isCancellationRequested: store.isCancellationRequested
    )
  }

  private var selectedProviderBadgeTitle: String {
    if store.aiProvider.requiresAPIKey {
      return store.connectionStatus(for: store.aiProvider).state.badgeTitle
    }
    if store.isPullingOllamaModel { return ollamaState.badgeTitle }
    let state = store.connectionStatus(for: .ollama).state
    return state == .unknown ? ollamaState.badgeTitle : state.badgeTitle
  }

  private var ollamaNeedsAttention: Bool {
    if store.isPullingOllamaModel { return true }
    let connection = store.connectionStatus(for: .ollama).state
    return connection != .connected && (ollamaState != .ready || connection != .unknown)
  }

  private var ollamaGuidance: String {
    let connection = store.connectionStatus(for: .ollama)
    if !store.isPullingOllamaModel, connection.state != .unknown, connection.state != .connected {
      return "\(connection.message) Check Local AI in Settings. Deterministic planning and Core workflows remain available."
    }
    return ollamaState.guidance(model: store.model(for: .ollama))
  }
}

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
          hasCodex: CodexBridge(executablePath: store.codexExecutablePath).isAvailable
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

        StatusBadge(status: store.connectionStatus(for: store.aiProvider).state.badgeTitle)
          .accessibilityLabel("Selected provider connection status")
          .accessibilityValue(store.connectionStatus(for: store.aiProvider).state.badgeTitle)
          .help(store.connectionStatus(for: store.aiProvider).message)

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
    }
    .padding(.horizontal, 36)
    .padding(.vertical, 16)
  }
}

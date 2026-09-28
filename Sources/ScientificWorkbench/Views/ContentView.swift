import SwiftUI

struct ContentView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var showInspector = true

  var body: some View {
    GeometryReader { proxy in
      let inspectorIsVisible = showInspector && proxy.size.width >= 1260

      HStack(spacing: 0) {
        SidebarView(store: store)
          .frame(width: 260)

        Divider()

        VStack(spacing: 0) {
          WorkbenchTitleBar(
            title: (store.selectedSection ?? .agent).title,
            showInspector: $showInspector,
            inspectorIsAvailable: proxy.size.width >= 1260,
            refresh: {
              Task { await store.refreshEnvironment() }
            }
          )

          Divider()

          detail
            .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)

        if inspectorIsVisible {
          Divider()
          InspectorView(store: store)
            .frame(width: 280)
        }
      }
      .frame(width: proxy.size.width, height: proxy.size.height)
    }
  }

  @ViewBuilder
  private var detail: some View {
    switch store.selectedSection ?? .agent {
    case .home:
      HomeView(store: store)
    case .agent:
      AgentView(store: store)
    case .capabilities:
      CapabilityCatalogView(
        store: store,
        entries: store.userCapabilities,
        title: "Capabilities",
        subtitle: "\(store.userCapabilities.count) user-facing capabilities loaded from the installed skill.",
        isMaintenance: false
      )
    case .jobs:
      JobsView(store: store)
    case .results:
      ResultsView(store: store)
    case .maintenance:
      CapabilityCatalogView(
        store: store,
        entries: store.maintainerCapabilities,
        title: "Maintenance",
        subtitle: "\(store.maintainerCapabilities.count) maintainer-only gates kept separate from daily work.",
        isMaintenance: true
      )
    case .settings:
      SettingsView(store: store)
    }
  }
}

private struct WorkbenchTitleBar: View {
  let title: String
  @Binding var showInspector: Bool
  let inspectorIsAvailable: Bool
  let refresh: () -> Void

  var body: some View {
    HStack(spacing: 12) {
      Text(title)
        .font(.headline)
        .fontWeight(.semibold)
        .lineLimit(1)

      Spacer()

      Button {
        refresh()
      } label: {
        Label("Refresh", systemImage: "arrow.clockwise")
      }
      .labelStyle(.iconOnly)
      .accessibilityLabel("Refresh environment")
      .accessibilityHint("Reloads the skill registry and environment readiness information.")
      .accessibilityIdentifier("toolbar.refresh-environment")
      .help("Refresh environment status")

      Button {
        showInspector.toggle()
      } label: {
        Label("Inspector", systemImage: "sidebar.trailing")
      }
      .labelStyle(.iconOnly)
      .disabled(!inspectorIsAvailable)
      .accessibilityLabel(showInspector ? "Hide inspector" : "Show inspector")
      .accessibilityHint(inspectorIsAvailable ? "Toggles the environment and selection inspector." : "Widen the window to make the inspector available.")
      .accessibilityIdentifier("toolbar.toggle-inspector")
      .help(inspectorIsAvailable ? "Toggle inspector" : "Widen the window to show the inspector")
    }
    .padding(.leading, 22)
    .padding(.trailing, 14)
    .frame(height: 52)
    .background(.bar)
  }
}

struct InspectorView: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 18) {
        VStack(alignment: .leading, spacing: 8) {
          Text("Environment")
            .font(.headline)
          StatusBadge(status: store.environmentStatus.status)
          Text(store.environmentStatus.datanalysisPython ?? "No datanalysis Python resolved yet.")
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(2)
            .truncationMode(.middle)
            .textSelection(.enabled)
        }

        Divider()

        VStack(alignment: .leading, spacing: 8) {
          Text("Surface")
            .font(.headline)
          MetricLine(label: "User capabilities", value: "\(store.userCapabilities.count)")
          MetricLine(label: "Maintenance gates", value: "\(store.maintainerCapabilities.count)")
          MetricLine(label: "Jobs", value: "\(store.jobs.count)")
          MetricLine(label: "Inputs", value: "\(store.inputPaths.count)")
        }

        if store.selectedSection == .agent {
          Divider()
          VStack(alignment: .leading, spacing: 8) {
            Text("Agent")
              .font(.headline)
            MetricLine(label: "Mode", value: store.agentMode.title)
            MetricLine(label: "AI", value: store.selectedAIIsConfigured ? store.aiProvider.title : "Local")
            MetricLine(label: "Auto-run", value: store.agentAutoRun ? "On" : "Off")
            MetricLine(label: "Codex sandbox", value: store.codexSandboxMode)
            Text(store.agentStatusMessage)
              .font(.caption)
              .foregroundStyle(.secondary)
          }
        } else if let selected = store.selectedCapability {
          Divider()
          VStack(alignment: .leading, spacing: 8) {
            Text("Selected Capability")
              .font(.headline)
            Text(selected.label)
              .font(.subheadline)
              .fontWeight(.semibold)
            Text(selected.shortDescription)
              .font(.caption)
              .foregroundStyle(.secondary)
          }
        }

        Spacer(minLength: 0)
      }
      .padding(.top, 22)
      .padding(.leading, 22)
      .padding(.trailing, 22)
      .padding(.bottom, 24)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.bar)
  }
}

struct MetricLine: View {
  let label: String
  let value: String

  var body: some View {
    HStack(spacing: 16) {
      Text(label)
        .foregroundStyle(.secondary)
        .lineLimit(1)
      Spacer()
      Text(value)
        .fontWeight(.medium)
        .monospacedDigit()
        .frame(minWidth: 30, alignment: .trailing)
    }
    .font(.caption)
  }
}

struct StatusBadge: View {
  let status: String

  var body: some View {
    Text(status.uppercased())
      .font(.caption)
      .fontWeight(.semibold)
      .padding(.horizontal, 8)
      .padding(.vertical, 4)
      .background(color.opacity(0.14), in: Capsule())
      .foregroundStyle(color)
  }

  private var color: Color {
    switch status.lowercased() {
    case "ok", "pass", "succeeded", "connected": return .green
    case "blocked", "blocked_controlado", "fail", "failed", "invalid key": return .red
    case "running", "testing", "resume": return .blue
    case "warning", "missing key", "quota/rate", "model unavailable", "network", "timeout", "cancelled", "install", "open", "pull", "action": return .orange
    case "optional": return .secondary
    default: return .secondary
    }
  }
}

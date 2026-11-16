import SwiftUI

struct ContentView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var showInspector = true

  var body: some View {
    GeometryReader { proxy in
      let inspectorIsVisible = showInspector && proxy.size.width >= 1260

      HStack(spacing: 0) {
        SidebarView(store: store)
          .equatable()
          .frame(width: 260)

        Divider()

        VStack(spacing: 0) {
          WorkbenchTitleBar(
            store: store,
            showInspector: $showInspector,
            inspectorIsAvailable: proxy.size.width >= 1260
          )
          .equatable()

          Divider()

          if let stage = WorkflowJourneyStage.forSection(store.selectedSection) {
            WorkflowJourneyBar(store: store, currentStage: stage)
              .equatable()
            Divider()
          }

          if let notice = store.workflowNavigationNotice {
            HStack {
              Text(notice)
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
              Spacer()
              if store.previousWorkflowDraft != nil {
                Button("Restore Previous Draft") { store.restorePreviousWorkflowDraft() }
                  .disabled(!store.canChangeWorkflowContext)
                  .accessibilityIdentifier("workflow.restore-previous-draft")
              }
              Button("Dismiss", systemImage: "xmark") { store.workflowNavigationNotice = nil }
                .labelStyle(.iconOnly)
                .accessibilityLabel("Dismiss workflow notice")
            }
            .padding(12)
            .background(.regularMaterial)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("workflow.context-notice")
            Divider()
          }

          detail
            .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)

        if inspectorIsVisible {
          Divider()
          InspectorView(store: store)
            .equatable()
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
        title: "Capabilities",
        subtitle: "\(store.capabilitySearchIndex.all.entries.count) user-facing capabilities loaded from the installed skill.",
        isMaintenance: false
      )
      .equatable()
    case .jobs:
      JobsView(store: store)
    case .results:
      ResultsView(store: store)
    case .maintenance:
      CapabilityCatalogView(
        store: store,
        title: "Maintenance",
        subtitle: "\(store.maintenanceSearchIndex.all.entries.count) maintainer-only gates kept separate from daily work.",
        isMaintenance: true
      )
      .equatable()
    case .settings:
      SettingsView(store: store)
    }
  }
}

private struct WorkbenchTitleBar: View, Equatable {
  private let store: WorkbenchStore
  @Binding private var showInspector: Bool
  private let title: String
  private let inspectorIsShown: Bool
  private let inspectorIsAvailable: Bool
  private let canStartWorkflow: Bool

  init(store: WorkbenchStore, showInspector: Binding<Bool>, inspectorIsAvailable: Bool) {
    self.store = store
    _showInspector = showInspector
    title = (store.selectedSection ?? .agent).title
    inspectorIsShown = showInspector.wrappedValue
    self.inspectorIsAvailable = inspectorIsAvailable
    canStartWorkflow = store.canChangeWorkflowContext
  }

  nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.store === rhs.store
      && lhs.title == rhs.title
      && lhs.inspectorIsShown == rhs.inspectorIsShown
      && lhs.inspectorIsAvailable == rhs.inspectorIsAvailable
      && lhs.canStartWorkflow == rhs.canStartWorkflow
  }

  var body: some View {
    HStack(spacing: 12) {
      Text(title)
        .font(.headline)
        .fontWeight(.semibold)
        .lineLimit(1)

      Spacer()

      Button("New Workflow", systemImage: "plus") { store.beginNewWorkflow() }
        .disabled(!canStartWorkflow)
        .accessibilityHint("Archives the current draft before choosing a new task. Keeps originals, jobs, logs, and results.")
        .accessibilityIdentifier("toolbar.new-workflow")

      Button {
        Task { await store.refreshEnvironment() }
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
      .accessibilityLabel(inspectorIsShown ? "Hide inspector" : "Show inspector")
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

private struct InspectorView: View, Equatable {
  private enum Selection: Equatable {
    case agent(mode: String, ai: String, autoRun: String, sandbox: String, status: String)
    case capability(label: String, detail: String)
    case none
  }

  private let environmentStatus: String
  private let python: String?
  private let userCapabilityCount: Int
  private let maintainerCapabilityCount: Int
  private let jobCount: String
  private let inputCount: Int
  private let selection: Selection

  init(store: WorkbenchStore) {
    environmentStatus = store.environmentSummaryStatus
    python = store.environmentStatus.datanalysisPython
    userCapabilityCount = store.userCapabilities.count
    maintainerCapabilityCount = store.maintainerCapabilities.count
    jobCount = store.isRestoringJobHistory ? "Loading…" : String(store.jobs.count)
    inputCount = store.inputPaths.count
    if store.selectedSection == .agent {
      selection = .agent(
        mode: store.agentMode.title,
        ai: store.selectedAIIsConfigured ? store.aiProvider.title : "Local",
        autoRun: store.agentAutoRun ? "On" : "Off",
        sandbox: store.codexSandboxMode,
        status: store.agentStatusMessage
      )
    } else if let selected = store.selectedSection == .maintenance
      ? store.selectedMaintenanceCapability : store.selectedCapability {
      selection = .capability(label: selected.label, detail: selected.shortDescription)
    } else {
      selection = .none
    }
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 18) {
        VStack(alignment: .leading, spacing: 8) {
          Text("Environment")
            .font(.headline)
          StatusBadge(status: environmentStatus)
          Text(python ?? "No datanalysis Python resolved yet.")
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
          MetricLine(label: "User capabilities", value: "\(userCapabilityCount)")
          MetricLine(label: "Maintenance gates", value: "\(maintainerCapabilityCount)")
          MetricLine(label: "Jobs", value: jobCount)
          MetricLine(label: "Inputs", value: "\(inputCount)")
        }

        switch selection {
        case let .agent(mode, ai, autoRun, sandbox, status):
          Divider()
          VStack(alignment: .leading, spacing: 8) {
            Text("Agent")
              .font(.headline)
            MetricLine(label: "Mode", value: mode)
            MetricLine(label: "AI", value: ai)
            MetricLine(label: "Auto-run", value: autoRun)
            MetricLine(label: "Codex sandbox", value: sandbox)
            Text(status)
              .font(.caption)
              .foregroundStyle(.secondary)
          }
        case let .capability(label, detail):
          Divider()
          VStack(alignment: .leading, spacing: 8) {
            Text("Selected Capability")
              .font(.headline)
            Text(label)
              .font(.subheadline)
              .fontWeight(.semibold)
            Text(detail)
              .font(.caption)
              .foregroundStyle(.secondary)
          }
        case .none:
          EmptyView()
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
      .foregroundStyle(Color.primary)
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

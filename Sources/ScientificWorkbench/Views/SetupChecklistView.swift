import SwiftUI

struct SetupChecklistCard: View {
  @ObservedObject var store: WorkbenchStore
  var compact = false
  var showActions = true

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .firstTextBaseline) {
        Label("Setup Checklist", systemImage: "checklist")
          .font(compact ? .headline : .title3)
          .fontWeight(.semibold)
        Spacer()
        StatusBadge(status: store.setupChecklistIsReady ? "ok" : "action")
      }

      Text(store.setupChecklistIsReady ? "Ready for local workflows." : "Finish the required items before expecting reliable agent runs.")
        .font(.caption)
        .foregroundStyle(.secondary)

      VStack(alignment: .leading, spacing: 8) {
        ForEach(store.setupChecklistItems) { item in
          SetupChecklistRow(item: item)
        }
      }

      if let recovery = store.setupRecoveryState {
        SetupRecoveryPanel(store: store, recovery: recovery)
      }

      if showActions {
        HStack(spacing: 10) {
          Button {
            store.selectedSection = .settings
          } label: {
            Label("Open Settings", systemImage: "gearshape")
          }

          Button {
            Task {
              await store.refreshEnvironment()
              await store.refreshOllamaSetup()
            }
          } label: {
            Label("Refresh", systemImage: "arrow.clockwise")
          }

          Button {
            store.aiProvider = .ollama
            Task { await store.testAIConnection(.ollama) }
          } label: {
            Label("Test Local AI", systemImage: "desktopcomputer")
          }
          .disabled(store.connectionStatus(for: .ollama).state == .testing)

          Spacer(minLength: 0)
        }
      }
    }
    .padding(14)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}

private struct SetupRecoveryPanel: View {
  @ObservedObject var store: WorkbenchStore
  let recovery: SetupRecoveryState

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(alignment: .firstTextBaseline) {
        Label("Setup Recovery", systemImage: "cross.case")
          .font(.caption)
          .fontWeight(.semibold)
        Spacer()
        StatusBadge(status: recovery.badgeTitle)
      }

      Text(recovery.detail)
        .font(.caption)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)

      VStack(alignment: .leading, spacing: 6) {
        ForEach(Array(recovery.recommendedActions.prefix(5).enumerated()), id: \.offset) { index, action in
          HStack(alignment: .top, spacing: 8) {
            Text("\(index + 1).")
              .font(.caption)
              .foregroundStyle(.secondary)
              .frame(width: 18, alignment: .trailing)
            Text(action)
              .font(.caption)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
      }

      HStack(spacing: 10) {
        Button {
          store.selectedSection = .settings
        } label: {
          Label("Open Settings", systemImage: "gearshape")
        }

        Button {
          Task {
            await store.refreshEnvironment()
            await store.refreshOllamaSetup()
          }
        } label: {
          Label("Recheck Setup", systemImage: "arrow.clockwise")
        }

        Button {
          store.exportSupportBundle()
        } label: {
          Label("Support Bundle", systemImage: "shippingbox")
        }

        Spacer(minLength: 0)
      }
    }
    .padding(10)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}

private struct SetupChecklistRow: View {
  let item: SetupChecklistItem

  var body: some View {
    HStack(alignment: .top, spacing: 10) {
      Image(systemName: item.systemImage)
        .foregroundStyle(iconColor)
        .frame(width: 18)
        .padding(.top, 2)

      VStack(alignment: .leading, spacing: 2) {
        HStack(spacing: 8) {
          Text(item.title)
            .font(.caption)
            .fontWeight(.semibold)
          if !item.isRequired {
            Text("Optional")
              .font(.caption2)
              .foregroundStyle(.secondary)
          }
        }
        Text(item.detail)
          .font(.caption)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 0)
      StatusBadge(status: item.state.badgeTitle)
    }
  }

  private var iconColor: Color {
    switch item.state {
    case .ready: return .green
    case .action: return .orange
    case .optional: return .secondary
    }
  }
}

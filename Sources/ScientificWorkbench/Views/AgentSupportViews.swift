import SwiftUI

struct AgentBoundaryStrip: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      BoundaryItem(
        title: "AI",
        value: aiValue,
        systemImage: store.aiProvider.requiresAPIKey ? "network" : "desktopcomputer"
      )
      BoundaryItem(
        title: "Inputs",
        value: store.inputPaths.isEmpty ? "None attached" : "\(store.inputPaths.count) read-only item\(store.inputPaths.count == 1 ? "" : "s")",
        systemImage: "paperclip"
      )
      BoundaryItem(
        title: "Outputs",
        value: URL(fileURLWithPath: store.outputRootPath).lastPathComponent,
        systemImage: "folder"
      )
    }
  }

  private var aiValue: String {
    if !store.aiProvider.requiresAPIKey {
      return "\(store.aiProvider.title) local chat/planning"
    }
    if store.selectedAIIsConfigured {
      return "\(store.aiProvider.title); \(store.cloudAttachmentContextMode.boundaryTitle)"
    }
    if CodexBridge(executablePath: store.codexExecutablePath).isAvailable {
      return "Local planner + Codex"
    }
    return "Local planner"
  }
}

private struct BoundaryItem: View {
  let title: String
  let value: String
  let systemImage: String

  var body: some View {
    HStack(spacing: 10) {
      Image(systemName: systemImage)
        .foregroundStyle(.secondary)
        .frame(width: 18)
      VStack(alignment: .leading, spacing: 2) {
        Text(title)
          .font(.caption)
          .foregroundStyle(.secondary)
        Text(value)
          .font(.caption)
          .fontWeight(.medium)
          .lineLimit(1)
          .truncationMode(.middle)
      }
      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(10)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}

struct ChatBubble: View {
  let message: AgentChatMessage

  var body: some View {
    HStack(alignment: .top) {
      if message.role == .user {
        Spacer(minLength: 80)
      }

      VStack(alignment: .leading, spacing: 6) {
        Text(message.role == .user ? "You" : "Scientific Workbench")
          .font(.caption)
          .foregroundStyle(.secondary)
        Text(message.text)
          .textSelection(.enabled)
      }
      .padding(12)
      .background(background, in: RoundedRectangle(cornerRadius: 8))
      .frame(maxWidth: 720, alignment: message.role == .user ? .trailing : .leading)

      if message.role != .user {
        Spacer(minLength: 80)
      }
    }
  }

  private var background: some ShapeStyle {
    message.role == .user ? AnyShapeStyle(Color.accentColor.opacity(0.18)) : AnyShapeStyle(.regularMaterial)
  }
}

struct AttachmentChip: View {
  let path: String
  let remove: () -> Void

  var body: some View {
    HStack(spacing: 6) {
      Image(systemName: "paperclip")
      Text(URL(fileURLWithPath: path).lastPathComponent)
        .lineLimit(1)
        .help(path)
      Button {
        remove()
      } label: {
        Image(systemName: "xmark.circle.fill")
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Remove attachment \(URL(fileURLWithPath: path).lastPathComponent)")
      .accessibilityHint("Removes this attachment from the current message without deleting it from disk.")
    }
    .font(.caption)
    .padding(.horizontal, 8)
    .padding(.vertical, 5)
    .background(.thinMaterial, in: Capsule())
  }
}

struct ProviderBadge: View {
  let provider: AIProvider
  let status: AIConnectionStatus
  let hasConfiguredKey: Bool
  let hasCodex: Bool

  var body: some View {
    Label(title, systemImage: icon)
      .font(.caption)
      .padding(.horizontal, 8)
      .padding(.vertical, 4)
      .background(.thinMaterial, in: Capsule())
      .foregroundStyle(.secondary)
      .help(status.message)
  }

  private var title: String {
    if !provider.requiresAPIKey, status.state == .connected { return "\(provider.title) local" }
    if !provider.requiresAPIKey { return "\(provider.title) local" }
    if status.state == .connected, hasCodex { return "\(provider.title) + Codex" }
    if status.state == .connected { return "\(provider.title) connected" }
    if hasConfiguredKey { return "\(provider.title) configured" }
    if hasCodex { return "Codex available" }
    return "Local planner"
  }

  private var icon: String {
    if !provider.requiresAPIKey { return "desktopcomputer" }
    if status.state == .connected || hasConfiguredKey { return "network" }
    if hasCodex { return "terminal" }
    return "desktopcomputer"
  }
}

struct CloudConsentSheet: View {
  let request: CloudConsentRequest
  let cancel: () -> Void
  let approve: (CloudConsentApprovalScope) -> Void
  @State private var approvalScope: CloudConsentApprovalScope = .requestOnly

  var body: some View {
    VStack(alignment: .leading, spacing: 18) {
      HStack(alignment: .top, spacing: 14) {
        Image(systemName: "network.badge.shield.half.filled")
          .font(.system(size: 30))
          .foregroundStyle(.tint)
          .frame(width: 38)

        VStack(alignment: .leading, spacing: 5) {
          Text("Send data to \(request.provider.title)?")
            .font(.title2)
            .fontWeight(.semibold)
          Text("Scientific Workbench is ready to use a cloud provider. Review the exact categories that will leave this Mac before the request starts.")
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
      }

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 7) {
        GridRow {
          Text("Provider")
            .foregroundStyle(.secondary)
          Text(request.provider.title)
            .fontWeight(.medium)
        }
        GridRow {
          Text("Model")
            .foregroundStyle(.secondary)
          Text(request.model)
            .fontWeight(.medium)
            .textSelection(.enabled)
        }
        GridRow {
          Text("Purpose")
            .foregroundStyle(.secondary)
          Text(request.purpose.title)
            .fontWeight(.medium)
        }
        GridRow {
          Text("Privacy mode")
            .foregroundStyle(.secondary)
          Text(request.attachmentContextMode.title)
            .fontWeight(.medium)
        }
      }

      GroupBox("Data included in this request") {
        VStack(alignment: .leading, spacing: 12) {
          ForEach(request.categories) { category in
            HStack(alignment: .top, spacing: 10) {
              Image(systemName: category.systemImage)
                .foregroundStyle(.secondary)
                .frame(width: 18)
              VStack(alignment: .leading, spacing: 2) {
                Text(category.title)
                  .fontWeight(.medium)
                Text(category.detail)
                  .font(.caption)
                  .foregroundStyle(.secondary)
                  .fixedSize(horizontal: false, vertical: true)
              }
            }
          }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
      }

      GroupBox("Approval duration") {
        VStack(alignment: .leading, spacing: 8) {
          Picker("Approval duration", selection: $approvalScope) {
            ForEach(CloudConsentApprovalScope.allCases) { scope in
              Text(scope.title).tag(scope)
            }
          }
          .labelsHidden()
          .pickerStyle(.radioGroup)

          Text(approvalScope.detail)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
      }

      Text("The provider also receives the selected model and normal generation settings. Your API credential is used only in the provider's authentication field. If any configured API credential appears in the message or recent history, Scientific Workbench replaces it with [REDACTED] before review and sending. The default approval is this request only; session approval is never persisted after Scientific Workbench closes.")
        .font(.caption)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)

      HStack {
        Button("Cancel", role: .cancel, action: cancel)
          .keyboardShortcut(.cancelAction)
        Spacer()
        Button(approvalScope == .requestOnly ? "Allow Once & Send" : "Remember & Send") {
          approve(approvalScope)
        }
          .buttonStyle(.borderedProminent)
          .keyboardShortcut(.defaultAction)
      }
    }
    .padding(24)
    .frame(minWidth: 540, idealWidth: 580, maxWidth: 620)
    .interactiveDismissDisabled()
  }
}

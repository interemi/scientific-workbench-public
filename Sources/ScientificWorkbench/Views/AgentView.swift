import SwiftUI
import UniformTypeIdentifiers

struct AgentView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var isDropTargeted = false

  var body: some View {
    VStack(spacing: 0) {
      AgentControlBar(store: store)
      Divider()
      chatTranscript
      Divider()
      composer
    }
    .navigationTitle("Chat")
    .sheet(item: $store.pendingCloudConsentRequest) { request in
      CloudConsentSheet(
        request: request,
        cancel: store.cancelPendingCloudRequest,
        approve: { scope in
          Task { await store.confirmPendingCloudRequest(approvalScope: scope) }
        }
      )
      .id(request.id)
    }
  }

  private var chatTranscript: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 14) {
        AgentBoundaryStrip(store: store)

        if !store.setupChecklistIsReady {
          SetupChecklistCard(store: store, compact: true)
        }

        ForEach(store.agentChatMessages) { message in
          ChatBubble(message: message)
        }

        if let plan = store.agentPlan {
          EditablePlanCard(store: store, plan: plan)
        }

        if let recovery = store.workflowRecoveryState {
          WorkflowRecoveryCard(store: store, recovery: recovery)
        }
      }
      .padding(.vertical, 22)
      .padding(.horizontal, 36)
      .frame(maxWidth: 1040, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
    }
  }

  private var composer: some View {
    VStack(alignment: .leading, spacing: 10) {
      attachmentBar

      TextField("Message Scientific Workbench...", text: $store.agentPrompt, axis: .vertical)
        .lineLimit(2...7)
        .textFieldStyle(.roundedBorder)
        .onSubmit {
          Task { await store.submitAgentChatPrompt() }
        }

      HStack(spacing: 10) {
        Button {
          store.chooseInputFiles()
        } label: {
          Label("Files", systemImage: "doc.badge.plus")
        }

        Button {
          store.chooseInputFolders()
        } label: {
          Label("Folder", systemImage: "folder.badge.plus")
        }

        if !store.inputPaths.isEmpty {
          Button("Clear") {
            store.clearInputs()
          }
        }

        Spacer()

        Button {
          Task { await store.submitAgentChatPrompt() }
        } label: {
          Label(store.isPlanningAgentWorkflow ? "Thinking..." : "Send", systemImage: "paperplane.fill")
        }
        .buttonStyle(.borderedProminent)
        .disabled(store.isPlanningAgentWorkflow || store.agentPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
      }
    }
    .padding(.horizontal, 36)
    .padding(.vertical, 14)
    .background(.bar)
    .overlay {
      if isDropTargeted {
        RoundedRectangle(cornerRadius: 8)
          .strokeBorder(Color.accentColor, style: StrokeStyle(lineWidth: 2, dash: [6, 4]))
          .padding(8)
      }
    }
    .onDrop(of: [UTType.fileURL.identifier], isTargeted: $isDropTargeted) { providers in
      handleDrop(providers)
    }
  }

  @ViewBuilder
  private var attachmentBar: some View {
    if store.inputPaths.isEmpty {
      HStack(spacing: 8) {
        Image(systemName: "paperclip")
        Text("Attach files or folders with the buttons below, or drop them on the composer.")
      }
      .font(.caption)
      .foregroundStyle(.secondary)
    } else {
      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 8) {
          ForEach(store.inputPaths, id: \.self) { path in
            AttachmentChip(path: path) {
              store.removeInputPath(path)
            }
          }
        }
        .padding(.horizontal, 2)
      }
    }
  }

  private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
    for provider in providers {
      provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
        let url: URL?
        if let data = item as? Data {
          url = URL(dataRepresentation: data, relativeTo: nil)
        } else {
          url = item as? URL
        }

        if let url {
          Task { @MainActor in
            store.addInputPath(url.path)
          }
        }
      }
    }
    return true
  }
}

import SwiftUI

struct OllamaSetupView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var pendingDownload: OllamaModelDownloadRequest?

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .firstTextBaseline) {
        Label("Ollama local AI", systemImage: "desktopcomputer")
          .font(.headline)
        Spacer()
        StatusBadge(status: presentationState.badgeTitle)
      }

      Text("Starting profile: \(OllamaModelProfile.recommended.model). Local AI is optional; deterministic planning and Core workflows need no model. Profile sizes are approximate model files, not minimum free disk or RAM requirements.")
        .font(.caption)
        .foregroundStyle(.secondary)

      Text("Installed system memory: \(ByteCountFormatter.string(fromByteCount: Int64(ProcessInfo.processInfo.physicalMemory), countStyle: .memory)). This is total memory, not currently available RAM. Fit and speed have not been measured for your workload.")
        .font(.caption)
        .foregroundStyle(.secondary)

      Picker("Model profile", selection: ollamaModelSelection) {
        ForEach(OllamaModelProfile.allCases) { profile in
          Text(profile.pickerTitle).tag(profile.model)
        }
        if selectedProfile == nil {
          Text("Custom").tag(store.model(for: .ollama))
        }
      }
      .pickerStyle(.segmented)
      .disabled(store.isPullingOllamaModel)

      Text(selectedProfile?.detailText ?? "Custom model: \(store.model(for: .ollama)). Make sure it is available in Ollama before testing or planning.")
        .font(.caption)
        .foregroundStyle(.secondary)

      TextField("Custom Ollama model", text: ollamaCustomModelBinding)
        .textContentType(.none)
        .disabled(store.isPullingOllamaModel)

      TextField("Local endpoint", text: ollamaBaseURLBinding)
        .textContentType(.URL)
        .disabled(store.isPullingOllamaModel)

      if !store.ollamaSetupStatus.installedModels.isEmpty {
        Text("Models at the last endpoint check: \(store.ollamaSetupStatus.installedModels.joined(separator: ", ")). Copy a listed name into Custom Ollama model to select it, then check and test again.")
          .font(.caption)
          .foregroundStyle(.secondary)
          .textSelection(.enabled)
      }

      if store.isPullingOllamaModel {
        ProgressView("Downloading model; percentage unavailable")
          .controlSize(.small)
          .accessibilityIdentifier("ollama.download-progress")
      }

      Text(presentationState.guidance(model: store.model(for: .ollama)))
        .font(.caption)
        .foregroundStyle(.secondary)
        .textSelection(.enabled)

      if !store.isPullingOllamaModel {
        Text(store.ollamaSetupStatus.message)
          .font(.caption)
          .foregroundStyle(.secondary)
          .textSelection(.enabled)
      }

      if store.connectionStatus(for: .ollama).state != .unknown {
        HStack {
          Text("Last Local AI connection test")
            .font(.caption)
          StatusBadge(status: store.connectionStatus(for: .ollama).state.badgeTitle)
        }
        Text(store.connectionStatus(for: .ollama).message)
          .font(.caption)
          .foregroundStyle(.secondary)
          .textSelection(.enabled)
      }

      VStack(alignment: .leading, spacing: 4) {
        ForEach(store.ollamaSetupStatus.detailLines, id: \.self) { line in
          Text(line)
            .font(.system(.caption, design: .monospaced))
            .foregroundStyle(.secondary)
            .textSelection(.enabled)
        }
      }

      HStack {
        Button("Install Ollama") {
          store.openOllamaDownloadPage()
        }

        Button("Open Ollama") {
          store.openOllamaApp()
        }

        Button(store.isCheckingOllamaSetup ? "Checking..." : "Check") {
          Task { await store.refreshOllamaSetup() }
        }
        .disabled(store.isCheckingOllamaSetup)

        Button(store.isPullingOllamaModel ? "Downloading..." : "Download Selected Model") {
          pendingDownload = store.prepareOllamaModelDownload()
        }
        .disabled(!store.canChangeWorkflowContext || store.ollamaSetupStatus.cliPath == nil)
        .accessibilityIdentifier("ollama.review-download")

        if store.isPullingOllamaModel {
          Button("Cancel Download", role: .cancel) {
            store.cancelActiveRun()
          }
          .disabled(store.isCancellationRequested)
        }

        Button("Test Local AI") {
          store.aiProvider = .ollama
          Task { await store.testAIConnection(.ollama) }
        }
        .disabled(store.connectionStatus(for: .ollama).state == .testing)
      }

    }
    .padding(.vertical, 8)
    .onAppear {
      guard store.ollamaSetupStatus.checkedAt == nil else { return }
      Task { await store.refreshOllamaSetup() }
    }
    .sheet(item: $pendingDownload) { request in
      VStack(alignment: .leading, spacing: 16) {
        Text("Review model download").font(.title2)
        Text(request.reviewDetail)
          .fixedSize(horizontal: false, vertical: true)
          .textSelection(.enabled)
        HStack {
          Button("Cancel", role: .cancel) { pendingDownload = nil }
          Spacer()
          Button("Download Model") {
            pendingDownload = nil
            Task { await store.confirmOllamaModelDownload(request) }
          }
          .buttonStyle(.borderedProminent)
          .accessibilityIdentifier("ollama.confirm-download")
        }
      }
      .padding(24)
      .frame(width: 520)
    }
  }

  private var selectedProfile: OllamaModelProfile? {
    OllamaModelProfile.matching(model: store.model(for: .ollama))
  }

  private var presentationState: OllamaPresentationState {
    store.ollamaSetupStatus.presentationState(
      isDownloading: store.isPullingOllamaModel,
      isCancellationRequested: store.isCancellationRequested
    )
  }

  private var ollamaModelSelection: Binding<String> {
    Binding(get: {
      store.model(for: .ollama)
    }, set: { model in
      if let profile = OllamaModelProfile.matching(model: model) {
        store.applyOllamaModelProfile(profile)
      } else {
        store.setModel(model, for: .ollama)
        store.persistSettings()
      }
    })
  }

  private var ollamaCustomModelBinding: Binding<String> {
    Binding(get: {
      store.model(for: .ollama)
    }, set: { model in
      store.setModel(model, for: .ollama)
      store.persistSettings()
    })
  }

  private var ollamaBaseURLBinding: Binding<String> {
    Binding(get: {
      store.baseURL(for: .ollama) ?? ""
    }, set: { baseURL in
      store.setBaseURL(baseURL, for: .ollama)
      store.persistSettings()
    })
  }
}

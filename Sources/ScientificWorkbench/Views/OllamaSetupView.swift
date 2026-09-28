import SwiftUI

struct OllamaSetupView: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .firstTextBaseline) {
        Label("Ollama local AI", systemImage: "desktopcomputer")
          .font(.headline)
        Spacer()
        StatusBadge(status: store.ollamaSetupStatus.badgeTitle)
      }

      Text("Recommended for this Mac: \(OllamaModelProfile.recommended.model), a newer Qwen3 4B model around 2.5 GB that should stay comfortable on 16 GB RAM while giving better planning, Spanish, and code-like reasoning than the tiny fallback.")
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

      Text(selectedProfile?.detailText ?? "Custom model: \(store.model(for: .ollama)). Make sure it is available in Ollama before testing or planning.")
        .font(.caption)
        .foregroundStyle(.secondary)

      TextField("Custom Ollama model", text: ollamaCustomModelBinding)
        .textContentType(.none)

      TextField("Local endpoint", text: ollamaBaseURLBinding)
        .textContentType(.URL)

      Text(store.ollamaSetupStatus.message)
        .font(.caption)
        .foregroundStyle(.secondary)
        .textSelection(.enabled)

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
          Task { await store.pullSelectedOllamaModel() }
        }
        .disabled(store.canCancelActiveRun || store.ollamaSetupStatus.cliPath == nil)

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

      Text("After installation, open Ollama once, download the model here, then run Test Local AI.")
        .font(.caption)
        .foregroundStyle(.secondary)
    }
    .padding(.vertical, 8)
    .onAppear {
      guard store.ollamaSetupStatus.checkedAt == nil else { return }
      Task { await store.refreshOllamaSetup() }
    }
  }

  private var selectedProfile: OllamaModelProfile? {
    OllamaModelProfile.matching(model: store.model(for: .ollama))
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

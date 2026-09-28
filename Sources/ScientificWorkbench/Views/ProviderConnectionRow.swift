import SwiftUI

struct ProviderConnectionRow: View {
  @ObservedObject var store: WorkbenchStore
  let provider: AIProvider

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        Text(provider.title)
          .font(.headline)
        Text(provider.connectionKind)
          .font(.caption)
          .foregroundStyle(.secondary)
        Spacer()
        StatusBadge(status: status.state.badgeTitle)
          .accessibilityLabel("\(provider.title) connection status")
          .accessibilityValue(status.state.badgeTitle)
      }

      if provider.requiresAPIKey {
        SecureField(credentialPlaceholder, text: credentialBinding)
          .textContentType(.password)
          .accessibilityIdentifier("provider.\(provider.rawValue).credential")
      } else {
        Label("No API key required. Uses a local Ollama server.", systemImage: "desktopcomputer")
          .font(.caption)
          .foregroundStyle(.secondary)
        TextField("Local endpoint", text: baseURLBinding)
          .textContentType(.URL)
          .accessibilityIdentifier("provider.ollama.endpoint")
      }

      TextField("Model", text: modelBinding)
        .textContentType(.none)
        .accessibilityLabel("\(provider.title) model")
        .accessibilityIdentifier("provider.\(provider.rawValue).model")

      HStack {
        Button(status.state == .testing ? "Testing..." : "Test Connection") {
          Task { await store.testAIConnection(provider) }
        }
        .disabled(status.state == .testing)
        .accessibilityIdentifier("provider.\(provider.rawValue).test")
        .accessibilityHint("Tests the current credentials, model, and endpoint. The result is valid only for this app session.")

        Text(status.message)
          .font(.caption)
          .foregroundStyle(.secondary)
          .lineLimit(3)
          .truncationMode(.middle)
      }
    }
    .padding(.vertical, 8)
  }

  private var status: AIConnectionStatus {
    store.connectionStatus(for: provider)
  }

  private var credentialPlaceholder: String {
    switch provider {
    case .ollama: return ""
    case .openAI: return "OpenAI API key"
    case .grok: return "Grok / xAI API key"
    case .gemini: return "Gemini API key"
    }
  }

  private var credentialBinding: Binding<String> {
    Binding(get: {
      store.apiKey(for: provider)
    }, set: { value in
      switch provider {
      case .ollama: break
      case .openAI, .grok, .gemini: store.setAPIKey(value, for: provider)
      }
    })
  }

  private var modelBinding: Binding<String> {
    Binding(get: {
      store.model(for: provider)
    }, set: { value in
      store.setModel(value, for: provider)
    })
  }

  private var baseURLBinding: Binding<String> {
    Binding(get: {
      store.baseURL(for: provider) ?? ""
    }, set: { value in
      store.setBaseURL(value, for: provider)
    })
  }
}

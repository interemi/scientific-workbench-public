import Foundation

struct AIConnectionRequest: Sendable {
  var provider: AIProvider
  var apiKey: String
  var model: String
  var baseURL: String?
  var secretsToRedact: [String]

  var trimmedAPIKey: String {
    apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  func hasSameConnectionTarget(as other: AIConnectionRequest) -> Bool {
    provider == other.provider
      && trimmedAPIKey == other.trimmedAPIKey
      && model == other.model
      && baseURL == other.baseURL
  }
}

struct AIConnectionService: Sendable {
  private let client: CloudAIClient

  init(client: CloudAIClient = CloudAIClient()) {
    self.client = client
  }

  func startingStatus(for request: AIConnectionRequest, now: Date = Date()) -> AIConnectionStatus {
    if request.provider.requiresAPIKey && request.trimmedAPIKey.isEmpty {
      return AIConnectionStatus(
        state: .missingKey,
        message: "Add \(request.provider.title) credentials first.",
        checkedAt: now
      )
    }

    return AIConnectionStatus(
      state: .testing,
      message: "Testing \(request.provider.title) with \(request.model)...",
      checkedAt: now
    )
  }

  func test(_ request: AIConnectionRequest, now: Date = Date()) async -> AIConnectionStatus {
    let startingStatus = startingStatus(for: request, now: now)
    guard startingStatus.state == .testing else { return startingStatus }

    do {
      let reply = try await client.testConnection(
        provider: request.provider,
        apiKey: request.trimmedAPIKey,
        model: request.model,
        baseURL: request.baseURL
      )
      return AIConnectionStatus(
        state: .connected,
        message: "Connected using \(request.model). \(redact(reply, request: request))",
        checkedAt: now
      )
    } catch {
      return AIConnectionStatus(
        state: (error as? CloudAIError)?.connectionState ?? .failed,
        message: failureMessage(error, request: request),
        checkedAt: now
      )
    }
  }

  func failureMessage(_ error: Error, request: AIConnectionRequest) -> String {
    let details = redact(error.localizedDescription, request: request)
    let provider = request.provider

    if provider == .ollama {
      let endpoint = request.baseURL ?? AIProvider.ollama.defaultBaseURL ?? "http://localhost:11434"
      if case .modelUnavailable? = error as? CloudAIError {
        return "Ollama is running, but \(request.model) is not available. Run `ollama pull \(request.model)`, then test again. Details: \(details)"
      }
      return "Ollama is not ready at \(endpoint). Install/open Ollama, run `ollama pull \(request.model)`, then test again. Details: \(details)"
    }

    guard let cloudError = error as? CloudAIError else { return details }
    switch cloudError {
    case .invalidKey:
      return "\(provider.title) rejected the credentials. Re-enter the API key in Settings, then test again. Details: \(details)"
    case .quotaOrRateLimit:
      return "\(provider.title) quota or rate limit was reached. Use Ollama/local planning, wait, or check the provider billing/quota page. Details: \(details)"
    case .modelUnavailable:
      return "\(provider.title) could not use the selected model. Choose a different model in Settings, then test again. Details: \(details)"
    case .networkUnavailable, .timedOut, .serverUnavailable:
      return "\(provider.title) could not be reached reliably. Check the network/provider status, then retry. Details: \(details)"
    case .requestFailed, .invalidResponse, .invalidJSON, .emptyPlan, .unexpectedTestResponse,
         .invalidBaseURL, .unsafeOllamaEndpoint:
      return details
    }
  }

  private func redact(_ text: String, request: AIConnectionRequest) -> String {
    SecretsRedactor.redact(
      text,
      secrets: request.secretsToRedact + [request.trimmedAPIKey]
    )
  }
}

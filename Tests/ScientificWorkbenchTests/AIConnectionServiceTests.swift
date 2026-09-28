import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func aiConnectionServiceRejectsMissingCloudCredentialWithoutNetworkUse() async {
    let recorder = RequestRecorder(responseBody: #"{"output_text":"unexpected"}"#)
    let service = AIConnectionService(client: CloudAIClient(dataLoader: recorder.load))
    let request = AIConnectionRequest(
      provider: .openAI,
      apiKey: "  ",
      model: "gpt-test",
      baseURL: nil,
      secretsToRedact: []
    )

    let startingStatus = service.startingStatus(for: request)
    let finalStatus = await service.test(request)

    #expect(startingStatus.state == .missingKey)
    #expect(finalStatus.state == .missingKey)
    #expect(finalStatus.message == "Add OpenAI credentials first.")
    #expect(await recorder.requests.isEmpty)
  }

  @Test
  func aiConnectionServiceRedactsConfiguredSecretsFromSuccessfulReply() async {
    let recorder = RequestRecorder(
      responseBody: #"{"output_text":"Scientific Workbench AI connection OK sk-live-key and secondary-secret"}"#
    )
    let service = AIConnectionService(client: CloudAIClient(dataLoader: recorder.load))
    let request = AIConnectionRequest(
      provider: .openAI,
      apiKey: "sk-live-key",
      model: "gpt-test",
      baseURL: nil,
      secretsToRedact: ["secondary-secret"]
    )

    let status = await service.test(request)

    #expect(status.state == .connected)
    #expect(status.message.contains("Connected using gpt-test."))
    #expect(status.message.contains("[REDACTED]"))
    #expect(!status.message.contains("sk-live-key"))
    #expect(!status.message.contains("secondary-secret"))
    #expect(await recorder.requests.count == 1)
  }

  @Test
  func aiConnectionServiceMapsAndRedactsProviderFailure() async {
    let recorder = RequestRecorder(
      responseBody: #"{"error":{"message":"invalid api key sk-rejected-key"}}"#,
      statusCode: 401
    )
    let service = AIConnectionService(client: CloudAIClient(dataLoader: recorder.load))
    let request = AIConnectionRequest(
      provider: .openAI,
      apiKey: "sk-rejected-key",
      model: "gpt-test",
      baseURL: nil,
      secretsToRedact: []
    )

    let status = await service.test(request)

    #expect(status.state == .invalidKey)
    #expect(status.message.contains("OpenAI rejected the credentials"))
    #expect(status.message.contains("[REDACTED]"))
    #expect(!status.message.contains("sk-rejected-key"))
  }

  @Test
  @MainActor
  func providerConfigurationChangesInvalidateSessionConnectionEvidence() {
    let suiteName = "Scientific-Workbench-Connection-Tests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    let connected = AIConnectionStatus(
      state: .connected,
      message: "Connected.",
      checkedAt: Date()
    )

    store.aiConnectionStatuses[.openAI] = connected
    store.setAPIKey("replacement-key", for: .openAI)
    #expect(store.connectionStatus(for: .openAI).state == .unknown)

    store.aiConnectionStatuses[.openAI] = connected
    store.setModel("replacement-model", for: .openAI)
    #expect(store.connectionStatus(for: .openAI).state == .unknown)

    store.aiConnectionStatuses[.ollama] = connected
    store.setBaseURL("http://127.0.0.1:11435", for: .ollama)
    #expect(store.connectionStatus(for: .ollama).state == .unknown)
  }

  @Test
  func connectionRequestTargetComparisonIgnoresRedactionContextButDetectsRoutingChanges() {
    let request = AIConnectionRequest(
      provider: .openAI,
      apiKey: "  sk-test-key  ",
      model: "gpt-test",
      baseURL: nil,
      secretsToRedact: ["first-secret"]
    )
    let sameTarget = AIConnectionRequest(
      provider: .openAI,
      apiKey: "sk-test-key",
      model: "gpt-test",
      baseURL: nil,
      secretsToRedact: ["different-secret"]
    )
    var changedModel = sameTarget
    changedModel.model = "gpt-other"
    var changedKey = sameTarget
    changedKey.apiKey = "sk-other-key"

    #expect(request.hasSameConnectionTarget(as: sameTarget))
    #expect(!request.hasSameConnectionTarget(as: changedModel))
    #expect(!request.hasSameConnectionTarget(as: changedKey))
  }

  @Test
  @MainActor
  func staleConnectionResultCannotApproveConfigurationChangedDuringProbe() async throws {
    let suiteName = "Scientific-Workbench-Connection-Tests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let client = CloudAIClient(dataLoader: { request in
      try await Task.sleep(for: .milliseconds(100))
      let response = HTTPURLResponse(
        url: request.url!,
        statusCode: 200,
        httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
      )!
      return (
        Data(#"{"output_text":"Scientific Workbench AI connection OK"}"#.utf8),
        response
      )
    })
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: client
    )
    store.setAPIKey("sk-test-key", for: .openAI)
    store.setModel("gpt-before", for: .openAI)

    let probe = Task { await store.testAIConnection(.openAI) }
    for _ in 0..<1_000 {
      if store.connectionStatus(for: .openAI).state == .testing { break }
      await Task.yield()
    }
    #expect(store.connectionStatus(for: .openAI).state == .testing)

    store.setModel("gpt-after", for: .openAI)
    await probe.value

    #expect(store.model(for: .openAI) == "gpt-after")
    #expect(store.connectionStatus(for: .openAI).state == .unknown)
  }

  @Test
  @MainActor
  func providerConnectionEvidenceDoesNotPersistAcrossAppSessions() {
    let suiteName = "Scientific-Workbench-Connection-Tests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let firstStore = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    firstStore.aiProvider = .gemini
    firstStore.setModel("gemini-test", for: .gemini)
    firstStore.persistSettings()
    firstStore.aiConnectionStatuses[.gemini] = AIConnectionStatus(
      state: .connected,
      message: "Connected in the first session.",
      checkedAt: Date()
    )

    let relaunchedStore = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )

    #expect(relaunchedStore.aiProvider == .gemini)
    #expect(relaunchedStore.model(for: .gemini) == "gemini-test")
    #expect(relaunchedStore.connectionStatus(for: .gemini) == .unknown)
  }

  @Test
  @MainActor
  func freshGeminiDefaultDoesNotChangePersistedModelSelections() {
    let suiteName = "Scientific-Workbench-Gemini-Default-Tests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let freshStore = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    #expect(freshStore.model(for: .gemini) == "gemini-3.5-flash-lite")

    defaults.set("gemini-2.5-pro", forKey: "geminiModel")
    let existingStore = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    #expect(existingStore.model(for: .gemini) == "gemini-2.5-pro")
    #expect(defaults.string(forKey: "geminiModel") == "gemini-2.5-pro")
  }
}

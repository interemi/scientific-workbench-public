import Foundation
@testable import ScientificWorkbench
import Testing

private func consentTestCapability() -> CapabilityEntry {
  CapabilityEntry(
    id: "profile_table",
    label: "profile_table.py",
    script: "scripts/profile_table.py",
    visibleBlock: "notebooks + cross-domain",
    kind: "golden_path",
    supportLevel: "stable",
    platform: "portable",
    requiresDatanalysis: false,
    preflightMode: "none",
    smokeTier: "core",
    shortDescription: "Profile a table."
  )
}

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func cloudChatDefaultsToOneRequestConsent() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(responseBody: #"{"output_text":"cloud-ok"}"#)
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    store.agentMode = .chat
    store.aiProvider = .openAI
    store.openAIAPIKey = "sk-test-openai"
    store.openAIModel = "gpt-test"
    store.agentPrompt = "Explain this result."
    let messageCountBeforeSubmission = store.agentChatMessages.count

    await store.submitAgentChatPrompt()

    let request = try #require(store.pendingCloudConsentRequest)
    #expect(request.provider == .openAI)
    #expect(request.model == "gpt-test")
    #expect(request.purpose == .chat)
    #expect(request.categories == [.currentMessage, .recentConversation])
    #expect(await recorder.requests.isEmpty)
    #expect(store.agentPrompt == "Explain this result.")
    #expect(store.agentChatMessages.count == messageCountBeforeSubmission)

    await store.confirmPendingCloudRequest()

    #expect(await recorder.requests.count == 1)
    #expect(store.pendingCloudConsentRequest == nil)
    #expect(store.agentPrompt.isEmpty)
    #expect(store.agentChatMessages.last?.text == "cloud-ok")

    store.agentPrompt = "A second request must ask again."
    await store.submitAgentChatPrompt()

    #expect(store.pendingCloudConsentRequest != nil)
    #expect(await recorder.requests.count == 1)
  }

  @Test
  @MainActor
  func cancellingCloudConsentKeepsDraftAndSendsNothing() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(responseBody: #"{"output_text":"unexpected"}"#)
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    store.agentMode = .chat
    store.aiProvider = .gemini
    store.geminiAPIKey = "gemini-test-key"
    store.agentPrompt = "Keep this private draft."

    await store.submitAgentChatPrompt()
    try #require(store.pendingCloudConsentRequest != nil)
    store.cancelPendingCloudRequest()

    #expect(await recorder.requests.isEmpty)
    #expect(store.pendingCloudConsentRequest == nil)
    #expect(store.agentPrompt == "Keep this private draft.")
    #expect(store.agentStatusMessage.contains("Nothing was sent"))
  }

  @Test
  @MainActor
  func explicitSessionConsentIsScopedToProviderModelPurposePrivacyModeAndCategories() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    store.agentMode = .chat
    store.aiProvider = .openAI
    store.openAIAPIKey = "sk-test-openai"
    store.openAIModel = "gpt-test"
    let originalPrivacyMode = store.cloudAttachmentContextMode
    store.agentPrompt = "First request."

    await store.submitAgentChatPrompt()
    await store.confirmPendingCloudRequest(approvalScope: .appSession)
    #expect(await recorder.requests.count == 1)

    store.agentPrompt = "Second request with the same scope."
    await store.submitAgentChatPrompt()
    #expect(store.pendingCloudConsentRequest == nil)
    #expect(await recorder.requests.count == 2)

    store.openAIModel = "gpt-other"
    store.agentPrompt = "Changed model."
    await store.submitAgentChatPrompt()
    #expect(store.pendingCloudConsentRequest?.model == "gpt-other")
    #expect(await recorder.requests.count == 2)
    store.cancelPendingCloudRequest()

    store.openAIModel = "gpt-test"
    store.cloudAttachmentContextMode = originalPrivacyMode == .none ? .filenamesOnly : .none
    store.agentPrompt = "Changed privacy mode."
    await store.submitAgentChatPrompt()
    #expect(store.pendingCloudConsentRequest?.attachmentContextMode != originalPrivacyMode)
    #expect(await recorder.requests.count == 2)
    store.cancelPendingCloudRequest()

    store.cloudAttachmentContextMode = originalPrivacyMode
    store.aiProvider = .gemini
    store.geminiAPIKey = "gemini-test-key"
    store.geminiModel = "gemini-test"
    store.agentPrompt = "Changed provider."
    await store.submitAgentChatPrompt()
    #expect(store.pendingCloudConsentRequest?.provider == .gemini)
    #expect(await recorder.requests.count == 2)
    store.cancelPendingCloudRequest()

    let input = FileManager.default.temporaryDirectory
      .appendingPathComponent("consent-expansion-\(UUID().uuidString).txt")
    try "safe fixture".write(to: input, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: input) }
    store.aiProvider = .openAI
    store.addInputPath(input.path)
    store.agentPrompt = "Changed data categories."
    await store.submitAgentChatPrompt()
    #expect(store.pendingCloudConsentRequest?.categories.contains(.attachmentFilenames) == true)
    #expect(await recorder.requests.count == 2)
    store.cancelPendingCloudRequest()

    store.inputPaths = []
    store.agentMode = .workflow
    store.capabilities = [consentTestCapability()]
    store.agentPrompt = "Plan a table workflow."
    await store.submitAgentChatPrompt()
    #expect(store.pendingCloudConsentRequest?.purpose == .workflowPlanning)
    #expect(await recorder.requests.count == 2)
  }

  @Test
  @MainActor
  func changedConsentFingerprintRequiresFreshReviewBeforeSending() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    store.agentMode = .chat
    store.aiProvider = .openAI
    store.openAIAPIKey = "sk-test-openai"
    store.openAIModel = "gpt-before"
    store.agentPrompt = "Original prompt."

    await store.submitAgentChatPrompt()
    let firstRequest = try #require(store.pendingCloudConsentRequest)

    store.openAIModel = "gpt-after"
    store.agentPrompt = "Updated prompt."
    await store.confirmPendingCloudRequest()

    let refreshedRequest = try #require(store.pendingCloudConsentRequest)
    #expect(refreshedRequest.id != firstRequest.id)
    #expect(refreshedRequest.model == "gpt-after")
    #expect(refreshedRequest.fingerprint.prompt == "Updated prompt.")
    #expect(await recorder.requests.isEmpty)
    #expect(store.agentPrompt == "Updated prompt.")
    #expect(store.agentStatusMessage.contains("Nothing was sent"))

    await store.confirmPendingCloudRequest()
    #expect(await recorder.requests.count == 1)
  }

  @Test
  @MainActor
  func consentFingerprintCanonicalizesInputsAndDetectsPreviewChanges() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Consent-\(UUID().uuidString)", isDirectory: true)
    let target = root.appendingPathComponent("target.txt")
    let symlink = root.appendingPathComponent("selected-link.txt")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "first preview".write(to: target, atomically: true, encoding: .utf8)
    try FileManager.default.createSymbolicLink(at: symlink, withDestinationURL: target)
    defer { try? FileManager.default.removeItem(at: root) }

    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    store.agentMode = .chat
    store.aiProvider = .openAI
    store.openAIAPIKey = "sk-test-openai"
    store.cloudAttachmentContextMode = .previews
    store.addInputPath(symlink.path)
    store.agentPrompt = "Inspect the selected input."

    await store.submitAgentChatPrompt()
    let firstRequest = try #require(store.pendingCloudConsentRequest)
    let firstInput = try #require(firstRequest.fingerprint.inputs.first)
    #expect(firstInput.canonicalPath == target.standardizedFileURL.resolvingSymlinksInPath().path)
    #expect(firstInput.presentedName == "selected-link.txt")
    #expect(firstInput.previewBytes == Data("first preview".utf8))

    try "second preview with different bytes".write(to: target, atomically: true, encoding: .utf8)
    await store.confirmPendingCloudRequest()

    let refreshedRequest = try #require(store.pendingCloudConsentRequest)
    #expect(refreshedRequest.id != firstRequest.id)
    #expect(refreshedRequest.fingerprint.inputs.first?.previewBytes == Data("second preview with different bytes".utf8))
    #expect(await recorder.requests.isEmpty)

    await store.confirmPendingCloudRequest()
    #expect(await recorder.requests.count == 1)
  }

  @Test
  @MainActor
  func configuredSecretsAreRedactedFromChatPromptHistoryFingerprintAndHTTPBody() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    let openAISecret = "sk-openai-accidental-secret"
    let grokSecret = "xai-accidental-secret"
    let geminiSecret = "gemini-accidental-secret"
    store.agentMode = .chat
    store.aiProvider = .openAI
    store.openAIAPIKey = openAISecret
    store.grokAPIKey = grokSecret
    store.geminiAPIKey = geminiSecret
    store.agentChatMessages.append(
      AgentChatMessage(role: .user, text: "Earlier I pasted \(grokSecret).")
    )
    let localDraft = "Compare \(openAISecret) and \(geminiSecret), but do not transmit either."
    store.agentPrompt = localDraft

    await store.submitAgentChatPrompt()

    let consent = try #require(store.pendingCloudConsentRequest)
    #expect(store.agentPrompt == localDraft)
    #expect(consent.fingerprint.prompt.contains("[REDACTED]"))
    #expect(!consent.fingerprint.prompt.contains(openAISecret))
    #expect(!consent.fingerprint.prompt.contains(geminiSecret))
    #expect(!consent.fingerprint.history.contains { $0.text.contains(grokSecret) })

    await store.confirmPendingCloudRequest()

    let request = try #require(await recorder.requests.first)
    let bodyData = try #require(request.httpBody)
    let bodyText = try #require(String(data: bodyData, encoding: .utf8))
    #expect(!bodyText.contains(openAISecret))
    #expect(!bodyText.contains(grokSecret))
    #expect(!bodyText.contains(geminiSecret))
    #expect(bodyText.contains("[REDACTED]"))
    #expect(store.agentChatMessages.contains { $0.role == .user && $0.text == localDraft })
  }

  @Test
  @MainActor
  func configuredSecretsAreRedactedFromCloudPlanningHTTPBody() async throws {
    let planJSON = #"{"title":"Safe plan","rationale":"Use the selected capability.","steps":[{"capability_id":"profile_table","summary":"Profile the table.","raw_arguments":"","uses_inputs":true,"uses_previous_output":false}]}"#
    let responseData = try JSONSerialization.data(withJSONObject: ["output_text": planJSON])
    let responseBody = try #require(String(data: responseData, encoding: .utf8))
    let recorder = RequestRecorder(responseBody: responseBody)
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    let secret = "sk-planning-accidental-secret"
    let localDraft = "Plan a table workflow without exposing \(secret)."
    store.agentMode = .workflow
    store.aiProvider = .openAI
    store.openAIAPIKey = secret
    store.openAIModel = "gpt-test"
    store.skillRootPath = "/tmp/Scientific-Workbench-Missing-Skill-\(UUID().uuidString)"
    store.capabilities = [consentTestCapability()]
    store.agentPrompt = localDraft

    await store.submitAgentChatPrompt()
    let consent = try #require(store.pendingCloudConsentRequest)
    #expect(consent.purpose == .workflowPlanning)
    #expect(consent.fingerprint.prompt.contains("[REDACTED]"))
    #expect(!consent.fingerprint.prompt.contains(secret))
    #expect(store.agentPrompt == localDraft)

    await store.confirmPendingCloudRequest()

    let request = try #require(await recorder.requests.first)
    let bodyData = try #require(request.httpBody)
    let bodyText = try #require(String(data: bodyData, encoding: .utf8))
    #expect(!bodyText.contains(secret))
    #expect(bodyText.contains("[REDACTED]"))
    #expect(store.agentChatMessages.contains { $0.role == .user && $0.text == localDraft })
    #expect(store.agentPlan?.title == "Safe plan")
  }

  @Test
  @MainActor
  func loopbackOllamaChatNeverRequestsCloudConsent() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(
      responseBody: #"{"message":{"role":"assistant","content":"local-ok"},"done":true}"#
    )
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    store.agentMode = .chat
    store.aiProvider = .ollama
    store.ollamaModel = "qwen-test"
    store.ollamaBaseURL = "http://127.0.0.1:11434"
    store.agentPrompt = "Answer locally."

    await store.submitAgentChatPrompt()

    #expect(store.pendingCloudConsentRequest == nil)
    #expect(await recorder.requests.count == 1)
    #expect(store.agentChatMessages.last?.text == "local-ok")
  }

  @Test
  @MainActor
  func remoteOllamaEndpointIsRejectedWithoutConsentOrNetworkRequest() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(
      responseBody: #"{"message":{"role":"assistant","content":"unexpected"},"done":true}"#
    )
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    store.agentMode = .chat
    store.aiProvider = .ollama
    store.ollamaModel = "qwen-test"
    store.ollamaBaseURL = "http://192.168.1.20:11434"
    store.agentPrompt = "Do not exfiltrate this preview."

    await store.submitAgentChatPrompt()

    #expect(store.pendingCloudConsentRequest == nil)
    #expect(await recorder.requests.isEmpty)
    #expect(store.agentChatMessages.last?.text.localizedCaseInsensitiveContains("loopback") == true)
  }
}

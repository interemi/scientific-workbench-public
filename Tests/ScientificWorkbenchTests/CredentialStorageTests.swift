import Foundation
@testable import ScientificWorkbench
import Testing

@MainActor
private final class InMemoryCloudCredentialStore: CloudCredentialStoring {
  var keys: [AIProvider: String]
  var failingProviders: Set<AIProvider> = []
  var saveCalls: [AIProvider] = []

  init(keys: [AIProvider: String] = [:]) {
    self.keys = keys
  }

  func readKey(for provider: AIProvider) -> String {
    keys[provider] ?? ""
  }

  func saveKey(_ key: String, for provider: AIProvider) -> CredentialWriteResult {
    saveCalls.append(provider)
    guard !failingProviders.contains(provider) else { return .failure(-1) }
    let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
      keys.removeValue(forKey: provider)
    } else {
      keys[provider] = trimmed
    }
    return .success
  }
}

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func deferredJobHistoryPreservesEvidenceWhenAnEarlyRunPersists() async throws {
    let syntheticKey = "synthetic-history-key"
    let root = try makeScenarioFixture(name: "deferred-job-history", files: [
      "Documents/saved-run/stdout.txt": "Diagnostic \(syntheticKey)",
      "Documents/saved-run/result.csv": "source_id,flux\n1,4.2\n",
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let output = root.appendingPathComponent("Documents")
    let savedRun = output.appendingPathComponent("saved-run")
    let history = output.appendingPathComponent(".scientificworkbench/jobs.json")
    var priorJob = JobRecord(capability: sampleCapability(), runDirectory: savedRun.path)
    priorJob.status = .succeeded
    try JobHistoryStore().persist(jobs: [priorJob], to: history)
    let historyBefore = try Data(contentsOf: history)
    let suiteName = "Scientific-Workbench-History-Restore-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set(AIProvider.openAI.rawValue, forKey: "aiProvider")
    defaults.set(output.path, forKey: "outputRootPath")
    defaults.set(root.appendingPathComponent("missing-skill").path, forKey: "skillRootPath")
    let store = WorkbenchStore(
      defaults: defaults,
      deferJobHistoryHydration: true,
      credentialStore: InMemoryCloudCredentialStore(keys: [.openAI: syntheticKey]),
      filesystemSafetyPolicy: FilesystemSafetyPolicy(homeDirectory: root)
    )

    #expect(store.isRestoringJobHistory)
    #expect(store.jobs.isEmpty)
    store.clearJobHistory()
    store.reloadJobHistory()
    #expect(try Data(contentsOf: history) == historyBefore)

    store.outputRootRiskApproved = true
    let submitted = try #require(await store.run(capability: sampleCapability(), rawArguments: ""))
    #expect(submitted.status == .blocked)
    #expect(!store.isRestoringJobHistory)
    #expect(store.selectedJobID == submitted.id)
    let restored = try #require(store.jobs.first { $0.id == priorJob.id })
    #expect(restored.stdout == "Diagnostic [REDACTED]")
    #expect(restored.artifacts.contains { $0.relativePath == "result.csv" })
    let saved = try #require(try JobHistoryStore().load(from: history))
    #expect(saved.map(\.id) == [submitted.id, priorJob.id])
    #expect(saved.last?.stdout == "Diagnostic [REDACTED]")
    #expect(try String(contentsOf: savedRun.appendingPathComponent("stdout.txt"), encoding: .utf8)
      == "Diagnostic \(syntheticKey)")
  }

  @Test
  @MainActor
  func realKeychainRoundTripUsesAnIsolatedService() {
    let service = "com.emilio.scientific-workbench.test.\(UUID().uuidString)"
    let credentials = KeychainCredentialStore(service: service)
    defer {
      #expect(credentials.saveKey("", for: .openAI) == .success)
      #expect(credentials.saveKey("", for: .gemini) == .success)
    }

    #expect(credentials.readKey(for: .openAI).isEmpty)
    #expect(credentials.saveKey("  synthetic-openai-key  ", for: .openAI) == .success)
    #expect(credentials.saveKey("synthetic-gemini-key", for: .gemini) == .success)

    let reopened = KeychainCredentialStore(service: service)
    #expect(reopened.readKey(for: .openAI) == "synthetic-openai-key")
    #expect(reopened.readKey(for: .gemini) == "synthetic-gemini-key")

    #expect(reopened.saveKey("updated-synthetic-key", for: .openAI) == .success)
    #expect(credentials.readKey(for: .openAI) == "updated-synthetic-key")
    #expect(credentials.readKey(for: .gemini) == "synthetic-gemini-key")

    #expect(reopened.saveKey("", for: .openAI) == .success)
    #expect(credentials.readKey(for: .openAI).isEmpty)
  }

  @Test
  @MainActor
  func savingOneEditedCloudKeyPreservesOtherProvidersAndSurvivesRelaunch() {
    let suiteName = "Scientific-Workbench-Credential-Save-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set(AIProvider.openAI.rawValue, forKey: "aiProvider")
    let credentials = InMemoryCloudCredentialStore(keys: [
      .openAI: "old-openai-key",
      .gemini: "untouched-gemini-key"
    ])
    let store = WorkbenchStore(
      defaults: defaults,
      loadPersistedState: false,
      credentialStore: credentials
    )
    #expect(store.apiKey(for: .openAI) == "old-openai-key")

    store.setAPIKey("  new-openai-key  ", for: .openAI)
    #expect(store.persistSettings(saveSecrets: true))
    #expect(credentials.saveCalls == [.openAI])
    #expect(credentials.keys[.openAI] == "new-openai-key")
    #expect(credentials.keys[.gemini] == "untouched-gemini-key")
    #expect(store.credentialSaveFailed == false)
    #expect(!(store.credentialSaveMessage ?? "").contains("new-openai-key"))

    let relaunched = WorkbenchStore(
      defaults: defaults,
      loadPersistedState: false,
      credentialStore: credentials
    )
    #expect(relaunched.apiKey(for: .openAI) == "new-openai-key")
    #expect(relaunched.connectionStatus(for: .openAI).state == .unknown)
  }

  @Test
  @MainActor
  func failedCloudKeySaveKeepsPriorStoredValueAndAllowsRetry() {
    let suiteName = "Scientific-Workbench-Credential-Failure-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set(AIProvider.openAI.rawValue, forKey: "aiProvider")
    let credentials = InMemoryCloudCredentialStore(keys: [.openAI: "previous-key"])
    credentials.failingProviders = [.openAI]
    let store = WorkbenchStore(
      defaults: defaults,
      loadPersistedState: false,
      credentialStore: credentials
    )

    store.setAPIKey("new-secret-key", for: .openAI)
    #expect(!store.persistSettings(saveSecrets: true))
    #expect(credentials.keys[.openAI] == "previous-key")
    #expect(store.apiKey(for: .openAI) == "new-secret-key")
    #expect(store.credentialSaveFailed)
    #expect((store.credentialSaveMessage ?? "").contains("OpenAI"))
    #expect(!(store.credentialSaveMessage ?? "").contains("new-secret-key"))
    #expect(!(store.credentialSaveMessage ?? "").contains("previous-key"))

    let beforeRetry = WorkbenchStore(
      defaults: defaults,
      loadPersistedState: false,
      credentialStore: credentials
    )
    #expect(beforeRetry.apiKey(for: .openAI) == "previous-key")

    credentials.failingProviders = []
    #expect(store.persistSettings(saveSecrets: true))
    #expect(credentials.saveCalls == [.openAI, .openAI])
    #expect(credentials.keys[.openAI] == "new-secret-key")
    #expect(!store.credentialSaveFailed)
    let afterRetry = WorkbenchStore(
      defaults: defaults,
      loadPersistedState: false,
      credentialStore: credentials
    )
    #expect(afterRetry.apiKey(for: .openAI) == "new-secret-key")
  }

  @Test
  @MainActor
  func clearingCloudKeyIsNotUndoneByConnectionTest() async {
    let suiteName = "Scientific-Workbench-Credential-Clear-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set(AIProvider.openAI.rawValue, forKey: "aiProvider")
    let credentials = InMemoryCloudCredentialStore(keys: [.openAI: "previous-key"])
    let recorder = RequestRecorder(responseBody: #"{"output_text":"unexpected"}"#)
    let store = WorkbenchStore(
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load),
      credentialStore: credentials
    )

    store.setAPIKey("", for: .openAI)
    await store.testAIConnection(.openAI)
    #expect(store.apiKey(for: .openAI).isEmpty)
    #expect(store.connectionStatus(for: .openAI).state == .missingKey)
    #expect(await recorder.requests.isEmpty)
    #expect(credentials.keys[.openAI] == "previous-key")
    #expect(credentials.saveCalls.isEmpty)

    #expect(store.persistSettings(saveSecrets: true))
    #expect(credentials.keys[.openAI] == nil)
  }
}

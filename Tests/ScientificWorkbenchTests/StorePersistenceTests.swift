import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func storeImportPreservesLocalRecipeButOmitsMaintainerAndDisablesRestrictedSteps() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Restricted-Plan-Import-\(UUID().uuidString)", isDirectory: true)
    let planURL = tempRoot.appendingPathComponent("plan.json")
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempRoot) }
    defaults.set(tempRoot.path, forKey: "outputRootPath")

    let payload = ExportedAgentPlanPayload(
      version: 1,
      generatedAt: Date(timeIntervalSince1970: 1_000),
      outputRootPath: tempRoot.path,
      inputPaths: [],
      aiProvider: .ollama,
      aiModel: "qwen3:4b-instruct",
      mode: .workflow,
      autoRun: true,
      plan: AgentPlan(
        title: "Untrusted imported plan",
        rationale: "Imported plans must be revalidated against the local registry.",
        steps: [
          AgentPlanStep(
            capabilityID: "profile_table",
            summary: "Profile a table.",
            rawArguments: "",
            usesInputs: true,
            usesPreviousOutput: false
          ),
          AgentPlanStep(
            capabilityID: "inspect_fits",
            summary: "Inspect FITS data.",
            rawArguments: "",
            usesInputs: true,
            usesPreviousOutput: false
          ),
          AgentPlanStep(
            capabilityID: "portable_smoke_test",
            summary: "Run a maintainer gate.",
            rawArguments: "",
            usesInputs: false,
            usesPreviousOutput: false
          ),
          AgentPlanStep(
            capabilityID: "legacy_spectroscopy_envcheck",
            summary: "Retain the CLI-only recipe step for review.",
            rawArguments: "--summary-json {summaryJson}",
            usesInputs: false,
            usesPreviousOutput: false
          ),
          AgentPlanStep(
            capabilityID: "legacy_external_reference_check",
            summary: "Retain the local recipe reference check for review.",
            rawArguments: "check --rv-summary {previousSummaryJson}",
            usesInputs: false,
            usesPreviousOutput: true
          ),
        ],
        source: .local
      )
    )
    try JSONEncoder.scientificWorkbench.encode(payload).write(to: planURL)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let legacyIDs = ["legacy_spectroscopy_envcheck", "legacy_external_reference_check"]
    let legacyCapabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
      .filter { legacyIDs.contains($0.id) }
    #expect(legacyCapabilities.count == 2)
    store.capabilities = [sampleCapability(), expertFITSCapability(), maintainerCapability()] + legacyCapabilities

    let imported = try #require(store.importAgentPlan(from: planURL.path))

    #expect(imported.steps.map(\.capabilityID) == ["profile_table", "inspect_fits"] + legacyIDs)
    #expect(imported.steps[0].isEnabled)
    #expect(!imported.steps[1].isEnabled)
    #expect(imported.steps[1].summary.contains("enable it explicitly"))
    #expect(imported.steps.dropFirst().allSatisfy { !$0.isEnabled })
    #expect(imported.steps[2].rawArguments == "--summary-json {summaryJson}")
    #expect(imported.steps[3].rawArguments == "check --rv-summary {previousSummaryJson}")
    #expect(store.agentAutoRun == false)
    #expect(store.agentStatusMessage.contains("Omitted 1 non-planner step"))
    #expect(store.agentStatusMessage.contains("Disabled 3 restricted steps"))
  }

  @Test
  @MainActor
  func registryReloadRevalidatesRestoredPlanAgainstInstalledPolicy() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Restored-Plan-Policy-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }
    defaults.set(outputRoot.path, forKey: "outputRootPath")

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.skillRootPath = DefaultPaths.motherSkillRoot
    store.agentPlan = AgentPlan(
      title: "Restored plan",
      rationale: "Persisted state is not trusted after registry reload.",
      steps: [
        AgentPlanStep(
          capabilityID: "inspect_fits",
          summary: "Inspect FITS data.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: "portable_smoke_test",
          summary: "Run a maintainer gate.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: "legacy_spectroscopy_envcheck",
          summary: "Preserve the restored local CLI-only step.",
          rawArguments: "--summary-json {summaryJson}",
          usesInputs: false,
          usesPreviousOutput: false
        ),
      ],
      source: .local
    )

    await store.reloadRegistry()

    let plan = try #require(store.agentPlan)
    #expect(plan.steps.map(\.capabilityID) == ["inspect_fits", "legacy_spectroscopy_envcheck"])
    #expect(plan.steps.allSatisfy { !$0.isEnabled })
    #expect(plan.steps[1].rawArguments == "--summary-json {summaryJson}")
    #expect(store.agentStatusMessage.contains("Revalidated restored plan"))
  }

  @Test
  @MainActor
  func storeNormalizesAndPersistsExternalProcessTimeout() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    defaults.set(33, forKey: "externalProcessTimeoutMinutes")

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    #expect(store.externalProcessTimeoutMinutes == 35)
    #expect(store.externalProcessTimeoutSeconds == 35 * 60)

    store.externalProcessTimeoutMinutes = 999
    store.persistSettings()

    #expect(store.externalProcessTimeoutMinutes == 120)
    #expect(defaults.integer(forKey: "externalProcessTimeoutMinutes") == 120)
  }

  @Test
  @MainActor
  func isolatedHeadlessStoreCanSkipPersistedAgentState() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-State-\(UUID().uuidString)", isDirectory: true)
    let stateURL = outputRoot
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("agent_state.json")
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    defaults.set(outputRoot.path, forKey: "outputRootPath")
    try FileManager.default.createDirectory(
      at: stateURL.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    try """
    {
      "agentPlan" : null,
      "agentStatusMessage" : "Restored persisted agent state",
      "generatedAt" : "2026-06-06T00:00:00Z",
      "lastWorkflowSummaryPath" : null,
      "stepExecutions" : [],
      "version" : 1
    }
    """.data(using: .utf8)!.write(to: stateURL)

    let normalStore = WorkbenchStore(loadSecrets: false, defaults: defaults)
    #expect(normalStore.agentStatusMessage == "Restored persisted agent state")

    let isolatedStore = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    #expect(isolatedStore.agentStatusMessage != "Restored persisted agent state")
    #expect(isolatedStore.jobs.isEmpty)
  }

  @Test
  @MainActor
  func completedAgentPlanIsNotRestoredAsActiveWorkflowOnStartup() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Completed-State-\(UUID().uuidString)", isDirectory: true)
    let stateURL = outputRoot
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("agent_state.json")
    defer { try? FileManager.default.removeItem(at: outputRoot) }
    defaults.set(outputRoot.path, forKey: "outputRootPath")

    let completedSteps = (1...16).map { index in
      AgentPlanStep(
        capabilityID: "legacy.docus.step\(index)",
        summary: "Completed DOCUS step \(index).",
        rawArguments: "",
        usesInputs: index > 1,
        usesPreviousOutput: index > 2
      )
    }
    let plan = AgentPlan(
      title: "Finished DOCUS-like workflow",
      rationale: "A completed plan should not stay armed on launch.",
      steps: completedSteps,
      source: .local
    )
    try AgentStateStore().persist(
      snapshot: AgentStateSnapshot(
        agentPlan: plan,
        stepExecutions: completedSteps.enumerated().map { offset, step in
          AgentPlanStepExecution(
            stepID: step.id,
            capabilityID: step.capabilityID,
            jobID: UUID(),
            status: .succeeded,
            runDirectory: outputRoot.appendingPathComponent("run-\(offset + 1)").path,
            finishedAt: Date()
          )
        },
        lastWorkflowSummaryPath: outputRoot.appendingPathComponent("summaries/latest.md").path,
        agentStatusMessage: "Workflow finished: 16/16 enabled steps completed."
      ),
      to: stateURL
    )

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    #expect(store.agentPlan == nil)
    #expect(store.agentPlanStepExecutions.isEmpty)
    #expect(store.lastWorkflowSummaryPath?.hasSuffix("summaries/latest.md") == true)
    #expect(store.agentStatusMessage.contains("Previous workflow finished"))

    let reloaded = try #require(try AgentStateStore().load(from: stateURL))
    #expect(reloaded.agentPlan == nil)
    #expect(reloaded.stepExecutions.isEmpty)
  }

  @Test
  @MainActor
  func transientGateOutputRootDefaultsAreResetOnStartup() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let pollutedOutputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("scientificworkbench-bundle-verify.TEST", isDirectory: true)
      .appendingPathComponent("output", isDirectory: true)
      .path
    defaults.set(pollutedOutputRoot, forKey: "outputRootPath")

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    #expect(store.outputRootPath == DefaultPaths.outputRoot)
    #expect(defaults.string(forKey: "outputRootPath") == DefaultPaths.outputRoot)
  }

  @Test
  @MainActor
  func applyingOllamaModelProfilePersistsModelAndUpdatesSetupTarget() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.aiConnectionStatuses[.ollama] = AIConnectionStatus(
      state: .connected,
      message: "Connected using previous model.",
      checkedAt: Date()
    )

    store.applyOllamaModelProfile(.compact)

    #expect(store.model(for: .ollama) == "qwen3:1.7b")
    #expect(store.ollamaSetupStatus.targetModel == "qwen3:1.7b")
    #expect(store.connectionStatus(for: .ollama).state == .unknown)
    #expect(defaults.string(forKey: "ollamaModel") == "qwen3:1.7b")
  }

  @Test
  @MainActor
  func testLocalAIConnectionDoesNotCreateOrMutateWorkflowState() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let recorder = RequestRecorder(responseBody: #"{"message":{"content":"OK"}}"#)
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: recorder.load)
    )
    let firstStep = AgentPlanStep(
      capabilityID: "datanalysis_env.status",
      summary: "Check environment.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let secondStep = AgentPlanStep(
      capabilityID: "profile_table",
      summary: "Profile a table.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let existingPlan = AgentPlan(
      title: "Edited",
      rationale: "User-edited draft plan.",
      steps: [firstStep, secondStep],
      source: .local
    )
    let existingExecution = AgentPlanStepExecution(
      stepID: firstStep.id,
      capabilityID: firstStep.capabilityID,
      jobID: UUID(),
      status: .succeeded,
      runDirectory: "/tmp/scientific-workbench-existing-run",
      finishedAt: Date()
    )
    let existingMessages = store.agentChatMessages

    store.aiProvider = .ollama
    store.agentPrompt = "This prompt must not be planned by the Test button."
    store.agentPlan = existingPlan
    store.agentPlanStepExecutions = [firstStep.id: existingExecution]
    store.agentStatusMessage = "Existing status message."

    await store.testAIConnection(.ollama)

    #expect(store.connectionStatus(for: .ollama).state == .connected)
    #expect(store.agentPrompt == "This prompt must not be planned by the Test button.")
    #expect(store.agentPlan == existingPlan)
    #expect(store.agentPlanStepExecutions == [firstStep.id: existingExecution])
    #expect(store.agentChatMessages == existingMessages)
    #expect(store.agentStatusMessage == "Existing status message.")
    #expect(store.agentMode == .auto)
    #expect(store.agentAutoRun == false)
  }

  @Test
  @MainActor
  func cloudChatFailureDoesNotRunCodexBridgeAutomatically() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-No-Codex-Fallback-\(UUID().uuidString)", isDirectory: true)
    let fakeCodex = root.appendingPathComponent("fake-codex")
    let sentinel = root.appendingPathComponent("codex-was-run")
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try """
    #!/bin/sh
    touch "\(sentinel.path)"
    exit 0
    """.write(to: fakeCodex, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: 0o755],
      ofItemAtPath: fakeCodex.path
    )

    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      cloudAIClient: CloudAIClient(dataLoader: { _ in
        throw URLError(.timedOut)
      })
    )
    store.agentMode = .chat
    store.aiProvider = .openAI
    store.openAIAPIKey = "sk-test-openai"
    store.codexExecutablePath = fakeCodex.path
    store.agentPrompt = "Answer this in chat mode."

    await store.submitAgentChatPrompt()
    #expect(store.pendingCloudConsentRequest?.provider == .openAI)
    await store.confirmPendingCloudRequest()

    #expect(!FileManager.default.fileExists(atPath: sentinel.path))
    #expect(store.agentChatMessages.last?.role == .assistant)
    #expect(store.agentChatMessages.last?.text.contains("Codex was not run automatically") == true)
    #expect(store.agentChatMessages.last?.text.contains("Switch Mode to Codex") == true)
  }

  @Test
  @MainActor
  func exportAndImportConfigurationRoundTripsWithoutSecrets() async throws {
    let exportDefaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let importDefaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Config-\(UUID().uuidString)", isDirectory: true)
    let exportURL = outputRoot.appendingPathComponent("config.json")
    let untrustedSkillRoot = outputRoot.appendingPathComponent("untrusted-skill", isDirectory: true)
    let untrustedExecutable = outputRoot.appendingPathComponent("untrusted-python")
    let executionMarker = outputRoot.appendingPathComponent("untrusted-executable-ran")
    let secret = "sk-secret-config-export"
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    try FileManager.default.createDirectory(
      at: untrustedSkillRoot,
      withIntermediateDirectories: true
    )
    let markerScript = "#!/bin/sh\nprintf executed > '\(executionMarker.path)'\n"
    try markerScript.write(to: untrustedExecutable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: 0o755],
      ofItemAtPath: untrustedExecutable.path
    )

    let exportingStore = WorkbenchStore(loadSecrets: false, defaults: exportDefaults)
    exportingStore.skillRootPath = untrustedSkillRoot.path
    exportingStore.outputRootPath = outputRoot.path
    exportingStore.pythonExecutable = untrustedExecutable.path
    exportingStore.aiProvider = .gemini
    exportingStore.ollamaModel = "qwen3:8b"
    exportingStore.ollamaBaseURL = "http://127.0.0.1:11434"
    exportingStore.openAIModel = "gpt-test"
    exportingStore.grokModel = "grok-test"
    exportingStore.geminiModel = "gemini-test"
    exportingStore.cloudAttachmentContextMode = .none
    exportingStore.codexExecutablePath = "/Applications/Codex.app/Contents/Resources/codex"
    exportingStore.codexSandboxMode = "workspace-write"
    exportingStore.externalProcessTimeoutMinutes = 95
    exportingStore.openAIAPIKey = secret
    exportingStore.grokAPIKey = secret
    exportingStore.geminiAPIKey = secret

    let exportedPath = try #require(exportingStore.exportConfiguration(
      to: exportURL.path,
      revealInFinder: false
    ))
    let exportedJSON = try String(contentsOfFile: exportedPath, encoding: .utf8)

    #expect(exportedJSON.contains(#""aiProvider" : "gemini""#))
    #expect(exportedJSON.contains(#""ollamaModel" : "qwen3:8b""#))
    #expect(exportedJSON.contains(#""cloudAttachmentContextMode" : "none""#))
    #expect(exportedJSON.contains(#""externalProcessTimeoutMinutes" : 95"#))
    #expect(!exportedJSON.contains(secret))
    #expect(!exportedJSON.localizedCaseInsensitiveContains("apikey"))
    #expect(!exportedJSON.localizedCaseInsensitiveContains("api_key"))

    let importingStore = WorkbenchStore(loadSecrets: false, defaults: importDefaults)
    let localSkillRoot = outputRoot.appendingPathComponent("local-skill", isDirectory: true).path
    let localOutputRoot = outputRoot.appendingPathComponent("local-output", isDirectory: true).path
    let localPython = "/usr/bin/python3"
    let localCodex = "/Applications/Codex.app/Contents/Resources/codex"
    try FileManager.default.createDirectory(
      at: URL(fileURLWithPath: localSkillRoot, isDirectory: true),
      withIntermediateDirectories: true
    )
    importingStore.skillRootPath = localSkillRoot
    importingStore.outputRootPath = localOutputRoot
    importingStore.pythonExecutable = localPython
    importingStore.codexExecutablePath = localCodex
    importingStore.codexSandboxMode = "read-only"
    importingStore.openAIAPIKey = "existing-openai-key"
    importingStore.grokAPIKey = "existing-grok-key"
    importingStore.geminiAPIKey = "existing-gemini-key"
    importingStore.aiConnectionStatuses[.gemini] = AIConnectionStatus(
      state: .connected,
      message: "old status",
      checkedAt: Date()
    )

    #expect(importingStore.importConfiguration(from: exportedPath))
    #expect(importingStore.skillRootPath == localSkillRoot)
    #expect(importingStore.outputRootPath == localOutputRoot)
    #expect(importingStore.pythonExecutable == localPython)
    #expect(importingStore.aiProvider == .gemini)
    #expect(importingStore.ollamaModel == "qwen3:8b")
    #expect(importingStore.ollamaBaseURL == "http://127.0.0.1:11434")
    #expect(importingStore.openAIModel == "gpt-test")
    #expect(importingStore.grokModel == "grok-test")
    #expect(importingStore.geminiModel == "gemini-test")
    #expect(importingStore.cloudAttachmentContextMode == .none)
    #expect(importingStore.codexExecutablePath == localCodex)
    #expect(importingStore.codexSandboxMode == "read-only")
    #expect(importingStore.externalProcessTimeoutMinutes == 95)
    #expect(importingStore.openAIAPIKey == "existing-openai-key")
    #expect(importingStore.grokAPIKey == "existing-grok-key")
    #expect(importingStore.geminiAPIKey == "existing-gemini-key")
    #expect(importingStore.connectionStatus(for: .gemini).state == .unknown)
    #expect(importingStore.ollamaSetupStatus.targetModel == "qwen3:8b")
    #expect(importDefaults.string(forKey: "aiProvider") == "gemini")
    #expect(importDefaults.string(forKey: "cloudAttachmentContextMode") == "none")
    #expect(importDefaults.integer(forKey: "externalProcessTimeoutMinutes") == 95)
    #expect(importDefaults.string(forKey: "skillRootPath") == localSkillRoot)
    #expect(importDefaults.string(forKey: "outputRootPath") == localOutputRoot)
    #expect(importDefaults.string(forKey: "pythonExecutable") == localPython)
    #expect(importDefaults.string(forKey: "codexExecutablePath") == localCodex)
    #expect(importDefaults.string(forKey: "codexSandboxMode") == "read-only")
    #expect(importingStore.agentStatusMessage.contains("Local paths, executables, the Codex sandbox, and API keys were not imported or changed"))

    await importingStore.startupRefresh()
    #expect(!FileManager.default.fileExists(atPath: executionMarker.path))
  }

  @Test
  @MainActor
  func storeLoadsAndClearsPersistedJobHistory() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Job-History-\(UUID().uuidString)", isDirectory: true)
    let historyURL = outputRoot
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("jobs.json")
    try FileManager.default.createDirectory(
      at: historyURL.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    defaults.set(outputRoot.path, forKey: "outputRootPath")
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let jobID = UUID()
    let payload = """
    {
      "version": 1,
      "generatedAt": "2026-05-26T10:00:00Z",
      "jobs": [
        {
          "id": "\(jobID.uuidString)",
          "capabilityID": "profile_table",
          "capabilityLabel": "profile_table.py",
          "status": "running",
          "command": "python profile_table",
          "stdout": "",
          "stderr": "",
          "runDirectory": "\(outputRoot.appendingPathComponent("run").path)",
          "artifacts": [],
          "createdAt": "2026-05-26T10:00:00Z"
        }
      ]
    }
    """
    try payload.write(to: historyURL, atomically: true, encoding: .utf8)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    #expect(store.jobs.count == 1)
    #expect(store.jobs.first?.id == jobID)
    #expect(store.jobs.first?.status == .cancelled)
    #expect(store.jobs.first?.message == "Run was interrupted before the app closed.")
    #expect(store.selectedJobID == jobID)

    store.clearJobHistory()

    #expect(store.jobs.isEmpty)
    let clearedData = try Data(contentsOf: historyURL)
    let clearedObject = try #require(try JSONSerialization.jsonObject(with: clearedData) as? [String: Any])
    let clearedJobs = try #require(clearedObject["jobs"] as? [Any])
    #expect(clearedJobs.isEmpty)
  }

  @Test
  @MainActor
  func storeExportsEditableAgentPlanAsRedactedJSON() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Plan-Export-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.outputRootPath = outputRoot.path
    store.inputPaths = ["/tmp/input.csv"]
    store.openAIAPIKey = "sk-secret-plan-export"
    store.aiProvider = .openAI
    store.openAIModel = "gpt-test"
    store.agentMode = .workflow
    store.agentAutoRun = true
    store.agentPlan = AgentPlan(
      title: "Plan sk-secret-plan-export",
      rationale: "Profile a table safely.",
      steps: [
        AgentPlanStep(
          capabilityID: "profile_table",
          summary: "Use sk-secret-plan-export only as a redaction test.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        )
      ],
      source: .local
    )

    let exportPath = try #require(store.exportAgentPlan())
    let data = try Data(contentsOf: URL(fileURLWithPath: exportPath))
    let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let plan = try #require(object["plan"] as? [String: Any])
    let steps = try #require(plan["steps"] as? [[String: Any]])

    #expect(store.lastExportedPlanPath == exportPath)
    #expect(object["version"] as? Int == ExportedAgentPlanPayload.currentVersion)
    #expect(object["aiProvider"] as? String == "openAI")
    #expect(object["aiModel"] as? String == "gpt-test")
    #expect(object["mode"] as? String == "workflow")
    #expect(object["autoRun"] as? Bool == true)
    #expect((plan["title"] as? String)?.contains("[REDACTED]") == true)
    #expect((steps.first?["summary"] as? String)?.contains("[REDACTED]") == true)
    #expect(!String(data: data, encoding: .utf8)!.contains("sk-secret-plan-export"))
  }

  @Test
  @MainActor
  func storeImportsExportedPlanRestoresExistingInputsAndDisablesMissingCapabilities() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Plan-Import-\(UUID().uuidString)", isDirectory: true)
    let inputURL = tempRoot.appendingPathComponent("input.csv")
    let planURL = tempRoot.appendingPathComponent("plan.json")
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    try "x,y\n1,2\n".write(to: inputURL, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: tempRoot) }
    defaults.set(tempRoot.path, forKey: "outputRootPath")

    let exportedPlan = AgentPlan(
      title: "Reusable table plan",
      rationale: "Profile then run a missing follow-up.",
      steps: [
        AgentPlanStep(
          capabilityID: "profile_table",
          summary: "Profile table.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: "missing_tool",
          summary: "This should be disabled.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: true
        )
      ],
      source: .local
    )
    let payload = ExportedAgentPlanPayload(
      version: 1,
      generatedAt: Date(timeIntervalSince1970: 1_000),
      outputRootPath: tempRoot.path,
      inputPaths: [inputURL.path, tempRoot.appendingPathComponent("missing.csv").path],
      aiProvider: .ollama,
      aiModel: "qwen3:4b-instruct",
      mode: .workflow,
      autoRun: false,
      plan: exportedPlan
    )
    let data = try JSONEncoder.scientificWorkbench.encode(payload)
    try data.write(to: planURL)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.capabilities = [
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
    ]

    let imported = try #require(store.importAgentPlan(from: planURL.path))

    #expect(imported.title == "Reusable table plan")
    #expect(store.agentPlan?.steps.count == 2)
    #expect(store.agentPlan?.steps[0].isEnabled == true)
    #expect(store.agentPlan?.steps[1].isEnabled == false)
    #expect(store.inputPaths == [inputURL.path])
    #expect(store.agentMode == .workflow)
    #expect(store.agentAutoRun == false)
    #expect(store.agentStatusMessage.contains("Disabled 1 missing step"))
    #expect(store.agentStatusMessage.contains("Restored 1/2 input paths"))
  }

  @Test
  @MainActor
  func dryRunAgentPlanBuildsCommandsWithoutExecuting() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.outputRootPath = "/tmp/scientific-workbench-dry-run"
    store.inputPaths = ["/tmp/table.csv"]
    store.capabilities = [
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
    ]
    store.agentPlan = AgentPlan(
      title: "Dry run table plan",
      rationale: "Validate command build.",
      steps: [
        AgentPlanStep(
          capabilityID: "profile_table",
          summary: "Profile table.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        )
      ],
      source: .local
    )

    let report = store.dryRunAgentPlan()

    #expect(report.contains("No commands were executed"))
    #expect(report.contains("OK `profile_table.py`"))
    #expect(report.contains("profile_table"))
    #expect(report.contains("/tmp/table.csv"))
    #expect(store.agentStatusMessage == "Dry run passed.")
    #expect(store.jobs.isEmpty)
  }

  @Test
  @MainActor
  func dryRunAgentPlanReportsMissingInputBeforeRun() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.capabilities = [
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
    ]
    store.agentPlan = AgentPlan(
      title: "Missing input",
      rationale: "Should block.",
      steps: [
        AgentPlanStep(
          capabilityID: "profile_table",
          summary: "Profile table.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        )
      ],
      source: .local
    )

    let report = store.dryRunAgentPlan()

    #expect(report.contains("BLOCKED `profile_table.py`"))
    #expect(report.contains("needs at least one input"))
    #expect(store.agentStatusMessage == "Dry run found issues.")
    #expect(store.jobs.isEmpty)
  }

  @Test
  @MainActor
  func dryRunLegacyIRAFUsesNoSpaceWorkspaceWhenOutputRootHasSpaces() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.outputRootPath = "/tmp/Scientific Workbench Runs"
    store.inputPaths = ["/tmp/DOCUS"]
    store.capabilities = [
      CapabilityEntry(
        id: "fxcor_iraf_workbench.prepare-session",
        label: "fxcor_iraf_workbench.py prepare-session",
        script: "scripts/fxcor_iraf_workbench.py",
        visibleBlock: "astronomy observational",
        kind: "supporting_tool",
        supportLevel: "narrow",
        platform: "portable",
        requiresDatanalysis: false,
        preflightMode: "none",
        smokeTier: "none",
        shortDescription: "Prepare an IRAF/fxcor workspace."
      )
    ]
    store.agentPlan = AgentPlan(
      title: "Legacy dry run",
      rationale: "Validate safe workspace routing.",
      steps: [
        AgentPlanStep(
          capabilityID: "fxcor_iraf_workbench.prepare-session",
          summary: "Prepare workspace.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        )
      ],
      source: .local
    )

    let report = store.dryRunAgentPlan()

    #expect(report.contains("OK `fxcor_iraf_workbench.py prepare-session`"))
    #expect(report.contains("ScientificWorkbenchRuns/LegacyWorkspaces"))
    #expect(report.contains("fxcor_workspace"))
    #expect(!report.contains("/tmp/Scientific Workbench Runs"))
    #expect(store.legacyWorkspaceNotice?.contains("automatically") == true)
    #expect(store.jobs.isEmpty)
  }

  @Test
  @MainActor
  func retryJobRunsSameCapabilityAndTracksSourceJob() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let skillRoot = try makeSuccessfulEnvironmentSkillFixture()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    defaults.set(skillRoot.path, forKey: "skillRootPath")
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Retry-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.outputRootPath = outputRoot.path
    let capability = CapabilityEntry(
      id: "datanalysis_env.status",
      label: "datanalysis_env.py status",
      script: "scripts/datanalysis_env.py",
      visibleBlock: "core / routing",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Check environment."
    )
    store.capabilities = [capability]

    var failedJob = JobRecord(capability: capability, runDirectory: outputRoot.appendingPathComponent("failed").path)
    failedJob.status = .failed
    failedJob.exitCode = 2
    failedJob.finishedAt = Date()
    failedJob.requestInputPaths = []
    failedJob.requestRawArguments = ""
    store.jobs = [failedJob]

    let message = await store.retryJob(failedJob)

    let retried = try #require(store.jobs.first)
    #expect(message.contains("Retry finished"))
    #expect(retried.id != failedJob.id)
    #expect(retried.retryOfJobID == failedJob.id)
    #expect(retried.capabilityID == "datanalysis_env.status")
    #expect(retried.requestInputPaths == [])
    #expect(retried.requestRawArguments == "")
    #expect(retried.command.contains(skillRoot.path))
    #expect(retried.status == .succeeded)
    #expect(retried.artifacts.contains { $0.relativePath == "summary.json" })
  }

  @Test
  @MainActor
  func retryJobBlocksWhenCapabilityIsMissing() async {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    let capability = CapabilityEntry(
      id: "missing_tool",
      label: "missing_tool.py",
      script: "scripts/missing_tool.py",
      visibleBlock: "core / routing",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Missing."
    )
    var failedJob = JobRecord(capability: capability, runDirectory: "/tmp/missing")
    failedJob.status = .failed
    store.jobs = [failedJob]
    store.capabilities = []

    let message = await store.retryJob(failedJob)

    #expect(message.contains("capability is not available"))
    #expect(store.jobs.count == 1)
    #expect(store.jobs.first?.id == failedJob.id)
  }

  @Test
  @MainActor
  func agentWorkflowCanResumeAfterDisablingFailedStep() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let skillRoot = try makeSuccessfulEnvironmentSkillFixture()
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    defaults.set(skillRoot.path, forKey: "skillRootPath")
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Workflow-Resume-\(UUID().uuidString)", isDirectory: true)
    defaults.set(outputRoot.path, forKey: "outputRootPath")
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    let envCapability = environmentCapability()
    let tableCapability = sampleCapability()
    store.capabilities = [envCapability, tableCapability]

    let firstStep = AgentPlanStep(
      capabilityID: envCapability.id,
      summary: "Check environment.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let blockedStep = AgentPlanStep(
      capabilityID: tableCapability.id,
      summary: "Profile a missing table.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    let finalStep = AgentPlanStep(
      capabilityID: envCapability.id,
      summary: "Confirm the workflow can continue.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    store.agentPlan = AgentPlan(
      title: "Resume test",
      rationale: "A blocked middle step should not force a full rerun.",
      steps: [firstStep, blockedStep, finalStep],
      source: .local
    )

    let firstResult = await store.runAgentPlan()

    #expect(firstResult.contains("Workflow stopped at profile_table.py"))
    #expect(store.jobs.contains { $0.capabilityID == envCapability.id && $0.command.contains(skillRoot.path) })
    #expect(store.agentPlanStepExecutions[firstStep.id]?.status == .succeeded)
    #expect(store.agentPlanStepExecutions[blockedStep.id]?.status == .blocked)
    #expect(store.agentPlanStepExecutions[finalStep.id] == nil)
    #expect(store.canResumeAgentPlan == true)
    let recovery = try #require(store.workflowRecoveryState)
    #expect(recovery.completedCount == 1)
    #expect(recovery.totalCount == 3)
    #expect(recovery.resumeStepCapabilityID == tableCapability.id)
    #expect(recovery.stoppedStatus == .blocked)
    #expect(recovery.stoppedJobLabel == tableCapability.label)
    #expect(recovery.canResume == true)
    #expect(store.jobs.count == 2)

    let reloadedStore = WorkbenchStore(loadSecrets: false, defaults: defaults)
    reloadedStore.capabilities = [envCapability, tableCapability]

    #expect(reloadedStore.agentPlan?.title == "Resume test")
    #expect(reloadedStore.agentPlanStepExecutions[firstStep.id]?.status == .succeeded)
    #expect(reloadedStore.agentPlanStepExecutions[blockedStep.id]?.status == .blocked)
    #expect(reloadedStore.agentPlanStepExecutions[finalStep.id] == nil)
    #expect(reloadedStore.canResumeAgentPlan == true)
    #expect(reloadedStore.workflowRecoveryState?.resumeStepCapabilityID == tableCapability.id)
    #expect(reloadedStore.jobs.count == 2)

    reloadedStore.updateAgentPlanStep(blockedStep.id) { step in
      step.isEnabled = false
    }

    #expect(reloadedStore.agentPlanStepExecutions[firstStep.id]?.status == .succeeded)
    #expect(reloadedStore.agentPlanStepExecutions[blockedStep.id] == nil)
    let recoveryAfterEdit = try #require(reloadedStore.workflowRecoveryState)
    #expect(recoveryAfterEdit.completedCount == 1)
    #expect(recoveryAfterEdit.totalCount == 2)
    #expect(recoveryAfterEdit.resumeStepCapabilityID == envCapability.id)
    #expect(recoveryAfterEdit.stoppedStatus == nil)

    let resumedResult = await reloadedStore.resumeAgentPlanFromLastSuccess()

    #expect(resumedResult.contains("Workflow finished: 2/2 enabled steps completed."))
    #expect(reloadedStore.agentPlanStepExecutions[finalStep.id]?.status == .succeeded)
    #expect(reloadedStore.canResumeAgentPlan == false)
    #expect(reloadedStore.jobs.count == 3)
    #expect(reloadedStore.jobs.filter { $0.capabilityID == envCapability.id }.count == 2)
  }

  @Test
  @MainActor
  func setupChecklistReportsReadyCoreState() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Setup-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.outputRootPath = outputRoot.path
    store.capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    store.environmentStatus = EnvironmentStatus(
      status: "ok",
      skillRoot: DefaultPaths.motherSkillRoot,
      datanalysisPython: "/usr/bin/python3",
      datanalysisRoot: DefaultPaths.motherSkillRoot,
      details: "Ready.",
      warnings: [],
      refreshedAt: Date()
    )
    store.ollamaSetupStatus = OllamaSetupStatus(
      cliPath: "/usr/local/bin/ollama",
      serverReachable: true,
      installedModels: [store.model(for: .ollama)],
      targetModel: store.model(for: .ollama),
      message: "Ready.",
      checkedAt: Date()
    )

    #expect(store.setupChecklistIsReady)
    #expect(store.setupChecklistItems.filter(\.isRequired).allSatisfy { $0.state == .ready })
    #expect(store.setupRecoveryState == nil)
  }

  @Test
  @MainActor
  func setupChecklistFlagsMissingLocalAI() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Setup-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.outputRootPath = outputRoot.path
    store.capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    store.environmentStatus = EnvironmentStatus(
      status: "ok",
      skillRoot: DefaultPaths.motherSkillRoot,
      datanalysisPython: "/usr/bin/python3",
      datanalysisRoot: DefaultPaths.motherSkillRoot,
      details: "Ready.",
      warnings: [],
      refreshedAt: Date()
    )
    store.ollamaSetupStatus = .unknown(model: store.model(for: .ollama))

    let localAI = try #require(store.setupChecklistItems.first { $0.id == "local_ai" })
    #expect(!store.setupChecklistIsReady)
    #expect(localAI.state == .action)
    #expect(localAI.detail.contains(store.model(for: .ollama)))
  }

  @Test
  @MainActor
  func setupRecoveryStateExplainsBlockingSetupItems() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let missingOutputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Missing-Output-\(UUID().uuidString)", isDirectory: true)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.outputRootPath = missingOutputRoot.path
    store.capabilities = []
    store.environmentStatus = .unknown(skillRoot: DefaultPaths.motherSkillRoot)
    store.ollamaSetupStatus = .unknown(model: store.model(for: .ollama))

    let recovery = try #require(store.setupRecoveryState)

    #expect(recovery.badgeTitle == "action")
    #expect(recovery.blockingItemIDs.contains("environment"))
    #expect(recovery.blockingItemIDs.contains("capabilities"))
    #expect(recovery.blockingItemIDs.contains("output_root"))
    #expect(recovery.blockingItemIDs.contains("local_ai"))
    #expect(recovery.detail.contains("Scientific environment"))
    #expect(recovery.recommendedActions.contains { $0.contains("Refresh Environment") })
    #expect(recovery.recommendedActions.contains { $0.contains("Reload Registry") })
    #expect(recovery.recommendedActions.contains { $0.contains("output folder") })
    #expect(recovery.recommendedActions.contains { $0.contains("Test Local AI") })
  }

  @Test
  @MainActor
  func editableAgentPlanStepUpdatesStorePlan() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Editable-Plan-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }
    defaults.set(outputRoot.path, forKey: "outputRootPath")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    let envStep = AgentPlanStep(
      capabilityID: "datanalysis_env.status",
      summary: "Check environment.",
      rawArguments: "",
      usesInputs: false,
      usesPreviousOutput: false
    )
    let tableStep = AgentPlanStep(
      capabilityID: "profile_table",
      summary: "Profile table.",
      rawArguments: "",
      usesInputs: true,
      usesPreviousOutput: false
    )
    store.agentPlan = AgentPlan(
      title: "Editable",
      rationale: "Original rationale.",
      steps: [envStep, tableStep],
      source: .local
    )

    store.updateAgentPlanTitle("Edited")
    store.updateAgentPlanRationale("Edited rationale.")
    store.updateAgentPlanStep(envStep.id) { step in
      step.isEnabled = false
      step.rawArguments = "--safe"
    }

    #expect(store.agentPlan?.title == "Edited")
    #expect(store.agentPlan?.rationale == "Edited rationale.")
    #expect(store.agentPlan?.steps.first?.isEnabled == false)
    #expect(store.agentPlan?.steps.first?.rawArguments == "--safe")
    #expect(store.enabledAgentPlanSteps.map(\.capabilityID) == ["profile_table"])
  }

  @Test
  @MainActor
  func unsafeOutputRootBlocksRunBeforeCreatingAJob() async {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".ssh", isDirectory: true)
      .appendingPathComponent("scientific-workbench", isDirectory: true)
      .path

    let result = await store.run(capability: sampleCapability(), rawArguments: "")

    #expect(result == nil)
    #expect(store.jobs.isEmpty)
    #expect(store.agentStatusMessage.contains("Unsafe output root"))
  }

  @Test
  @MainActor
  func higherRiskOutputRootRequiresSessionApproval() async {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.outputRootPath = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Desktop", isDirectory: true)
      .path

    let result = await store.run(capability: sampleCapability(), rawArguments: "")

    #expect(result == nil)
    #expect(store.jobs.isEmpty)
    #expect(store.agentStatusMessage.contains("confirm the path in Settings"))
    store.outputRootRiskApproved = true
    store.outputRootPath += "/Scientific Workbench Runs"
    #expect(!store.outputRootRiskApproved)
  }

  @Test
  @MainActor
  func runDirectoryOverrideCannotEscapeConfiguredRoot() async {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Safe-Root-\(UUID().uuidString)", isDirectory: true)
    let outside = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Outside-\(UUID().uuidString)", isDirectory: true)
    defaults.set(outputRoot.path, forKey: "outputRootPath")
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )

    let result = await store.run(
      capability: sampleCapability(),
      rawArguments: "",
      runDirectoryOverride: outside.path
    )

    #expect(result == nil)
    #expect(store.jobs.isEmpty)
    #expect(store.agentStatusMessage.contains("run folder must be a child"))
  }

  @Test
  @MainActor
  func registryReloadSurfacesOptionalModuleDegradationWithoutBlockingCore() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let mother = try makeScenarioFixture(
      name: "degraded-store-registry",
      files: [
        "public_surface_registry.yaml": """
        entries:
          - id: datanalysis_env.status
            label: datanalysis_env.py status
            script: scripts/datanalysis_env.py
            visible_block: core / routing
            kind: golden_path
            support_level: stable
            platform: portable
            requires_datanalysis: false
            preflight_mode: none
            smoke_tier: core
            short_description: Environment status.
        """,
        "scripts/datanalysis_env.py": "# fixture\n",
      ]
    )
    defer { try? FileManager.default.removeItem(at: mother) }
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.skillRootPath = mother.path

    await store.reloadRegistry()

    #expect(store.registryError == nil)
    #expect(store.capabilities.map(\.id) == ["datanalysis_env.status"])
    #expect(store.registryNotice?.contains("Optional skill modules unavailable") == true)
    #expect(store.registryNotice?.contains("scientific-data-astro") == true)
  }

}

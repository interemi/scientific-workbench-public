import Foundation
import AppKit
import Darwin
import UniformTypeIdentifiers

private struct PendingCloudAgentSubmission {
  var prompt: String
  var resolvedMode: AgentRunMode
  var request: CloudConsentRequest
}

@MainActor
final class WorkbenchStore: ObservableObject {
  @Published var selectedSection: AppSection? = .agent
  @Published var capabilities: [CapabilityEntry] = []
  @Published var selectedCapabilityID: String?
  @Published var capabilityCatalogMode: CapabilityCatalogMode = .normal
  @Published var jobs: [JobRecord] = []
  @Published var selectedJobID: UUID?
  @Published var inputPaths: [String] = [] {
    didSet {
      if oldValue != inputPaths {
        invalidateOutputRootRiskApprovalIfContextChanged()
      }
    }
  }
  @Published var searchText = ""
  @Published var skillRootPath: String
  @Published var outputRootPath: String {
    didSet {
      if oldValue != outputRootPath {
        outputRootRiskApproved = false
      }
    }
  }
  @Published var outputRootRiskApproved = false {
    didSet {
      if outputRootRiskApproved {
        outputRootRiskApprovalFingerprint = currentOutputRootRiskApprovalFingerprint(
          inputPaths: inputPaths
        )
      } else {
        outputRootRiskApprovalFingerprint = nil
      }
    }
  }
  @Published var pythonExecutable: String
  @Published var externalProcessTimeoutMinutes: Int
  @Published var registryError: String?
  @Published var registryNotice: String?
  @Published var persistenceRecoveryNotice: String?
  @Published var lastPersistenceRecoveryArchivePath: String?
  @Published var environmentStatus: EnvironmentStatus
  @Published var agentPrompt = ""
  @Published var agentPlan: AgentPlan?
  @Published var agentPlanStepExecutions: [AgentPlanStep.ID: AgentPlanStepExecution] = [:]
  @Published var agentStatusMessage = "Write a prompt, add optional inputs, then ask the agent to plan a workflow."
  @Published var agentChatMessages: [AgentChatMessage] = [
    AgentChatMessage(
      role: .assistant,
      text: "Tell me what you want to do, attach files or folders if useful, and I will decide whether to answer, plan a workflow, or suggest Codex for explicit coding-agent work. Outputs stay away from your originals unless you explicitly choose otherwise."
    )
  ]
  @Published var agentAutoRun = false
  @Published var agentMode: AgentRunMode = .auto
  @Published var isPlanningAgentWorkflow = false
  @Published var isRunningAgentWorkflow = false
  @Published var isCancellationRequested = false
  @Published var lastWorkflowSummaryPath: String?
  @Published var lastExportedPlanPath: String?
  @Published var ollamaSetupStatus: OllamaSetupStatus
  @Published var isCheckingOllamaSetup = false
  @Published var isPullingOllamaModel = false
  @Published var isRunningCodexBridge = false
  @Published var aiProvider: AIProvider
  @Published var ollamaModel: String
  @Published var ollamaBaseURL: String
  @Published var openAIAPIKey: String
  @Published var openAIModel: String
  @Published var grokAPIKey: String
  @Published var grokModel: String
  @Published var geminiAPIKey: String
  @Published var geminiModel: String
  @Published var credentialSaveMessage: String? = nil
  @Published var credentialSaveFailed = false
  @Published var cloudAttachmentContextMode: CloudAttachmentContextMode
  @Published var pendingCloudConsentRequest: CloudConsentRequest?
  @Published var aiConnectionStatuses: [AIProvider: AIConnectionStatus] = Dictionary(
    uniqueKeysWithValues: AIProvider.allCases.map { ($0, .unknown) }
  )
  @Published var codexExecutablePath: String
  @Published var codexSandboxMode: String
  @Published var stiltsCommand: String
  @Published var stiltsJar: String
  @Published var topcatCommand: String
  @Published var topcatJar: String
  @Published var aptCommand: String
  @Published var aptPreferences: String
  @Published var optionalAstronomyBackendStatus: OptionalAstronomyBackendStatus = .unknown
  @Published var isCheckingOptionalAstronomyBackends = false
  @Published var radialVelocityReview: RadialVelocityTableReview?
  @Published var radialVelocityReviewError: String?
  @Published var isReviewingRadialVelocityInput = false
  @Published var radialVelocityTimeColumn: Int?
  @Published var radialVelocityValueColumn: Int?
  @Published var radialVelocityUncertaintyColumn: Int?
  @Published var radialVelocityTimeSystem: RadialVelocityTimeSystem = .jd
  @Published var radialVelocityUnit: RadialVelocityUnit = .kilometersPerSecond
  @Published var photometricCalibrationReview: PhotometricCalibrationReview?
  @Published var photometricCalibrationError: String?
  @Published var isReviewingPhotometricCalibration = false
  @Published var photometricInstrumentalColumn: Int?
  @Published var photometricCatalogColumn: Int?
  @Published var photometricAirmassColumn: Int?
  @Published var photometricFilterColumn: Int?
  @Published var photometricFilterValue: String?
  @Published var photometricFilterValues: [String] = []
  @Published var photometricUncertaintyColumn: Int?
  @Published var photometricColorColumn: Int?
  @Published var photometricIncludeColorTerm = false
  @Published var documentStyleReview: DOCXStyleReview?
  @Published var documentStyleError: String?
  @Published var isReviewingDocumentStyles = false
  @Published var docxRequireBold = false
  @Published var docxRequireItalic = false
  @Published var docxRequireUnderline = false
  @Published var docxFindText = ""
  @Published var docxReplacementText = ""
  @Published var docxReplacementConfirmed = false
  @Published var keynotePreflightReview: KeynotePreflightReview?
  @Published var keynoteWorkflowError: String?
  @Published var isCheckingKeynote = false
  @Published var isExportingKeynote = false
  @Published var keynoteExportConfirmed = false

  private let registryLoader = CapabilityRegistryLoader()
  private let runner = ProcessRunner()
  private let runBundleService = JobRunBundleService()
  private let envelopeParser = ToolEnvelopeParser()
  private let environmentService = SkillEnvironmentService()
  private let agentPlanner: AgentPlanner
  private let agentRoutingService = AgentRoutingService()
  private let cloudAIClient: CloudAIClient
  private let aiConnectionService: AIConnectionService
  private let ollamaSetupService = OllamaSetupService()
  private let configurationService = ConfigurationExportImportService()
  private let supportBundleService = SupportBundleService()
  private let launchTranscriptService = LaunchTranscriptService()
  private let workflowSummaryService = WorkflowSummaryService()
  private let workflowExecutionCoordinator = WorkflowExecutionCoordinator()
  private let jobHistoryStore = JobHistoryStore()
  private let agentStateStore = AgentStateStore()
  private let persistenceRecoveryArchive = PersistenceRecoveryArchive()
  private let setupChecklistService = SetupChecklistService()
  private let legacyWorkspacePolicy = LegacyWorkspacePolicy.shared
  private let workflowRecoveryService = WorkflowRecoveryService()
  private let workflowDryRunService = WorkflowDryRunService()
  private let optionalAstronomyBackendService = OptionalAstronomyBackendService()
  private let radialVelocityInspectionService = RadialVelocityInspectionService()
  private let photometricCalibrationService = PhotometricCalibrationService()
  private let documentWorkflowService = DocumentWorkflowService()
  private let filesystemSafetyPolicy: FilesystemSafetyPolicy
  private let runDirectoryFactory = RunDirectoryFactory()
  private let legacyReportProjectStagingService = LegacyReportProjectStagingService()
  private let defaults: UserDefaults
  private let credentialStore: any CloudCredentialStoring
  private var editedCredentialProviders: Set<AIProvider> = []
  private var handledLaunchAutomation = false
  private var forceLocalPlanner = false
  private var enableRestrictedStepsForLaunchAutomation = false
  private var pendingCloudAgentSubmission: PendingCloudAgentSubmission?
  private var rememberedCloudConsentScopes: Set<CloudConsentSessionScope> = []
  private var outputRootRiskApprovalFingerprint: String?
  private var ollamaPullTask: Task<OllamaCommandResult, Error>?
  private var codexBridgeTask: Task<String, Error>?

  init(
    loadSecrets: Bool = true,
    defaults: UserDefaults = .standard,
    loadPersistedState: Bool = true,
    cloudAIClient: CloudAIClient = CloudAIClient(),
    credentialStore: any CloudCredentialStoring = KeychainCredentialStore(),
    filesystemSafetyPolicy: FilesystemSafetyPolicy = FilesystemSafetyPolicy()
  ) {
    self.defaults = defaults
    self.cloudAIClient = cloudAIClient
    self.credentialStore = credentialStore
    self.aiConnectionService = AIConnectionService(client: cloudAIClient)
    self.filesystemSafetyPolicy = filesystemSafetyPolicy
    self.agentPlanner = AgentPlanner(
      cloudAIClient: CloudAIPlannerClient(client: cloudAIClient)
    )
    let skillRoot = defaults.string(forKey: "skillRootPath") ?? DefaultPaths.motherSkillRoot
    let persistedOutputRoot = defaults.string(forKey: "outputRootPath") ?? DefaultPaths.outputRoot
    let outputRoot = DefaultPaths.sanitizedPersistedOutputRoot(persistedOutputRoot)
    if outputRoot != persistedOutputRoot {
      defaults.set(outputRoot, forKey: "outputRootPath")
    }
    let python = defaults.string(forKey: "pythonExecutable") ?? DefaultPaths.systemPython
    let storedTimeoutMinutes = defaults.object(forKey: "externalProcessTimeoutMinutes") == nil
      ? ExternalProcessTimeoutPolicy.defaultMinutes
      : defaults.integer(forKey: "externalProcessTimeoutMinutes")
    let storedAIProvider = AIProvider(rawValue: defaults.string(forKey: "aiProvider") ?? "") ?? .ollama
    let keychainAPIKey = loadSecrets && storedAIProvider == .openAI ? credentialStore.readKey(for: .openAI) : ""
    let keychainGrokKey = loadSecrets && storedAIProvider == .grok ? credentialStore.readKey(for: .grok) : ""
    let keychainGeminiKey = loadSecrets && storedAIProvider == .gemini ? credentialStore.readKey(for: .gemini) : ""
    let environmentAPIKey = ProcessInfo.processInfo.environment["OPENAI_API_KEY"] ?? ""
    let environmentGrokKey = ProcessInfo.processInfo.environment["XAI_API_KEY"] ?? ""
    let environmentGeminiKey = ProcessInfo.processInfo.environment["GEMINI_API_KEY"]
      ?? ProcessInfo.processInfo.environment["GOOGLE_API_KEY"]
      ?? ""
    skillRootPath = skillRoot
    outputRootPath = outputRoot
    pythonExecutable = python
    externalProcessTimeoutMinutes = ExternalProcessTimeoutPolicy.normalized(minutes: storedTimeoutMinutes)
    aiProvider = storedAIProvider
    let storedOllamaModel = defaults.string(forKey: "ollamaModel") ?? OllamaModelProfile.recommended.model
    ollamaModel = storedOllamaModel
    ollamaBaseURL = defaults.string(forKey: "ollamaBaseURL") ?? AIProvider.ollama.defaultBaseURL ?? "http://localhost:11434"
    ollamaSetupStatus = .unknown(model: storedOllamaModel)
    openAIAPIKey = keychainAPIKey.isEmpty ? environmentAPIKey : keychainAPIKey
    openAIModel = defaults.string(forKey: "openAIModel") ?? AIProvider.openAI.defaultModel
    grokAPIKey = keychainGrokKey.isEmpty ? environmentGrokKey : keychainGrokKey
    grokModel = defaults.string(forKey: "grokModel") ?? AIProvider.grok.defaultModel
    geminiAPIKey = keychainGeminiKey.isEmpty ? environmentGeminiKey : keychainGeminiKey
    geminiModel = defaults.string(forKey: "geminiModel") ?? AIProvider.gemini.defaultModel
    cloudAttachmentContextMode = CloudAttachmentContextMode(
      rawValue: defaults.string(forKey: "cloudAttachmentContextMode") ?? ""
    ) ?? .filenamesOnly
    pendingCloudConsentRequest = nil
    codexExecutablePath = defaults.string(forKey: "codexExecutablePath") ?? "/Applications/Codex.app/Contents/Resources/codex"
    codexSandboxMode = Self.sanitizedCodexSandboxMode(
      defaults.string(forKey: "codexSandboxMode") ?? "read-only"
    )
    stiltsCommand = defaults.string(forKey: "stiltsCommand") ?? ""
    stiltsJar = defaults.string(forKey: "stiltsJar") ?? ""
    topcatCommand = defaults.string(forKey: "topcatCommand") ?? ""
    topcatJar = defaults.string(forKey: "topcatJar") ?? ""
    aptCommand = defaults.string(forKey: "aptCommand") ?? ""
    aptPreferences = defaults.string(forKey: "aptPreferences") ?? ""
    environmentStatus = .unknown(skillRoot: skillRoot)
    registryNotice = nil
    if loadPersistedState {
      loadJobHistory()
      loadAgentState()
    }
  }

  var userCapabilities: [CapabilityEntry] {
    capabilities.userFacing
  }

  var maintainerCapabilities: [CapabilityEntry] {
    capabilities.maintainerOnly
  }

  func userCapabilities(in mode: CapabilityCatalogMode) -> [CapabilityEntry] {
    userCapabilities.filter { $0.isVisible(in: mode) }
  }

  var selectedCapability: CapabilityEntry? {
    guard let selectedCapabilityID else { return nil }
    return capabilities.first { $0.id == selectedCapabilityID }
  }

  var selectedJob: JobRecord? {
    guard let selectedJobID else { return jobs.first }
    return jobs.first { $0.id == selectedJobID }
  }

  var latestAPTJob: JobRecord? {
    jobs.first { $0.capabilityID == "apt_workbench" }
  }

  var latestDocumentStyleJob: JobRecord? {
    jobs.first {
      $0.capabilityID == "office_roundtrip.docx-style-inventory"
        || $0.capabilityID == "office_roundtrip.docx-styled-replace"
    }
  }

  var documentStyleDiff: [DOCXStyleDiff] {
    guard let documentStyleReview else { return [] }
    return documentWorkflowService.diff(
      review: documentStyleReview,
      find: docxFindText,
      replace: docxReplacementText
    )
  }

  var hasActiveJob: Bool {
    jobs.contains { $0.status == .queued || $0.status == .running }
  }

  var canCancelActiveRun: Bool {
    isRunningAgentWorkflow || hasActiveJob || isPullingOllamaModel || isRunningCodexBridge
  }

  var selectedAIModel: String {
    model(for: aiProvider)
  }

  var selectedAIAPIKey: String {
    apiKey(for: aiProvider)
  }

  var selectedAIBaseURL: String? {
    baseURL(for: aiProvider)
  }

  var externalProcessTimeoutSeconds: TimeInterval {
    ExternalProcessTimeoutPolicy.seconds(for: externalProcessTimeoutMinutes)
  }

  var selectedAIIsConfigured: Bool {
    isAIConfigured(aiProvider)
  }

  var effectiveAttachmentContextMode: CloudAttachmentContextMode {
    aiProvider.requiresAPIKey ? cloudAttachmentContextMode : .previews
  }

  var enabledAgentPlanSteps: [AgentPlanStep] {
    agentPlan?.steps.filter(\.isEnabled) ?? []
  }

  var canResumeAgentPlan: Bool {
    workflowRecoveryService.canResume(
      plan: agentPlan,
      stepExecutions: agentPlanStepExecutions,
      isRunningWorkflow: isRunningAgentWorkflow
    )
  }

  var setupChecklistItems: [SetupChecklistItem] {
    setupChecklistService.items(context: setupChecklistContext)
  }

  var setupChecklistIsReady: Bool {
    setupChecklistService.isReady(items: setupChecklistItems)
  }

  var setupRecoveryState: SetupRecoveryState? {
    setupChecklistService.recoveryState(items: setupChecklistItems)
  }

  var legacyWorkspaceNotice: String? {
    legacyWorkspacePolicy.notice(for: outputRootPath)
  }

  var outputRootRisk: FilesystemRisk {
    filesystemSafetyPolicy.assessOutputRoot(outputRootPath, inputPaths: inputPaths)
  }

  var hasNativeCatalogAlternative: Bool {
    capabilities.contains { $0.id == "catalog_workbench.crossmatch-sky" }
  }

  var radialVelocitySelectionValidation: RadialVelocitySelectionValidation? {
    guard let radialVelocityReview else { return nil }
    return radialVelocityInspectionService.validate(
      review: radialVelocityReview,
      selection: radialVelocitySelection
    )
  }

  private var radialVelocitySelection: RadialVelocitySelection {
    RadialVelocitySelection(
      timeColumn: radialVelocityTimeColumn,
      velocityColumn: radialVelocityValueColumn,
      uncertaintyColumn: radialVelocityUncertaintyColumn,
      timeSystem: radialVelocityTimeSystem,
      velocityUnit: radialVelocityUnit
    )
  }

  var photometricCalibrationValidation: PhotometricCalibrationValidation? {
    guard let photometricCalibrationReview else { return nil }
    return photometricCalibrationService.validate(
      review: photometricCalibrationReview,
      selection: photometricCalibrationSelection
    )
  }

  private var photometricCalibrationSelection: PhotometricCalibrationSelection {
    PhotometricCalibrationSelection(
      instrumentalColumn: photometricInstrumentalColumn,
      catalogColumn: photometricCatalogColumn,
      airmassColumn: photometricAirmassColumn,
      filterColumn: photometricFilterColumn,
      filterValue: photometricFilterValue,
      uncertaintyColumn: photometricUncertaintyColumn,
      colorColumn: photometricColorColumn,
      includeColorTerm: photometricIncludeColorTerm
    )
  }

  private var setupChecklistContext: SetupChecklistContext {
    SetupChecklistContext(
      environmentStatus: environmentStatus,
      outputRootPath: outputRootPath,
      userCapabilityCount: userCapabilities.count,
      ollamaModel: model(for: .ollama),
      ollamaSetupStatus: ollamaSetupStatus,
      ollamaConnectionStatus: connectionStatus(for: .ollama),
      cloudProviderReadiness: Dictionary(
        uniqueKeysWithValues: AIProvider.allCases
          .filter(\.requiresAPIKey)
          .map { ($0, connectionStatus(for: $0)) }
      ),
      configuredCloudProviders: Set(
        AIProvider.allCases
          .filter { $0.requiresAPIKey && isAIConfigured($0) }
      ),
      codexExecutablePath: codexExecutablePath
    )
  }

  var userGuideURL: URL? {
    if let bundledGuideURL = Bundle.main.resourceURL?
      .appendingPathComponent("Guides", isDirectory: true)
      .appendingPathComponent("Scientific_Workbench_User_Guide.md"),
      FileManager.default.fileExists(atPath: bundledGuideURL.path) {
      return bundledGuideURL
    }

    let sourceGuideURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Guides", isDirectory: true)
      .appendingPathComponent("Scientific_Workbench_User_Guide.md")
    guard FileManager.default.fileExists(atPath: sourceGuideURL.path) else {
      return nil
    }
    return sourceGuideURL
  }

  var workflowRecoveryState: WorkflowRecoveryState? {
    workflowRecoveryService.state(
      plan: agentPlan,
      stepExecutions: agentPlanStepExecutions,
      jobs: jobs,
      isRunningWorkflow: isRunningAgentWorkflow
    )
  }

  func execution(for step: AgentPlanStep) -> AgentPlanStepExecution? {
    agentPlanStepExecutions[step.id]
  }

  func model(for provider: AIProvider) -> String {
    switch provider {
    case .ollama:
      return ollamaModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? provider.defaultModel : ollamaModel
    case .openAI:
      return openAIModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? provider.defaultModel : openAIModel
    case .grok:
      return grokModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? provider.defaultModel : grokModel
    case .gemini:
      return geminiModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? provider.defaultModel : geminiModel
    }
  }

  func apiKey(for provider: AIProvider) -> String {
    switch provider {
    case .ollama: return ""
    case .openAI: return openAIAPIKey
    case .grok: return grokAPIKey
    case .gemini: return geminiAPIKey
    }
  }

  func isAIConfigured(_ provider: AIProvider) -> Bool {
    guard provider.requiresAPIKey else { return true }
    return !apiKey(for: provider).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  func baseURL(for provider: AIProvider) -> String? {
    switch provider {
    case .ollama:
      return ollamaBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        ? provider.defaultBaseURL
        : ollamaBaseURL
    case .openAI, .grok, .gemini:
      return provider.defaultBaseURL
    }
  }

  func connectionStatus(for provider: AIProvider) -> AIConnectionStatus {
    aiConnectionStatuses[provider] ?? .unknown
  }

  func setModel(_ model: String, for provider: AIProvider) {
    switch provider {
    case .ollama:
      ollamaModel = model
      var status = ollamaSetupStatus
      status.targetModel = self.model(for: .ollama)
      ollamaSetupStatus = status
    case .openAI: openAIModel = model
    case .grok: grokModel = model
    case .gemini: geminiModel = model
    }
    invalidateAIConnectionStatus(for: provider)
  }

  func setAPIKey(_ apiKey: String, for provider: AIProvider) {
    switch provider {
    case .ollama:
      return
    case .openAI:
      openAIAPIKey = apiKey
    case .grok:
      grokAPIKey = apiKey
    case .gemini:
      geminiAPIKey = apiKey
    }
    editedCredentialProviders.insert(provider)
    credentialSaveMessage = nil
    credentialSaveFailed = false
    invalidateAIConnectionStatus(for: provider)
  }

  func applyOllamaModelProfile(_ profile: OllamaModelProfile) {
    setModel(profile.model, for: .ollama)
    persistSettings()
  }

  func setBaseURL(_ baseURL: String, for provider: AIProvider) {
    switch provider {
    case .ollama:
      ollamaBaseURL = baseURL
    case .openAI, .grok, .gemini:
      break
    }
    invalidateAIConnectionStatus(for: provider)
  }

  func updateAgentPlanTitle(_ title: String) {
    agentPlan?.title = title
    persistAgentState()
  }

  func updateAgentPlanRationale(_ rationale: String) {
    agentPlan?.rationale = rationale
    persistAgentState()
  }

  func updateAgentPlanStep(_ stepID: AgentPlanStep.ID, mutate: (inout AgentPlanStep) -> Void) {
    guard var plan = agentPlan,
          let index = plan.steps.firstIndex(where: { $0.id == stepID }) else { return }
    mutate(&plan.steps[index])
    agentPlan = plan
    for staleStep in plan.steps[index...] {
      agentPlanStepExecutions[staleStep.id] = nil
    }
    persistAgentState()
  }

  @discardableResult
  func exportAgentPlan() -> String? {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return nil }
    guard let agentPlan else {
      agentStatusMessage = "Create a plan before exporting."
      return nil
    }

    let url = exportedPlansDirectory
      .appendingPathComponent(
        "\(DateFormatters.runFolder.string(from: Date()))_agent_plan_\(UUID().uuidString.lowercased()).json"
      )
    do {
      try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
      )
      let payload = ExportedAgentPlanPayload(
        version: ExportedAgentPlanPayload.currentVersion,
        generatedAt: Date(),
        outputRootPath: outputRootPath,
        inputPaths: inputPaths.map(redactSecrets),
        aiProvider: aiProvider,
        aiModel: selectedAIModel,
        mode: agentMode,
        autoRun: agentAutoRun,
        plan: redactedPlan(agentPlan)
      )
      let data = try JSONEncoder.scientificWorkbench.encode(payload)
      try data.write(to: url, options: [.atomic])
      lastExportedPlanPath = url.path
      agentStatusMessage = "Exported plan to \(url.lastPathComponent)."
      return url.path
    } catch {
      agentStatusMessage = "Could not export plan: \(error.localizedDescription)"
      return nil
    }
  }

  func revealExportedPlans() {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return }
    try? FileManager.default.createDirectory(
      at: exportedPlansDirectory,
      withIntermediateDirectories: true
    )
    NSWorkspace.shared.open(exportedPlansDirectory)
  }

  @discardableResult
  func exportConfiguration(to path: String? = nil, revealInFinder: Bool = true) -> String? {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return nil }
    let approvedPath: String?
    if let path {
      guard let destination = approvedExportDestination(path) else { return nil }
      approvedPath = destination.path
    } else {
      approvedPath = nil
    }
    let snapshot = WorkbenchConfigurationSnapshot(
      generatedAt: Date(),
      appName: "Scientific Workbench",
      skillRootPath: skillRootPath,
      outputRootPath: outputRootPath,
      pythonExecutable: pythonExecutable,
      aiProvider: aiProvider,
      ollamaModel: ollamaModel,
      ollamaBaseURL: ollamaBaseURL,
      openAIModel: openAIModel,
      grokModel: grokModel,
      geminiModel: geminiModel,
      cloudAttachmentContextMode: cloudAttachmentContextMode,
      codexExecutablePath: codexExecutablePath,
      codexSandboxMode: codexSandboxMode,
      externalProcessTimeoutMinutes: externalProcessTimeoutMinutes
    )

    do {
      let url = try configurationService.export(
        snapshot: snapshot,
        to: approvedPath,
        configurationDirectory: configurationDirectory,
        redact: redactSecrets
      )
      agentStatusMessage = "Exported configuration to \(url.lastPathComponent)."
      if revealInFinder {
        NSWorkspace.shared.activateFileViewerSelecting([url])
      }
      return url.path
    } catch {
      agentStatusMessage = "Could not export configuration: \(redactSecrets(error.localizedDescription))"
      return nil
    }
  }

  func chooseConfigurationFile() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    panel.allowedContentTypes = [.json]
    panel.prompt = "Import"
    panel.message = "Choose a Scientific Workbench configuration export."
    if panel.runModal() == .OK, let url = panel.url {
      importConfiguration(from: url.path)
    }
  }

  @discardableResult
  func importConfiguration(from path: String) -> Bool {
    do {
      let payload = try configurationService.importPayload(from: path)

      aiProvider = payload.aiProvider
      ollamaModel = nonEmpty(payload.ollamaModel, fallback: AIProvider.ollama.defaultModel)
      ollamaBaseURL = nonEmpty(payload.ollamaBaseURL, fallback: AIProvider.ollama.defaultBaseURL ?? "http://localhost:11434")
      openAIModel = nonEmpty(payload.openAIModel, fallback: AIProvider.openAI.defaultModel)
      grokModel = nonEmpty(payload.grokModel, fallback: AIProvider.grok.defaultModel)
      geminiModel = nonEmpty(payload.geminiModel, fallback: AIProvider.gemini.defaultModel)
      cloudAttachmentContextMode = payload.cloudAttachmentContextMode ?? .filenamesOnly
      if let importedTimeoutMinutes = payload.externalProcessTimeoutMinutes {
        externalProcessTimeoutMinutes = ExternalProcessTimeoutPolicy.normalized(minutes: importedTimeoutMinutes)
      }
      ollamaSetupStatus = .unknown(model: model(for: .ollama))
      aiConnectionStatuses = Dictionary(
        uniqueKeysWithValues: AIProvider.allCases.map { ($0, .unknown) }
      )
      persistSettings(saveSecrets: false)
      agentStatusMessage = "Imported portable preferences from \(URL(fileURLWithPath: path).lastPathComponent). Local paths, executables, the Codex sandbox, and API keys were not imported or changed."
      return true
    } catch {
      agentStatusMessage = "Could not import configuration: \(redactSecrets(error.localizedDescription))"
      return false
    }
  }

  func revealOutputRoot() {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return }
    let outputRootURL = URL(fileURLWithPath: outputRootPath, isDirectory: true)
    try? FileManager.default.createDirectory(
      at: outputRootURL,
      withIntermediateDirectories: true
    )
    NSWorkspace.shared.open(outputRootURL)
  }

  func openUserGuide() {
    guard let userGuideURL else {
      agentStatusMessage = "Could not find the bundled Scientific Workbench guide."
      return
    }
    openMarkdownDocument(userGuideURL)
  }

  @discardableResult
  func exportSupportBundle(revealInFinder: Bool = true) -> String? {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return nil }
    let generatedAt = Date()
    do {
      let payload = supportBundlePayload(generatedAt: generatedAt)
      let result = try supportBundleService.export(
        generatedAt: generatedAt,
        supportBundlesDirectory: supportBundlesDirectory,
        payload: payload,
        latestWorkflowSummaryPath: lastWorkflowSummaryPath,
        redact: redactSecrets
      )

      agentStatusMessage = "Exported support bundle to \(result.bundleURL.lastPathComponent)."
      if revealInFinder {
        NSWorkspace.shared.activateFileViewerSelecting([result.bundleURL])
      }
      return result.bundleURL.path
    } catch {
      agentStatusMessage = "Could not export support bundle: \(redactSecrets(error.localizedDescription))"
      return nil
    }
  }

  @discardableResult
  func exportJobSupportBundle(_ job: JobRecord, revealInFinder: Bool = true) -> String? {
    guard ensureOutputRootWriteApproved(inputPaths: job.requestInputPaths) else { return nil }
    do {
      let result = try supportBundleService.exportJob(
        job: job,
        redactedJob: redactedJob(job),
        supportBundlesDirectory: supportBundlesDirectory,
        redact: redactSecrets
      )
      agentStatusMessage = "Exported support bundle for \(job.capabilityLabel)."
      if revealInFinder {
        NSWorkspace.shared.activateFileViewerSelecting([result.bundleURL])
      }
      return result.bundleURL.path
    } catch {
      agentStatusMessage = "Could not export job support bundle: \(redactSecrets(error.localizedDescription))"
      return nil
    }
  }

  func chooseAgentPlanFile() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    panel.allowedContentTypes = [.json]
    panel.prompt = "Import"
    panel.message = "Choose an exported Scientific Workbench agent plan."
    if panel.runModal() == .OK, let url = panel.url {
      importAgentPlan(from: url.path)
    }
  }

  @discardableResult
  func importAgentPlan(from path: String) -> AgentPlan? {
    do {
      let data = try Data(contentsOf: URL(fileURLWithPath: path))
      let payload = try JSONDecoder.scientificWorkbench.decode(ExportedAgentPlanPayload.self, from: data)
      guard (1...ExportedAgentPlanPayload.currentVersion).contains(payload.version) else {
        throw PersistenceStoreError.unsupportedVersion(
          kind: "exported agent plan",
          version: payload.version
        )
      }
      let identifierRecovery = deduplicatedPersistedPlan(payload.plan)
      var importedPlan = redactedPlan(identifierRecovery.plan)
      let sanitization = sanitizedAgentPlanForCurrentRegistry(importedPlan)
      importedPlan = sanitization.plan

      let restoredInputs = payload.inputPaths.filter { FileManager.default.fileExists(atPath: $0) }
      if !restoredInputs.isEmpty {
        inputPaths = restoredInputs
      }
      agentPlan = importedPlan
      agentPlanStepExecutions = [:]
      agentMode = .workflow
      agentAutoRun = false
      selectedSection = .agent
      let missingText = sanitization.disabledMissing == 0
        ? "" : " Disabled \(sanitization.disabledMissing) missing step\(sanitization.disabledMissing == 1 ? "" : "s")."
      let restrictedText = sanitization.disabledRestricted == 0
        ? "" : " Disabled \(sanitization.disabledRestricted) restricted step\(sanitization.disabledRestricted == 1 ? "" : "s")."
      let hiddenText = sanitization.omittedHidden == 0
        ? "" : " Omitted \(sanitization.omittedHidden) non-planner step\(sanitization.omittedHidden == 1 ? "" : "s")."
      let inputText: String
      if payload.inputPaths.isEmpty {
        inputText = " No inputs were stored in the plan."
      } else if restoredInputs.count == payload.inputPaths.count {
        inputText = " Restored \(restoredInputs.count) input path\(restoredInputs.count == 1 ? "" : "s")."
      } else {
        inputText = " Restored \(restoredInputs.count)/\(payload.inputPaths.count) input path\(payload.inputPaths.count == 1 ? "" : "s"); attach any missing inputs before running."
      }
      let migrationText = payload.version == ExportedAgentPlanPayload.currentVersion
        ? ""
        : " Migrated plan schema \(payload.version) to \(ExportedAgentPlanPayload.currentVersion)."
      let duplicateText = identifierRecovery.removed == 0
        ? ""
        : " Removed \(identifierRecovery.removed) duplicate step identifier\(identifierRecovery.removed == 1 ? "" : "s")."
      agentStatusMessage = "Imported plan '\(importedPlan.title)' with \(importedPlan.steps.count) step\(importedPlan.steps.count == 1 ? "" : "s").\(migrationText)\(duplicateText)\(missingText)\(restrictedText)\(hiddenText)\(inputText)"
      persistAgentState()
      return importedPlan
    } catch {
      agentStatusMessage = "Could not import plan: \(error.localizedDescription)"
      return nil
    }
  }

  func dryRunAgentPlan() -> String {
    let result = workflowDryRunService.buildReport(
      request: WorkflowDryRunService.Request(
        plan: agentPlan,
        capabilities: capabilities,
        inputPaths: inputPaths,
        pythonExecutable: pythonExecutable,
        timeoutSeconds: externalProcessTimeoutSeconds,
        skillRootPath: skillRootPath,
        makeRunDirectory: { self.makeRunDirectory(for: $0) },
        resolveRawArguments: { rawArguments, runDirectory, previousRunDirectory, completedRunDirectories in
          self.resolveAgentRawArguments(
            rawArguments,
            runDirectory: runDirectory,
            previousRunDirectory: previousRunDirectory,
            completedRunDirectories: completedRunDirectories
          )
        },
        redact: redactSecrets
      )
    )
    agentStatusMessage = result.statusMessage
    return result.report
  }

  @discardableResult
  func retryJob(_ job: JobRecord) async -> String {
    guard !hasActiveJob else {
      agentStatusMessage = "Wait for the active job to finish before retrying."
      return agentStatusMessage
    }
    guard job.status != .queued && job.status != .running else {
      agentStatusMessage = "This job is still active and cannot be retried yet."
      return agentStatusMessage
    }
    guard let capability = capabilities.first(where: { $0.id == job.capabilityID }) else {
      agentStatusMessage = "Cannot retry \(job.capabilityLabel): capability is not available in the current registry."
      return agentStatusMessage
    }

    selectedSection = .jobs
    agentStatusMessage = "Retrying \(job.capabilityLabel)..."
    let retried = await run(
      capability: capability,
      rawArguments: job.requestRawArguments,
      inputPathsOverride: job.requestInputPaths,
      retryOfJobID: job.id
    )
    if let retried {
      agentStatusMessage = "Retry finished for \(job.capabilityLabel): \(retried.status.title)."
    } else {
      agentStatusMessage = "Could not retry \(job.capabilityLabel)."
    }
    return agentStatusMessage
  }

  func testAIConnection(_ provider: AIProvider? = nil) async {
    let provider = provider ?? aiProvider
    loadSavedSecretIfNeeded(for: provider)
    persistSettings()
    let request = aiConnectionRequest(for: provider)
    let startingStatus = aiConnectionService.startingStatus(for: request)
    aiConnectionStatuses[provider] = startingStatus
    guard startingStatus.state == .testing else { return }
    let result = await aiConnectionService.test(request)
    guard aiConnectionRequest(for: provider).hasSameConnectionTarget(as: request) else {
      invalidateAIConnectionStatus(for: provider)
      return
    }
    aiConnectionStatuses[provider] = result
  }

  func refreshOllamaSetup() async {
    isCheckingOllamaSetup = true
    let status = await ollamaSetupService.status(
      baseURL: baseURL(for: .ollama),
      model: model(for: .ollama)
    )
    ollamaSetupStatus = status
    isCheckingOllamaSetup = false
  }

  func openOllamaDownloadPage() {
    NSWorkspace.shared.open(URL(string: "https://ollama.com/download/mac")!)
  }

  func openOllamaApp() {
    let appURL = URL(fileURLWithPath: "/Applications/Ollama.app")
    if FileManager.default.fileExists(atPath: appURL.path) {
      NSWorkspace.shared.open(appURL)
    } else {
      openOllamaDownloadPage()
    }
  }

  func pullSelectedOllamaModel() async {
    guard !isPullingOllamaModel else { return }
    guard !hasActiveJob, !isRunningAgentWorkflow, !isRunningCodexBridge else {
      ollamaSetupStatus.message = "Wait for the active Scientific Workbench operation to finish or cancel it before downloading a model."
      return
    }
    isCancellationRequested = false
    isPullingOllamaModel = true
    let model = model(for: .ollama)
    let task = Task { try await ollamaSetupService.pullModel(model) }
    ollamaPullTask = task
    defer {
      ollamaPullTask = nil
      isPullingOllamaModel = false
      isCancellationRequested = false
    }
    do {
      let result = try await task.value
      ollamaSetupStatus.message = result.succeeded
        ? "\(model) downloaded. Checking local AI setup again..."
        : "Ollama pull exited with \(result.exitCode): \(result.userMessage)"
      await refreshOllamaSetup()
    } catch {
      if error is CancellationError || isOllamaCancellation(error) {
        agentStatusMessage = "Ollama model download cancelled."
      }
      ollamaSetupStatus = OllamaSetupStatus(
        cliPath: ollamaSetupStatus.cliPath,
        serverReachable: ollamaSetupStatus.serverReachable,
        installedModels: ollamaSetupStatus.installedModels,
        targetModel: model,
        message: error.localizedDescription,
        checkedAt: Date()
      )
    }
  }

  func startupRefresh() async {
    await reloadRegistry()
    await refreshEnvironment()
  }

  func runLaunchAutomationIfNeeded() async {
    guard !handledLaunchAutomation else { return }
    handledLaunchAutomation = true

    let options = LaunchAutomationOptions.parse(CommandLine.arguments)
    await runLaunchAutomation(options)
  }

  func runLaunchAutomation(_ options: LaunchAutomationOptions) async {
    guard options.shouldRun else { return }
    let previousRestrictedStepOverride = enableRestrictedStepsForLaunchAutomation
    enableRestrictedStepsForLaunchAutomation = options.enableRestrictedSteps
    defer { enableRestrictedStepsForLaunchAutomation = previousRestrictedStepOverride }

    selectedSection = .agent
    if let outputRootPath = options.outputRootPath {
      self.outputRootPath = outputRootPath
    }
    if let mode = options.mode {
      agentMode = mode
    }
    if let codexSandboxMode = options.codexSandboxMode {
      self.codexSandboxMode = Self.sanitizedCodexSandboxMode(codexSandboxMode)
    }
    if let aiProvider = options.aiProvider {
      self.aiProvider = aiProvider
    }
    if let aiModel = options.aiModel {
      setModel(aiModel, for: self.aiProvider)
    }
    if let aiBaseURL = options.aiBaseURL {
      setBaseURL(aiBaseURL, for: self.aiProvider)
    }
    forceLocalPlanner = options.forceLocalPlanner
    agentAutoRun = options.autoRun
    for path in options.inputPaths {
      addInputPath(path)
    }
    if let prompt = options.prompt {
      agentPrompt = prompt
    } else if !options.inputPaths.isEmpty {
      agentPrompt = "Analyze the attached inputs and produce a safe scientific workflow without editing originals."
    }

    await submitAgentChatPrompt()

    if let transcriptPath = options.transcriptPath {
      writeLaunchTranscript(to: transcriptPath)
    }

    if options.exitAfterRun {
      exit(0)
    }
    forceLocalPlanner = false
  }

  @discardableResult
  func persistSettings(saveSecrets: Bool = false) -> Bool {
    codexSandboxMode = Self.sanitizedCodexSandboxMode(codexSandboxMode)
    externalProcessTimeoutMinutes = ExternalProcessTimeoutPolicy.normalized(
      minutes: externalProcessTimeoutMinutes
    )
    defaults.set(skillRootPath, forKey: "skillRootPath")
    defaults.set(outputRootPath, forKey: "outputRootPath")
    defaults.set(pythonExecutable, forKey: "pythonExecutable")
    defaults.set(externalProcessTimeoutMinutes, forKey: "externalProcessTimeoutMinutes")
    defaults.set(aiProvider.rawValue, forKey: "aiProvider")
    defaults.set(ollamaModel, forKey: "ollamaModel")
    defaults.set(ollamaBaseURL, forKey: "ollamaBaseURL")
    defaults.set(openAIModel, forKey: "openAIModel")
    defaults.set(grokModel, forKey: "grokModel")
    defaults.set(geminiModel, forKey: "geminiModel")
    defaults.set(cloudAttachmentContextMode.rawValue, forKey: "cloudAttachmentContextMode")
    defaults.set(codexExecutablePath, forKey: "codexExecutablePath")
    defaults.set(codexSandboxMode, forKey: "codexSandboxMode")
    defaults.set(stiltsCommand, forKey: "stiltsCommand")
    defaults.set(stiltsJar, forKey: "stiltsJar")
    defaults.set(topcatCommand, forKey: "topcatCommand")
    defaults.set(topcatJar, forKey: "topcatJar")
    defaults.set(aptCommand, forKey: "aptCommand")
    defaults.set(aptPreferences, forKey: "aptPreferences")
    if saveSecrets {
      let edited = AIProvider.allCases.filter { editedCredentialProviders.contains($0) }
      var failures: [AIProvider] = []
      for provider in edited {
        switch credentialStore.saveKey(apiKey(for: provider), for: provider) {
        case .success:
          editedCredentialProviders.remove(provider)
        case .failure:
          failures.append(provider)
        }
      }
      credentialSaveFailed = !failures.isEmpty
      if failures.isEmpty {
        credentialSaveMessage = edited.isEmpty
          ? "Connection settings saved. Stored API keys were unchanged."
          : "Connection settings and edited API keys saved to Keychain."
      } else {
        let names = failures.map(\.title).joined(separator: ", ")
        credentialSaveMessage = "Could not save API keys for \(names) to Keychain. Unsaved edits remain only in this app session; retry Save Connections before closing the app."
      }
      return failures.isEmpty
    }
    return true
  }

  func reloadJobHistory() {
    loadJobHistory()
  }

  func clearJobHistory() {
    jobs = []
    selectedJobID = nil
    persistJobHistory()
  }

  func revealJobHistory() {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return }
    let url = jobHistoryURL
    try? FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    NSWorkspace.shared.activateFileViewerSelecting([url])
  }

  func revealPersistenceRecoveryArchive() {
    guard let lastPersistenceRecoveryArchivePath else { return }
    NSWorkspace.shared.activateFileViewerSelecting([
      URL(fileURLWithPath: lastPersistenceRecoveryArchivePath)
    ])
  }

  func reloadRegistry() async {
    do {
      let result = try registryLoader.loadWithDiagnostics(skillRoot: skillRootPath)
      capabilities = result.entries
      registryError = nil
      revalidateRestoredAgentPlanIfNeeded()
      if result.unavailableOptionalRoots.isEmpty {
        registryNotice = nil
      } else {
        let modules = result.unavailableOptionalRoots
          .map { $0.role.defaultDirectoryName }
          .sorted()
          .joined(separator: ", ")
        registryNotice = "Core capabilities loaded. Optional skill modules unavailable: \(modules)."
      }
      if let selectedCapabilityID,
         capabilities.contains(where: { $0.id == selectedCapabilityID }) {
        return
      } else {
        selectedCapabilityID = userCapabilities.first?.id
      }
    } catch {
      registryError = error.localizedDescription
      registryNotice = nil
      capabilities = []
    }
  }

  func refreshEnvironment() async {
    persistSettings()
    environmentStatus = await environmentService.refresh(
      skillRoot: skillRootPath,
      pythonExecutable: pythonExecutable
    )
  }

  func refreshOptionalAstronomyBackends() async {
    persistSettings()
    isCheckingOptionalAstronomyBackends = true
    defer { isCheckingOptionalAstronomyBackends = false }
    optionalAstronomyBackendStatus = await optionalAstronomyBackendService.refresh(
      skillRoot: skillRootPath,
      pythonExecutable: pythonExecutable,
      stiltsCommand: stiltsCommand,
      stiltsJar: stiltsJar,
      topcatCommand: topcatCommand,
      topcatJar: topcatJar,
      aptCommand: aptCommand,
      aptPreferences: aptPreferences
    )
  }

  @discardableResult
  func runAPTPreflight() async -> JobRecord? {
    persistSettings()
    guard let capability = capabilities.first(where: { $0.id == "apt_workbench" }) else {
      registryError = "Capability apt_workbench is not available in the current registry."
      return nil
    }
    let runDirectory = makeRunDirectory(for: capability)
    var arguments = ["preflight"]
    appendRawOption("--apt-command", value: aptCommand, to: &arguments)
    appendRawOption("--apt-preferences", value: aptPreferences, to: &arguments)
    arguments += [
      "--summary-json",
      URL(fileURLWithPath: runDirectory).appendingPathComponent("summary.json").path,
    ]
    let job = await run(
      capability: capability,
      rawArguments: arguments.map(ShellWords.quote).joined(separator: " "),
      inputPathsOverride: [],
      runDirectoryOverride: runDirectory
    )
    await refreshOptionalAstronomyBackends()
    return job
  }

  func openOptionalCapability(_ capabilityID: String) {
    guard let capability = capabilities.first(where: { $0.id == capabilityID }) else {
      registryError = "Capability \(capabilityID) is not available in the current registry."
      return
    }
    if let mode = capability.catalogMode {
      capabilityCatalogMode = mode
    }
    selectedCapabilityID = capabilityID
    selectedSection = .capabilities
  }

  func useNativeCatalogAlternative() {
    openOptionalCapability(
      optionalAstronomyBackendStatus.nativeAlternativeCapabilityID
        ?? "catalog_workbench.crossmatch-sky"
    )
  }

  func useNativeAPTAlternative(_ capabilityID: String = "inspect_fits") {
    let candidates = [capabilityID]
      + optionalAstronomyBackendStatus.aptNativeAlternativeCapabilityIDs
      + ["inspect_fits", "photometry_noise_budget"]
    guard let available = candidates.first(where: { candidate in
      capabilities.contains { $0.id == candidate }
    }) else {
      registryError = "No native APT alternative is available in the current registry."
      return
    }
    openOptionalCapability(available)
  }

  func showLatestAPTResults() {
    guard let job = latestAPTJob else { return }
    selectedJobID = job.id
    selectedSection = .results
  }

  func revealLatestAPTRun() {
    guard let job = latestAPTJob else { return }
    revealRunDirectory(job)
  }

  func resetDocumentWorkflow() {
    documentStyleReview = nil
    documentStyleError = nil
    docxReplacementConfirmed = false
  }

  func reviewDOCXStyles() async {
    documentStyleError = nil
    docxReplacementConfirmed = false
    guard let sourcePath = inputPaths.first else {
      documentStyleReview = nil
      return
    }
    guard let capability = capabilities.first(where: { $0.id == "office_roundtrip.docx-style-inventory" }) else {
      documentStyleError = "DOCX style inventory is not available in the current registry."
      return
    }
    isReviewingDocumentStyles = true
    defer { isReviewingDocumentStyles = false }
    guard let runDirectory = prepareValidatedRunDirectory(
      for: capability,
      originalInputPaths: [sourcePath]
    ) else {
      documentStyleReview = nil
      documentStyleError = agentStatusMessage
      return
    }
    do {
      let staged = try documentWorkflowService.stageDOCX(
        sourcePath: sourcePath,
        runDirectory: runDirectory
      )
      let runURL = URL(fileURLWithPath: runDirectory)
      var arguments = [
        staged.stagedPath,
        "--output-csv", runURL.appendingPathComponent("tables/style_inventory.csv").path,
        "--report-md", runURL.appendingPathComponent("reports/style_inventory.md").path,
        "--summary-json", runURL.appendingPathComponent("summary.json").path,
      ]
      appendDOCXStyleFlags(to: &arguments)
      let job = await run(
        capability: capability,
        rawArguments: arguments.map(ShellWords.quote).joined(separator: " "),
        inputPathsOverride: [staged.stagedPath],
        selectJobs: false,
        runDirectoryOverride: runDirectory
      )
      guard documentWorkflowService.originalIsUnchanged(staged) else {
        documentStyleReview = nil
        documentStyleError = DocumentWorkflowError.originalChanged.localizedDescription
        return
      }
      guard job?.status == .succeeded else {
        documentStyleReview = nil
        documentStyleError = job?.message ?? "DOCX style inventory did not complete."
        return
      }
      documentStyleReview = try documentWorkflowService.parseDOCXInventory(
        summaryPath: runURL.appendingPathComponent("summary.json").path,
        originalFingerprint: staged.originalFingerprint
      )
    } catch {
      documentStyleReview = nil
      documentStyleError = error.localizedDescription
    }
  }

  func showLatestDocumentStyleResults() {
    guard let job = latestDocumentStyleJob else { return }
    selectedJobID = job.id
    selectedSection = .results
  }

  @discardableResult
  func runReviewedDOCXReplacement(capability: CapabilityEntry) async -> JobRecord? {
    documentStyleError = nil
    do {
      try documentWorkflowService.validateReplacementApproval(
        confirmed: docxReplacementConfirmed,
        diff: documentStyleDiff
      )
    } catch {
      documentStyleError = error.localizedDescription
      return nil
    }
    guard let sourcePath = inputPaths.first else {
      documentStyleError = "Choose one DOCX file."
      return nil
    }
    guard let runDirectory = prepareValidatedRunDirectory(
      for: capability,
      originalInputPaths: [sourcePath]
    ) else {
      documentStyleError = agentStatusMessage
      return nil
    }
    do {
      let staged = try documentWorkflowService.stageDOCX(
        sourcePath: sourcePath,
        runDirectory: runDirectory
      )
      let runURL = URL(fileURLWithPath: runDirectory)
      var arguments = [
        staged.stagedPath,
        runURL.appendingPathComponent("artifacts/edited_copy.docx").path,
        "--find", docxFindText,
        "--replace", docxReplacementText,
        "--require-confirmation",
        "--confirmation-id", "scientific-workbench:\(UUID().uuidString)",
        "--diff-json", runURL.appendingPathComponent("previews/style_diff.json").path,
        "--summary-json", runURL.appendingPathComponent("summary.json").path,
        "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
      ]
      appendDOCXStyleFlags(to: &arguments)
      let job = await run(
        capability: capability,
        rawArguments: arguments.map(ShellWords.quote).joined(separator: " "),
        inputPathsOverride: [staged.stagedPath],
        runDirectoryOverride: runDirectory
      )
      guard documentWorkflowService.originalIsUnchanged(staged) else {
        documentStyleError = DocumentWorkflowError.originalChanged.localizedDescription
        return job
      }
      docxReplacementConfirmed = false
      return job
    } catch {
      documentStyleError = error.localizedDescription
      return nil
    }
  }

  func resetKeynoteWorkflow() {
    keynotePreflightReview = nil
    keynoteWorkflowError = nil
    keynoteExportConfirmed = false
  }

  @discardableResult
  func runKeynotePreflight(capability: CapabilityEntry) async -> JobRecord? {
    keynoteWorkflowError = nil
    keynoteExportConfirmed = false
    guard let sourcePath = inputPaths.first else {
      keynotePreflightReview = nil
      return nil
    }
    isCheckingKeynote = true
    defer { isCheckingKeynote = false }
    guard let runDirectory = prepareValidatedRunDirectory(
      for: capability,
      originalInputPaths: [sourcePath]
    ) else {
      keynoteWorkflowError = agentStatusMessage
      return nil
    }
    do {
      let staged = try documentWorkflowService.stagePresentation(
        sourcePath: sourcePath,
        runDirectory: runDirectory
      )
      let runURL = URL(fileURLWithPath: runDirectory)
      let arguments = [
        staged.stagedPath,
        runURL.appendingPathComponent("previews/keynote_export.pdf").path,
        "--preflight-only",
        "--log-txt", runURL.appendingPathComponent("logs/keynote_preflight.txt").path,
        "--summary-json", runURL.appendingPathComponent("summary.json").path,
      ]
      let job = await run(
        capability: capability,
        rawArguments: arguments.map(ShellWords.quote).joined(separator: " "),
        inputPathsOverride: [staged.stagedPath],
        selectJobs: false,
        runDirectoryOverride: runDirectory
      )
      guard documentWorkflowService.originalIsUnchanged(staged) else {
        keynotePreflightReview = nil
        keynoteWorkflowError = DocumentWorkflowError.originalChanged.localizedDescription
        return job
      }
      keynotePreflightReview = try documentWorkflowService.parseKeynotePreflight(
        summaryPath: runURL.appendingPathComponent("summary.json").path,
        originalFingerprint: staged.originalFingerprint
      )
      return job
    } catch {
      keynotePreflightReview = nil
      keynoteWorkflowError = error.localizedDescription
      return nil
    }
  }

  @discardableResult
  func runConfirmedKeynoteExport(capability: CapabilityEntry) async -> JobRecord? {
    keynoteWorkflowError = nil
    do {
      try documentWorkflowService.validateKeynoteExportApproval(
        confirmed: keynoteExportConfirmed,
        preflight: keynotePreflightReview
      )
    } catch {
      keynoteWorkflowError = error.localizedDescription
      return nil
    }
    guard let sourcePath = inputPaths.first else {
      keynoteWorkflowError = "Choose one presentation."
      return nil
    }
    guard let runDirectory = prepareValidatedRunDirectory(
      for: capability,
      originalInputPaths: [sourcePath]
    ) else {
      keynoteWorkflowError = agentStatusMessage
      return nil
    }
    isExportingKeynote = true
    defer { isExportingKeynote = false }
    do {
      let staged = try documentWorkflowService.stagePresentation(
        sourcePath: sourcePath,
        runDirectory: runDirectory
      )
      let runURL = URL(fileURLWithPath: runDirectory)
      let arguments = [
        staged.stagedPath,
        runURL.appendingPathComponent("previews/keynote_export.pdf").path,
        "--require-confirmation",
        "--confirmation-id", "scientific-workbench:\(UUID().uuidString)",
        "--log-txt", runURL.appendingPathComponent("logs/keynote_export.txt").path,
        "--summary-json", runURL.appendingPathComponent("summary.json").path,
        "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
      ]
      let job = await run(
        capability: capability,
        rawArguments: arguments.map(ShellWords.quote).joined(separator: " "),
        inputPathsOverride: [staged.stagedPath],
        runDirectoryOverride: runDirectory
      )
      guard documentWorkflowService.originalIsUnchanged(staged) else {
        keynoteWorkflowError = DocumentWorkflowError.originalChanged.localizedDescription
        return job
      }
      keynoteExportConfirmed = false
      return job
    } catch {
      keynoteWorkflowError = error.localizedDescription
      return nil
    }
  }

  private func appendDOCXStyleFlags(to arguments: inout [String]) {
    if docxRequireBold { arguments.append("--require-bold") }
    if docxRequireItalic { arguments.append("--require-italic") }
    if docxRequireUnderline { arguments.append("--require-underline") }
  }

  func reviewRadialVelocityInput() {
    radialVelocityReviewError = nil
    guard let path = inputPaths.first else {
      radialVelocityReview = nil
      return
    }
    isReviewingRadialVelocityInput = true
    defer { isReviewingRadialVelocityInput = false }
    do {
      let review = try radialVelocityInspectionService.inspect(path: path)
      radialVelocityReview = review
      radialVelocityTimeColumn = review.recommendedTimeColumn
      radialVelocityValueColumn = review.recommendedVelocityColumn
      radialVelocityUncertaintyColumn = review.recommendedUncertaintyColumn
      radialVelocityTimeSystem = review.inferredTimeSystem ?? .jd
      radialVelocityUnit = review.inferredVelocityUnit ?? .kilometersPerSecond
    } catch {
      radialVelocityReview = nil
      radialVelocityReviewError = error.localizedDescription
    }
  }

  @discardableResult
  func runReviewedRadialVelocityInspection(
    capability: CapabilityEntry,
    selectJobs: Bool = true
  ) async -> JobRecord? {
    guard let review = radialVelocityReview else {
      radialVelocityReviewError = "Inspect and review the RV columns before running."
      return nil
    }
    let validation = radialVelocityInspectionService.validate(
      review: review,
      selection: radialVelocitySelection
    )
    guard validation.canRun else {
      radialVelocityReviewError = validation.findings.first
      return nil
    }
    guard let runDirectory = prepareValidatedRunDirectory(
      for: capability,
      originalInputPaths: [review.inputPath]
    ) else {
      radialVelocityReviewError = agentStatusMessage
      return nil
    }
    do {
      let staged = try radialVelocityInspectionService.stage(
        review: review,
        selection: radialVelocitySelection,
        runDirectory: runDirectory
      )
      return await run(
        capability: capability,
        rawArguments: "",
        inputPathsOverride: [staged.velsPath],
        selectJobs: selectJobs,
        runDirectoryOverride: runDirectory
      )
    } catch {
      radialVelocityReviewError = error.localizedDescription
      return nil
    }
  }

  func reviewPhotometricCalibrationInput() {
    photometricCalibrationError = nil
    guard let path = inputPaths.first else {
      photometricCalibrationReview = nil
      return
    }
    isReviewingPhotometricCalibration = true
    defer { isReviewingPhotometricCalibration = false }
    do {
      let review = try photometricCalibrationService.inspect(path: path)
      photometricCalibrationReview = review
      photometricInstrumentalColumn = review.recommendedInstrumentalColumn
      photometricCatalogColumn = review.recommendedCatalogColumn
      photometricAirmassColumn = review.recommendedAirmassColumn
      photometricFilterColumn = review.recommendedFilterColumn
      photometricUncertaintyColumn = review.recommendedUncertaintyColumn
      photometricColorColumn = review.recommendedColorColumn
      photometricIncludeColorTerm = false
      refreshPhotometricFilterValues()
    } catch {
      photometricCalibrationReview = nil
      photometricCalibrationError = error.localizedDescription
    }
  }

  func refreshPhotometricFilterValues() {
    guard let review = photometricCalibrationReview else {
      photometricFilterValues = []
      photometricFilterValue = nil
      return
    }
    photometricFilterValues = photometricCalibrationService.filterValues(
      review: review,
      filterColumn: photometricFilterColumn
    )
    if photometricFilterValues.count == 1 {
      photometricFilterValue = photometricFilterValues.first
    } else if !photometricFilterValues.contains(photometricFilterValue ?? "") {
      photometricFilterValue = nil
    }
  }

  @discardableResult
  func runReviewedPhotometricCalibration(
    capability: CapabilityEntry,
    selectJobs: Bool = true
  ) async -> JobRecord? {
    guard let review = photometricCalibrationReview else {
      photometricCalibrationError = "Inspect and review the calibration columns before fitting."
      return nil
    }
    let validation = photometricCalibrationService.validate(
      review: review,
      selection: photometricCalibrationSelection
    )
    guard validation.canRun else {
      photometricCalibrationError = validation.findings.first
      return nil
    }
    guard let runDirectory = prepareValidatedRunDirectory(
      for: capability,
      originalInputPaths: [review.inputPath]
    ) else {
      photometricCalibrationError = agentStatusMessage
      return nil
    }
    do {
      let staged = try photometricCalibrationService.stage(
        review: review,
        selection: photometricCalibrationSelection,
        runDirectory: runDirectory
      )
      return await run(
        capability: capability,
        rawArguments: "",
        inputPathsOverride: [staged.tablePath],
        selectJobs: selectJobs,
        runDirectoryOverride: runDirectory
      )
    } catch {
      photometricCalibrationError = error.localizedDescription
      return nil
    }
  }

  func addInputPath(_ path: String) {
    guard !inputPaths.contains(path) else { return }
    inputPaths.append(path)
  }

  func removeInputPath(_ path: String) {
    inputPaths.removeAll { $0 == path }
  }

  func clearInputs() {
    inputPaths.removeAll()
  }

  func chooseInputFiles() {
    chooseInputs(canChooseFiles: true, canChooseDirectories: false)
  }

  func chooseInputFolders() {
    chooseInputs(canChooseFiles: false, canChooseDirectories: true)
  }

  func runSelectedCapability(rawArguments: String) async {
    guard let selectedCapability else { return }
    await run(capability: selectedCapability, rawArguments: rawArguments)
  }

  func cancelActiveRun() {
    guard canCancelActiveRun else { return }
    isCancellationRequested = true
    agentStatusMessage = "Cancelling the active run..."
    ollamaPullTask?.cancel()
    codexBridgeTask?.cancel()
    Task {
      await runner.cancelAll()
    }
  }

  @discardableResult
  func planAgentWorkflow(prompt promptOverride: String? = nil) async -> AgentPlan? {
    let prompt = (promptOverride ?? agentPrompt).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !prompt.isEmpty else {
      agentStatusMessage = "Write a prompt first."
      return nil
    }
    guard !capabilities.isEmpty else {
      agentStatusMessage = "The capability registry is not loaded yet."
      return nil
    }

    if !forceLocalPlanner {
      loadSavedSecretIfNeeded(for: aiProvider)
    }
    persistSettings()
    isPlanningAgentWorkflow = true
    let plan: AgentPlan
    if forceLocalPlanner {
      agentStatusMessage = "Planning with deterministic local planner."
      plan = await agentPlanner.deterministicPlan(
        prompt: prompt,
        inputPaths: inputPaths,
        capabilities: capabilities,
        skillRoot: skillRootPath,
        pythonExecutable: pythonExecutable
      )
    } else {
      agentStatusMessage = selectedAIIsConfigured
        ? "Planning with \(aiProvider.title)."
        : "Planning locally because no \(aiProvider.title) API key is configured."
      let outboundPrompt = aiProvider.requiresAPIKey && selectedAIIsConfigured
        ? redactingConfiguredCloudSecrets(in: prompt)
        : prompt
      plan = await agentPlanner.plan(
        prompt: outboundPrompt,
        inputPaths: inputPaths,
        capabilities: capabilities,
        provider: aiProvider,
        apiKey: selectedAIAPIKey,
        model: selectedAIModel,
        baseURL: selectedAIBaseURL,
        attachmentContextMode: effectiveAttachmentContextMode,
        skillRoot: skillRootPath,
        pythonExecutable: pythonExecutable
      )
    }
    let safePlan = launchAutomationPlanWithRestrictedStepsEnabledIfNeeded(redactedPlan(plan))
    agentPlan = safePlan
    agentPlanStepExecutions = [:]
    agentStatusMessage = "Planned \(safePlan.steps.count) step\(safePlan.steps.count == 1 ? "" : "s") using \(safePlan.source.title)."
    persistAgentState()
    isPlanningAgentWorkflow = false
    return safePlan
  }

  func submitAgentChatPrompt() async {
    let prompt = agentPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !prompt.isEmpty else { return }
    guard pendingCloudAgentSubmission == nil else { return }

    let resolvedMode = agentRoutingService.resolvedMode(
      configuredMode: agentMode,
      prompt: prompt,
      hasInputs: !inputPaths.isEmpty
    )
    if !forceLocalPlanner {
      loadSavedSecretIfNeeded(for: aiProvider)
    }
    if let request = cloudConsentRequest(for: resolvedMode, prompt: prompt), requiresCloudConsent(request) {
      pendingCloudAgentSubmission = PendingCloudAgentSubmission(
        prompt: prompt,
        resolvedMode: resolvedMode,
        request: request
      )
      pendingCloudConsentRequest = request
      agentStatusMessage = "Review what will be sent to \(request.provider.title) before continuing."
      return
    }

    await performAgentSubmission(prompt: prompt, resolvedMode: resolvedMode)
  }

  func confirmPendingCloudRequest(
    approvalScope: CloudConsentApprovalScope = .requestOnly
  ) async {
    guard let pendingCloudAgentSubmission,
          pendingCloudConsentRequest?.id == pendingCloudAgentSubmission.request.id else {
      pendingCloudConsentRequest = nil
      self.pendingCloudAgentSubmission = nil
      return
    }

    let currentPrompt = agentPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !currentPrompt.isEmpty else {
      cancelPendingCloudRequest(
        message: "The cloud request changed because the draft is now empty. Nothing was sent."
      )
      return
    }
    let currentResolvedMode = agentRoutingService.resolvedMode(
      configuredMode: agentMode,
      prompt: currentPrompt,
      hasInputs: !inputPaths.isEmpty
    )
    if !forceLocalPlanner {
      loadSavedSecretIfNeeded(for: aiProvider)
    }
    guard let refreshedRequest = cloudConsentRequest(
      for: currentResolvedMode,
      prompt: currentPrompt
    ) else {
      cancelPendingCloudRequest(
        message: "The provider or routing context changed. Nothing was sent; press Send to evaluate the current local/cloud route again."
      )
      return
    }

    guard refreshedRequest.fingerprint == pendingCloudAgentSubmission.request.fingerprint else {
      self.pendingCloudAgentSubmission = PendingCloudAgentSubmission(
        prompt: currentPrompt,
        resolvedMode: currentResolvedMode,
        request: refreshedRequest
      )
      pendingCloudConsentRequest = refreshedRequest
      agentStatusMessage = "The cloud request changed. Nothing was sent; review the updated provider, model, context, and privacy scope."
      return
    }

    if approvalScope == .appSession {
      rememberedCloudConsentScopes.insert(refreshedRequest.sessionScope)
    }
    self.pendingCloudAgentSubmission = nil
    pendingCloudConsentRequest = nil
    await performAgentSubmission(
      prompt: currentPrompt,
      resolvedMode: currentResolvedMode
    )
  }

  func cancelPendingCloudRequest() {
    cancelPendingCloudRequest(
      message: "Cloud request cancelled. Nothing was sent; your message remains in the composer."
    )
  }

  private func cancelPendingCloudRequest(message: String) {
    pendingCloudAgentSubmission = nil
    pendingCloudConsentRequest = nil
    agentStatusMessage = message
  }

  private func performAgentSubmission(prompt: String, resolvedMode: AgentRunMode) async {

    agentChatMessages.append(AgentChatMessage(role: .user, text: prompt))
    if agentPrompt.trimmingCharacters(in: .whitespacesAndNewlines) == prompt {
      agentPrompt = ""
    }

    switch resolvedMode {
    case .chat:
      let response = await answerChatPrompt(prompt)
      agentChatMessages.append(AgentChatMessage(role: .assistant, text: response))
    case .workflow:
      guard let plan = await planAgentWorkflow(prompt: prompt) else {
        agentChatMessages.append(AgentChatMessage(role: .assistant, text: agentStatusMessage))
        return
      }
      agentChatMessages.append(AgentChatMessage(role: .assistant, text: agentRoutingService.chatSummary(for: plan)))
      if agentAutoRun {
        let result = await runAgentPlan()
        agentChatMessages.append(AgentChatMessage(role: .assistant, text: result))
      }
    case .codex:
      let response = await runCodexPrompt(prompt)
      agentChatMessages.append(AgentChatMessage(role: .assistant, text: response))
    case .auto:
      break
    }
  }

  private func cloudConsentRequest(
    for resolvedMode: AgentRunMode,
    prompt: String
  ) -> CloudConsentRequest? {
    guard !forceLocalPlanner, selectedAIIsConfigured else { return nil }
    let purpose: CloudRequestPurpose
    switch resolvedMode {
    case .chat:
      purpose = .chat
    case .workflow:
      purpose = .workflowPlanning
    case .auto, .codex:
      return nil
    }

    let outboundPrompt = redactingConfiguredCloudSecrets(in: prompt)
    let history = purpose == .chat
      ? agentChatMessages.suffix(12).map { message in
        AgentChatMessage(
          id: message.id,
          role: message.role,
          text: redactingConfiguredCloudSecrets(in: message.text),
          createdAt: message.createdAt
        )
      }
      : []
    let recoveryContext = purpose == .chat
      ? workflowRecoveryPromptContext().map { redactingConfiguredCloudSecrets(in: $0) }
      : nil
    let trimmedModel = selectedAIModel.trimmingCharacters(in: .whitespacesAndNewlines)
    let outboundModel = trimmedModel.isEmpty ? aiProvider.defaultModel : trimmedModel
    return agentRoutingService.cloudConsentRequest(
      provider: aiProvider,
      model: outboundModel,
      purpose: purpose,
      prompt: outboundPrompt,
      history: history,
      inputPaths: inputPaths,
      attachmentContextMode: effectiveAttachmentContextMode,
      workflowRecoveryContext: recoveryContext,
      capabilities: capabilities
    )
  }

  private func requiresCloudConsent(_ request: CloudConsentRequest) -> Bool {
    !rememberedCloudConsentScopes.contains(request.sessionScope)
  }

  @discardableResult
  func runAgentPlan() async -> String {
    await runAgentPlan(resumeFromPreviousSuccesses: false)
  }

  @discardableResult
  func resumeAgentPlanFromLastSuccess() async -> String {
    await runAgentPlan(resumeFromPreviousSuccesses: true)
  }

  @discardableResult
  private func runAgentPlan(resumeFromPreviousSuccesses: Bool) async -> String {
    guard let plan = agentPlan else {
      agentStatusMessage = "Create a plan before running."
      return agentStatusMessage
    }
    guard !isRunningAgentWorkflow else { return "A workflow is already running." }
    guard !hasActiveJob, !isPullingOllamaModel, !isRunningCodexBridge else {
      agentStatusMessage = "Wait for the active Scientific Workbench operation to finish or cancel it first."
      return agentStatusMessage
    }
    let enabledSteps = plan.steps.enumerated().filter { $0.element.isEnabled }
    guard !enabledSteps.isEmpty else {
      agentStatusMessage = "Enable at least one plan step before running."
      return agentStatusMessage
    }

    if !resumeFromPreviousSuccesses {
      agentPlanStepExecutions = [:]
      persistAgentState()
    }

    isRunningAgentWorkflow = true
    isCancellationRequested = false
    lastWorkflowSummaryPath = nil
    selectedSection = .jobs
    return await workflowExecutionCoordinator.run(
      request: WorkflowExecutionCoordinator.Request(
        plan: plan,
        capabilities: capabilities,
        inputPaths: inputPaths,
        existingStepExecutions: agentPlanStepExecutions,
        resumeFromPreviousSuccesses: resumeFromPreviousSuccesses,
        allowRestrictedLocalAutomationSteps: enableRestrictedStepsForLaunchAutomation
      ),
      callbacks: WorkflowExecutionCoordinator.Callbacks(
        isCancellationRequested: { self.isCancellationRequested },
        setCancellationRequested: { self.isCancellationRequested = $0 },
        setRunningWorkflow: { self.isRunningAgentWorkflow = $0 },
        setStatusMessage: { self.agentStatusMessage = $0 },
        makeRunDirectory: { self.makeRunDirectory(for: $0) },
        resolveRawArguments: { rawArguments, runDirectory, previousRunDirectory, completedRunDirectories in
          self.resolveAgentRawArguments(
            rawArguments,
            runDirectory: runDirectory,
            previousRunDirectory: previousRunDirectory,
            completedRunDirectories: completedRunDirectories
          )
        },
        runStep: { request in
          await self.run(
            capability: request.capability,
            rawArguments: request.rawArguments,
            inputPathsOverride: request.inputPaths,
            selectJobs: false,
            runDirectoryOverride: request.runDirectory,
            allowDuringAgentWorkflow: true
          )
        },
        recordStepExecution: { stepID, execution in
          self.agentPlanStepExecutions[stepID] = execution
        },
        setSelectedJobID: { self.selectedJobID = $0 },
        writeWorkflowSummary: { enabledSteps, jobIDs, status, startedAt, finishedAt in
          _ = self.writeWorkflowSummary(
            plan: plan,
            enabledSteps: enabledSteps,
            jobIDs: jobIDs,
            status: status,
            startedAt: startedAt,
            finishedAt: finishedAt
          )
        },
        persistAgentState: { self.persistAgentState() }
      )
    )
  }

  func chooseDirectory(assignTo keyPath: ReferenceWritableKeyPath<WorkbenchStore, String>) {
    let panel = NSOpenPanel()
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    if panel.runModal() == .OK, let url = panel.url {
      self[keyPath: keyPath] = url.path
      persistSettings()
    }
  }

  func chooseFile(assignTo keyPath: ReferenceWritableKeyPath<WorkbenchStore, String>) {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    if panel.runModal() == .OK, let url = panel.url {
      self[keyPath: keyPath] = url.path
      persistSettings()
    }
  }

  func choosePythonExecutable() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    if panel.runModal() == .OK, let url = panel.url {
      pythonExecutable = url.path
      persistSettings()
    }
  }

  private func chooseInputs(canChooseFiles: Bool, canChooseDirectories: Bool) {
    let panel = NSOpenPanel()
    panel.canChooseFiles = canChooseFiles
    panel.canChooseDirectories = canChooseDirectories
    panel.allowsMultipleSelection = true
    panel.prompt = "Add"
    panel.message = canChooseDirectories ? "Choose folders to use as inputs." : "Choose files to use as inputs."
    if panel.runModal() == .OK {
      for url in panel.urls {
        addInputPath(url.path)
      }
    }
  }

  @discardableResult
  func run(
    capability: CapabilityEntry,
    rawArguments: String,
    inputPathsOverride: [String]? = nil,
    selectJobs: Bool = true,
    runDirectoryOverride: String? = nil,
    retryOfJobID: UUID? = nil,
    allowDuringAgentWorkflow: Bool = false
  ) async -> JobRecord? {
    guard allowDuringAgentWorkflow || (!isRunningAgentWorkflow && !hasActiveJob) else {
      agentStatusMessage = "Wait for the active Scientific Workbench run to finish or cancel it first."
      return nil
    }
    guard !isPullingOllamaModel, !isRunningCodexBridge else {
      agentStatusMessage = "Wait for the active Scientific Workbench operation to finish or cancel it first."
      return nil
    }
    let ownsCancellationState = !allowDuringAgentWorkflow
    if ownsCancellationState {
      isCancellationRequested = false
    }
    let requestInputPaths = inputPathsOverride ?? inputPaths
    guard ensureOutputRootWriteApproved(inputPaths: requestInputPaths) else { return nil }
    let runDirectory = runDirectoryOverride ?? makeRunDirectory(for: capability)
    let allowedRunRoot = legacyWorkspacePolicy.runRoot(
      for: capability.id,
      preferredOutputRoot: outputRootPath
    )
    do {
      try filesystemSafetyPolicy.validateRunDirectory(
        runDirectory,
        inputPaths: requestInputPaths,
        allowedRoots: [allowedRunRoot]
      )
    } catch {
      agentStatusMessage = redactSecrets(error.localizedDescription)
      return nil
    }
    var job = JobRecord(capability: capability, runDirectory: runDirectory)
    job.requestInputPaths = requestInputPaths
    job.requestRawArguments = rawArguments
    job.retryOfJobID = retryOfJobID
    jobs.insert(job, at: 0)
    selectedJobID = job.id
    persistJobHistory()
    if selectJobs {
      selectedSection = .jobs
    }

    do {
      try FileManager.default.createDirectory(
        atPath: runDirectory,
        withIntermediateDirectories: true
      )
      let effectiveRawArguments = try legacyReportProjectStagingService.stagePopulateProjectIfNeeded(
        capabilityID: capability.id,
        rawArguments: rawArguments,
        inputPaths: requestInputPaths,
        runDirectory: runDirectory
      )
      let request = RunRequest(
        capabilityID: capability.id,
        inputPaths: requestInputPaths,
        outputDirectory: runDirectory,
        rawArguments: effectiveRawArguments
      )
      let builder = CapabilityCommandBuilder(
        pythonExecutable: pythonExecutable,
        timeoutSeconds: externalProcessTimeoutSeconds
      )
      let command = try builder.build(
        capability: capability,
        request: request,
        skillRoot: skillRootPath
      )

      job.status = .running
      job.command = redactSecrets(command.pretty)
      job.startedAt = Date()
      replace(job)

      let result = try await runner.run(command)
      let stdoutEnvelope = envelopeParser.parse(result.stdout)
      job.stdout = redactSecrets(result.stdout)
      job.stderr = redactSecrets(result.stderr)
      job.exitCode = result.exitCode
      job.finishedAt = result.finishedAt
      runBundleService.writeCaptureFiles(
        runDirectory: runDirectory,
        command: job.command,
        stdout: job.stdout,
        stderr: job.stderr
      )
      runBundleService.hydrate(
        &job,
        fallbackEnvelope: stdoutEnvelope,
        redact: redactSecrets
      )
      if isCancellationRequested {
        job.status = .cancelled
        job.message = "Run cancelled by user."
      } else {
        job.status = JobStatus.resolved(
          exitCode: result.exitCode,
          envelopeStatus: job.parsedStatus,
          appStatus: job.appStatus
        )
      }
      if result.exitCode != 0, job.status != .cancelled {
        job.message = redactSecrets(result.stderr.isEmpty ? "Process exited with \(result.exitCode)." : result.stderr)
      }
      if job.message == nil, let firstError = job.structuredErrors.first {
        job.message = firstError.message
      }
      runBundleService.writeNextStepsIfMissing(for: job)
      runBundleService.hydrate(
        &job,
        fallbackEnvelope: stdoutEnvelope,
        redact: redactSecrets
      )
      replace(job)
      if ownsCancellationState {
        isCancellationRequested = false
      }
      return job
    } catch {
      if isCancellationRequested || error is CancellationError || isProcessRunnerCancellation(error) {
        job.status = .cancelled
        job.message = "Run cancelled by user."
      } else if case .timedOut? = error as? ProcessRunnerError {
        job.status = .timedOut
        job.message = redactSecrets(error.localizedDescription)
      } else {
        job.status = .blocked
        job.message = redactSecrets(error.localizedDescription)
      }
      job.finishedAt = Date()
      runBundleService.writeCaptureFiles(
        runDirectory: runDirectory,
        command: job.command,
        stdout: job.stdout,
        stderr: job.message ?? ""
      )
      runBundleService.hydrate(&job, redact: redactSecrets)
      runBundleService.writeNextStepsIfMissing(for: job)
      runBundleService.hydrate(&job, redact: redactSecrets)
      replace(job)
      if ownsCancellationState {
        isCancellationRequested = false
      }
      return job
    }
  }

  @discardableResult
  func runGuided(
    capability: CapabilityEntry,
    inputPathsOverride: [String]? = nil,
    selectJobs: Bool = true,
    arguments: (URL) -> [String]
  ) async -> JobRecord? {
    let runDirectory = makeRunDirectory(for: capability)
    let runURL = URL(fileURLWithPath: runDirectory, isDirectory: true)
    let rawArguments = arguments(runURL)
      .map(ShellWords.quote)
      .joined(separator: " ")
    return await run(
      capability: capability,
      rawArguments: rawArguments,
      inputPathsOverride: inputPathsOverride,
      selectJobs: selectJobs,
      runDirectoryOverride: runDirectory
    )
  }

  private func isProcessRunnerCancellation(_ error: Error) -> Bool {
    if case .cancelled? = error as? ProcessRunnerError {
      return true
    }
    return false
  }

  func openArtifact(_ artifact: Artifact) {
    NSWorkspace.shared.open(artifact.url)
  }

  func revealArtifact(_ artifact: Artifact) {
    NSWorkspace.shared.activateFileViewerSelecting([artifact.url])
  }

  func redactedPreviewText(_ text: String) -> String {
    redactSecrets(text)
  }

  func refreshRunBundle(for job: JobRecord) {
    var refreshed = job
    runBundleService.hydrate(&refreshed, redact: redactSecrets)
    replace(refreshed)
  }

  func openWorkflowSummary() {
    guard let lastWorkflowSummaryPath else { return }
    openMarkdownDocument(URL(fileURLWithPath: lastWorkflowSummaryPath))
  }

  func revealRunDirectory(_ job: JobRecord) {
    NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: job.runDirectory)])
  }

  private func makeRunDirectory(for capability: CapabilityEntry) -> String {
    let runRoot = legacyWorkspacePolicy.runRoot(
      for: capability.id,
      preferredOutputRoot: outputRootPath
    )
    return runDirectoryFactory.makePath(root: runRoot, capabilityID: capability.id)
  }

  private func prepareValidatedRunDirectory(
    for capability: CapabilityEntry,
    originalInputPaths: [String]
  ) -> String? {
    guard ensureOutputRootWriteApproved(inputPaths: originalInputPaths) else { return nil }
    let runDirectory = makeRunDirectory(for: capability)
    let allowedRunRoot = legacyWorkspacePolicy.runRoot(
      for: capability.id,
      preferredOutputRoot: outputRootPath
    )
    do {
      try filesystemSafetyPolicy.validateRunDirectory(
        runDirectory,
        inputPaths: originalInputPaths,
        allowedRoots: [allowedRunRoot]
      )
      try FileManager.default.createDirectory(
        atPath: runDirectory,
        withIntermediateDirectories: true
      )
      return runDirectory
    } catch {
      agentStatusMessage = redactSecrets(error.localizedDescription)
      return nil
    }
  }

  private func ensureOutputRootWriteApproved(inputPaths: [String]) -> Bool {
    switch filesystemSafetyPolicy.assessOutputRoot(outputRootPath, inputPaths: inputPaths) {
    case .safe:
      return true
    case .requiresConfirmation(let reason):
      guard outputRootRiskApprovalIsCurrent(inputPaths: inputPaths) else {
        agentStatusMessage = "Output blocked until you confirm the path in Settings: \(reason)"
        return false
      }
      return true
    case .blocked(let reason):
      agentStatusMessage = "Unsafe output root: \(reason)"
      return false
    }
  }

  private func outputRootWriteIsApproved(inputPaths: [String]) -> Bool {
    switch filesystemSafetyPolicy.assessOutputRoot(outputRootPath, inputPaths: inputPaths) {
    case .safe:
      return true
    case .requiresConfirmation:
      return outputRootRiskApprovalIsCurrent(inputPaths: inputPaths)
    case .blocked:
      return false
    }
  }

  private func outputRootRiskApprovalIsCurrent(inputPaths: [String]) -> Bool {
    outputRootRiskApproved
      && outputRootRiskApprovalFingerprint == currentOutputRootRiskApprovalFingerprint(
        inputPaths: inputPaths
      )
  }

  private func invalidateOutputRootRiskApprovalIfContextChanged() {
    guard outputRootRiskApproved else { return }
    guard !outputRootRiskApprovalIsCurrent(inputPaths: inputPaths) else { return }
    outputRootRiskApproved = false
  }

  private func currentOutputRootRiskApprovalFingerprint(inputPaths: [String]) -> String {
    let root = canonicalFilesystemURL(outputRootPath).path
    let inputs = Set(inputPaths.map { canonicalFilesystemURL($0).path }).sorted()
    return ([root] + inputs).joined(separator: "\u{1F}")
  }

  private func appendRawOption(_ option: String, value: String, to arguments: inout [String]) {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    arguments += [option, trimmed]
  }

  private func replace(_ job: JobRecord) {
    guard let index = jobs.firstIndex(where: { $0.id == job.id }) else { return }
    jobs[index] = job
    persistJobHistory()
  }

  private var jobHistoryURL: URL {
    URL(fileURLWithPath: outputRootPath)
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("jobs.json")
  }

  private var exportedPlansDirectory: URL {
    URL(fileURLWithPath: outputRootPath)
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("plans", isDirectory: true)
  }

  private var configurationDirectory: URL {
    URL(fileURLWithPath: outputRootPath)
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("configuration", isDirectory: true)
  }

  private var supportBundlesDirectory: URL {
    URL(fileURLWithPath: outputRootPath)
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("support", isDirectory: true)
  }

  private var agentStateURL: URL {
    URL(fileURLWithPath: outputRootPath)
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("agent_state.json")
  }

  private func loadJobHistory() {
    guard outputRootReadIsAllowed else { return }
    let url = jobHistoryURL
    do {
      guard let result = try jobHistoryStore.loadRecovering(from: url) else { return }
      if result.diagnostics.requiresRewrite {
        try preserveAndRewriteJobHistory(result, at: url)
      }
      jobs = result.jobs.map { loadedJob in
        var refreshed = loadedJob
        runBundleService.hydrate(&refreshed, redact: redactSecrets)
        return refreshed
      }
      selectedJobID = jobs.first?.id
    } catch let error as PersistenceStoreError where error.canRecoverByArchiving {
      recoverUnreadableJobHistory(at: url, error: error)
    } catch {
      registryError = "Could not load job history: \(error.localizedDescription)"
    }
  }

  private func loadAgentState() {
    guard outputRootReadIsAllowed else { return }
    let url = agentStateURL
    do {
      guard let result = try agentStateStore.loadRecovering(from: url) else { return }
      if result.diagnostics.requiresRewrite {
        try preserveAndRewriteAgentState(result, at: url)
      }
      let snapshot = result.snapshot
      let restoredStepExecutions = Dictionary(
        uniqueKeysWithValues: snapshot.stepExecutions.map { ($0.stepID, $0) }
      )
      lastWorkflowSummaryPath = snapshot.lastWorkflowSummaryPath
      if shouldRestoreAgentPlan(snapshot.agentPlan, stepExecutions: restoredStepExecutions) {
        agentPlan = snapshot.agentPlan
        agentPlanStepExecutions = restoredStepExecutions
      } else {
        agentPlan = nil
        agentPlanStepExecutions = [:]
        if snapshot.agentPlan != nil {
          agentStatusMessage = "Ready. Previous workflow finished; open the latest summary if you need its results."
          persistAgentState()
          return
        }
      }
      if !snapshot.agentStatusMessage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        agentStatusMessage = snapshot.agentStatusMessage
      }
    } catch let error as PersistenceStoreError where error.canRecoverByArchiving {
      recoverUnreadableAgentState(at: url, error: error)
    } catch {
      registryError = "Could not load agent state: \(error.localizedDescription)"
    }
  }

  private func preserveAndRewriteJobHistory(
    _ result: JobHistoryLoadResult,
    at url: URL
  ) throws {
    guard outputRootWriteIsApproved(inputPaths: inputPaths) else {
      throw PersistenceStoreError.recoveryWriteNotApproved(url.path)
    }
    let archiveURL = try persistenceRecoveryArchive.preserveOriginal(
      at: url,
      reason: result.diagnostics.sourceVersion == JobHistoryStore.currentVersion
        ? "recovery"
        : "migration-v\(result.diagnostics.sourceVersion)"
    )
    try jobHistoryStore.persist(jobs: result.jobs, to: url)
    recordPersistenceRecovery(
      "Job history: \(result.diagnostics.summary). Original preserved at \(archiveURL.path).",
      archiveURL: archiveURL
    )
  }

  private func preserveAndRewriteAgentState(
    _ result: AgentStateLoadResult,
    at url: URL
  ) throws {
    guard outputRootWriteIsApproved(inputPaths: inputPaths) else {
      throw PersistenceStoreError.recoveryWriteNotApproved(url.path)
    }
    let archiveURL = try persistenceRecoveryArchive.preserveOriginal(
      at: url,
      reason: result.diagnostics.sourceVersion == AgentStateStore.currentVersion
        ? "recovery"
        : "migration-v\(result.diagnostics.sourceVersion)"
    )
    try agentStateStore.persist(snapshot: result.snapshot, to: url)
    recordPersistenceRecovery(
      "Agent state: \(result.diagnostics.summary). Original preserved at \(archiveURL.path).",
      archiveURL: archiveURL
    )
  }

  private func recoverUnreadableJobHistory(at url: URL, error: PersistenceStoreError) {
    guard outputRootWriteIsApproved(inputPaths: inputPaths) else {
      registryError = "Could not recover job history: \(error.localizedDescription)"
      return
    }
    do {
      let archiveURL = try persistenceRecoveryArchive.preserveOriginal(at: url, reason: "corrupt")
      try jobHistoryStore.persist(jobs: [], to: url)
      jobs = []
      selectedJobID = nil
      recordPersistenceRecovery(
        "Job history was unreadable. The exact original was preserved at \(archiveURL.path); Scientific Workbench started a clean schema-\(JobHistoryStore.currentVersion) history.",
        archiveURL: archiveURL
      )
    } catch {
      registryError = "Could not recover job history without risking the original: \(error.localizedDescription)"
    }
  }

  private func recoverUnreadableAgentState(at url: URL, error: PersistenceStoreError) {
    guard outputRootWriteIsApproved(inputPaths: inputPaths) else {
      registryError = "Could not recover agent state: \(error.localizedDescription)"
      return
    }
    do {
      let archiveURL = try persistenceRecoveryArchive.preserveOriginal(at: url, reason: "corrupt")
      let cleanSnapshot = AgentStateSnapshot(
        agentPlan: nil,
        stepExecutions: [],
        lastWorkflowSummaryPath: nil,
        agentStatusMessage: "Recovered from unreadable persisted workflow state. Review the preserved original if needed."
      )
      try agentStateStore.persist(snapshot: cleanSnapshot, to: url)
      agentPlan = nil
      agentPlanStepExecutions = [:]
      lastWorkflowSummaryPath = nil
      agentStatusMessage = cleanSnapshot.agentStatusMessage
      recordPersistenceRecovery(
        "Agent state was unreadable. The exact original was preserved at \(archiveURL.path); Scientific Workbench started clean schema-\(AgentStateStore.currentVersion) workflow state.",
        archiveURL: archiveURL
      )
    } catch {
      registryError = "Could not recover agent state without risking the original: \(error.localizedDescription)"
    }
  }

  private func recordPersistenceRecovery(_ message: String, archiveURL: URL) {
    if let existing = persistenceRecoveryNotice, !existing.isEmpty {
      persistenceRecoveryNotice = existing + "\n" + message
    } else {
      persistenceRecoveryNotice = message
    }
    lastPersistenceRecoveryArchivePath = archiveURL.path
  }

  private func shouldRestoreAgentPlan(
    _ plan: AgentPlan?,
    stepExecutions: [AgentPlanStep.ID: AgentPlanStepExecution]
  ) -> Bool {
    guard let plan else { return false }
    let enabledSteps = plan.steps.filter(\.isEnabled)
    guard !enabledSteps.isEmpty else { return false }
    guard !stepExecutions.isEmpty else { return true }
    return enabledSteps.contains { step in
      stepExecutions[step.id]?.status != .succeeded
    }
  }

  private var outputRootReadIsAllowed: Bool {
    if case .blocked = filesystemSafetyPolicy.assessOutputRoot(outputRootPath, inputPaths: inputPaths) {
      return false
    }
    return true
  }

  private func sanitizedAgentPlanForCurrentRegistry(
    _ plan: AgentPlan
  ) -> (plan: AgentPlan, disabledMissing: Int, disabledRestricted: Int, omittedHidden: Int) {
    let capabilitiesByID = Dictionary(uniqueKeysWithValues: capabilities.map { ($0.id, $0) })
    guard !capabilitiesByID.isEmpty else { return (plan, 0, 0, 0) }
    var sanitized = plan
    var disabledMissing = 0
    var disabledRestricted = 0
    var omittedHidden = 0
    sanitized.steps = plan.steps.compactMap { step in
      guard let capability = capabilitiesByID[step.capabilityID] else {
        var disabled = step
        disabled.isEnabled = false
        if !disabled.summary.localizedCaseInsensitiveContains("missing capability") {
          disabled.summary += " Missing capability in current registry."
        }
        disabledMissing += 1
        return disabled
      }
      guard !capability.isMaintainerOnly,
            capability.appReadiness.isPlannerVisible || plan.source == .local else {
        omittedHidden += 1
        return nil
      }
      guard capability.requiresPlannerConfirmation else { return step }
      var restricted = step
      if restricted.isEnabled { disabledRestricted += 1 }
      restricted.isEnabled = false
      if !restricted.summary.localizedCaseInsensitiveContains("enable it explicitly") {
        restricted.summary += " Review this \(capability.workflowMode.rawValue) / \(capability.appReadiness.rawValue) step and enable it explicitly."
      }
      return restricted
    }
    return (sanitized, disabledMissing, disabledRestricted, omittedHidden)
  }

  private func revalidateRestoredAgentPlanIfNeeded() {
    guard let agentPlan else { return }
    let sanitization = sanitizedAgentPlanForCurrentRegistry(agentPlan)
    guard sanitization.plan != agentPlan else { return }
    self.agentPlan = sanitization.plan
    let remainingStepIDs = Set(sanitization.plan.steps.map(\.id))
    agentPlanStepExecutions = agentPlanStepExecutions.filter { remainingStepIDs.contains($0.key) }
    agentAutoRun = false
    agentStatusMessage = "Revalidated restored plan against the installed capability policy; restricted steps require fresh review."
    persistAgentState()
  }

  private func persistAgentState() {
    guard outputRootWriteIsApproved(inputPaths: inputPaths) else { return }
    let url = agentStateURL
    do {
      try agentStateStore.persist(
        snapshot: AgentStateSnapshot(
        agentPlan: agentPlan.map { redactedPlan($0) },
        stepExecutions: Array(agentPlanStepExecutions.values),
        lastWorkflowSummaryPath: lastWorkflowSummaryPath,
        agentStatusMessage: redactSecrets(agentStatusMessage)
        ),
        to: url
      )
    } catch {
      registryError = "Could not save agent state: \(error.localizedDescription)"
    }
  }

  private func persistJobHistory() {
    guard outputRootWriteIsApproved(inputPaths: inputPaths) else { return }
    let url = jobHistoryURL
    do {
      try jobHistoryStore.persist(jobs: jobs, to: url)
    } catch {
      registryError = "Could not save job history: \(error.localizedDescription)"
    }
  }

  private func launchAutomationPlanWithRestrictedStepsEnabledIfNeeded(_ plan: AgentPlan) -> AgentPlan {
    guard enableRestrictedStepsForLaunchAutomation else { return plan }
    let capabilitiesByID = Dictionary(uniqueKeysWithValues: capabilities.map { ($0.id, $0) })
    var updatedPlan = plan
    updatedPlan.steps = plan.steps.map { step in
      guard let capability = capabilitiesByID[step.capabilityID],
            !capability.isMaintainerOnly,
            capability.appReadiness.isPlannerVisible || plan.source == .local else { return step }
      var enabledStep = step
      enabledStep.isEnabled = true
      return enabledStep
    }
    return updatedPlan
  }

  private func openMarkdownDocument(_ url: URL) {
    let textEditURL = URL(fileURLWithPath: "/System/Applications/TextEdit.app", isDirectory: true)
    let configuration = NSWorkspace.OpenConfiguration()
    if FileManager.default.fileExists(atPath: textEditURL.path) {
      NSWorkspace.shared.open([url], withApplicationAt: textEditURL, configuration: configuration) { _, error in
        if error != nil {
          NSWorkspace.shared.activateFileViewerSelecting([url])
        }
      }
    } else {
      NSWorkspace.shared.activateFileViewerSelecting([url])
    }
  }

  private func answerChatPrompt(_ prompt: String) async -> String {
    loadSavedSecretIfNeeded(for: aiProvider)
    let trimmedKey = selectedAIAPIKey.trimmingCharacters(in: .whitespacesAndNewlines)
    if selectedAIIsConfigured {
      do {
        let outboundHistory = agentChatMessages.dropLast().suffix(12).map { message in
          AgentChatMessage(
            id: message.id,
            role: message.role,
            text: redactingConfiguredCloudSecrets(in: message.text),
            createdAt: message.createdAt
          )
        }
        return try await cloudAIClient.respond(
          prompt: redactingConfiguredCloudSecrets(in: prompt),
          history: outboundHistory,
          inputPaths: inputPaths,
          workflowRecoveryContext: workflowRecoveryPromptContext()
            .map { redactingConfiguredCloudSecrets(in: $0) },
          attachmentContextMode: effectiveAttachmentContextMode,
          provider: aiProvider,
          apiKey: trimmedKey,
          model: selectedAIModel,
          baseURL: selectedAIBaseURL
        )
      } catch {
        let providerError = "\(aiProvider.title) chat failed: \(aiConnectionService.failureMessage(error, request: aiConnectionRequest(for: aiProvider)))"
        return "\(providerError)\n\nCodex was not run automatically. Switch Mode to Codex and press Send only if you want to spend Codex usage on this prompt."
      }
    }

    return "I can plan and run local workflows without a cloud API key. Choose Ollama for local AI chat, add a cloud key only if you want one, or switch Mode to Codex explicitly for coding-agent tasks."
  }

  private func workflowRecoveryPromptContext() -> String? {
    guard let recovery = workflowRecoveryState else { return nil }
    let stoppedJob = recovery.stoppedJobID.flatMap { jobID in
      jobs.first { $0.id == jobID }
    }
    return agentRoutingService.workflowRecoveryPromptContext(
      recovery: recovery,
      stoppedJob: stoppedJob,
      lastWorkflowSummaryPath: lastWorkflowSummaryPath,
      attachmentContextMode: effectiveAttachmentContextMode,
      redact: redactSecrets
    )
  }

  private func nonEmpty(_ value: String, fallback: String) -> String {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? fallback : value
  }

  private static func sanitizedCodexSandboxMode(_ value: String) -> String {
    value == "workspace-write" ? "workspace-write" : "read-only"
  }

  private func runCodexPrompt(_ prompt: String) async -> String {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else {
      return agentStatusMessage
    }
    guard !isRunningCodexBridge, !hasActiveJob, !isRunningAgentWorkflow, !isPullingOllamaModel else {
      return "A Scientific Workbench operation is already active. Cancel it or wait for it to finish."
    }
    isCancellationRequested = false
    isRunningCodexBridge = true
    agentStatusMessage = "Running Codex bridge. This can take a few minutes and does not create Jobs until it returns."
    persistSettings()
    try? FileManager.default.createDirectory(
      atPath: outputRootPath,
      withIntermediateDirectories: true
    )
    let task = Task {
      try await CodexBridge(executablePath: codexExecutablePath).run(
        prompt: prompt,
        inputPaths: inputPaths,
        outputRootPath: outputRootPath,
        sandboxMode: codexSandboxMode
      )
    }
    codexBridgeTask = task
    defer {
      codexBridgeTask = nil
      isRunningCodexBridge = false
      isCancellationRequested = false
    }
    do {
      let response = try await task.value
      agentStatusMessage = "Codex bridge finished."
      return response
    } catch {
      agentStatusMessage = (error is CancellationError || isCodexBridgeCancellation(error))
        ? "Codex bridge cancelled."
        : "Codex bridge failed."
      return redactSecrets(error.localizedDescription)
    }
  }

  private func isOllamaCancellation(_ error: Error) -> Bool {
    if case .cancelled? = error as? OllamaSetupError {
      return true
    }
    return false
  }

  private func isCodexBridgeCancellation(_ error: Error) -> Bool {
    if case .cancelled? = error as? CodexBridgeError {
      return true
    }
    return false
  }

  private func resolveAgentRawArguments(
    _ rawArguments: String,
    runDirectory: String?,
    previousRunDirectory: String?,
    completedRunDirectories: [String: String] = [:]
  ) -> String {
    guard !rawArguments.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return rawArguments
    }

    let currentRun = runDirectory ?? outputRootPath
    var replacements: [String: String] = [
      "{outputRoot}": outputRootPath,
      "{runDirectory}": currentRun,
      "{artifactsDir}": URL(fileURLWithPath: currentRun).appendingPathComponent("artifacts").path,
      "{summaryJson}": URL(fileURLWithPath: currentRun).appendingPathComponent("summary.json").path,
      "{manifestJson}": URL(fileURLWithPath: currentRun).appendingPathComponent("manifest.json").path
    ]

    if let previousRunDirectory {
      replacements["{previousRunDirectory}"] = previousRunDirectory
      replacements["{previousArtifactsDir}"] = URL(fileURLWithPath: previousRunDirectory)
        .appendingPathComponent("artifacts")
        .path
      replacements["{previousSummaryJson}"] = URL(fileURLWithPath: previousRunDirectory)
        .appendingPathComponent("summary.json")
        .path
      replacements["{previousManifestJson}"] = URL(fileURLWithPath: previousRunDirectory)
        .appendingPathComponent("manifest.json")
        .path
    }

    for (index, inputPath) in inputPaths.enumerated() {
      replacements["{input\(index)}"] = inputPath
    }

    for (token, completedRunDirectory) in completedRunDirectories {
      replacements["{runDirectory:\(token)}"] = completedRunDirectory
      replacements["{artifactsDir:\(token)}"] = URL(fileURLWithPath: completedRunDirectory)
        .appendingPathComponent("artifacts")
        .path
      replacements["{summaryJson:\(token)}"] = URL(fileURLWithPath: completedRunDirectory)
        .appendingPathComponent("summary.json")
        .path
      replacements["{manifestJson:\(token)}"] = URL(fileURLWithPath: completedRunDirectory)
        .appendingPathComponent("manifest.json")
        .path
    }

    return replacements
      .sorted { $0.key.count > $1.key.count }
      .reduce(rawArguments) { partial, pair in
        partial.replacingOccurrences(of: pair.key, with: ShellWords.quote(pair.value))
      }
  }

  private func supportBundlePayload(generatedAt: Date) -> SupportBundlePayload {
    SupportBundlePayload(
      version: 1,
      generatedAt: generatedAt,
      appName: "Scientific Workbench",
      skillRootPath: redactSecrets(skillRootPath),
      outputRootPath: redactSecrets(outputRootPath),
      pythonExecutable: redactSecrets(pythonExecutable),
      selectedSection: selectedSection,
      aiProvider: aiProvider,
      aiModel: selectedAIModel,
      cloudAttachmentContextMode: cloudAttachmentContextMode,
      agentMode: agentMode,
      agentAutoRun: agentAutoRun,
      agentStatusMessage: redactSecrets(agentStatusMessage),
      inputPaths: inputPaths.map(redactSecrets),
      setupChecklistItems: setupChecklistItems.map(redactedChecklistItem),
      setupRecoveryState: setupRecoveryState.map(redactedSetupRecoveryState),
      environmentStatus: redactedEnvironmentStatus(environmentStatus),
      ollamaSetupStatus: redactedOllamaSetupStatus(ollamaSetupStatus),
      aiConnectionStatuses: Dictionary(
        uniqueKeysWithValues: aiConnectionStatuses.map { provider, status in
          (provider.rawValue, redactedAIConnectionStatus(status))
        }
      ),
      capabilityCounts: [
        "all": capabilities.count,
        "user_facing": userCapabilities.count,
        "maintainer_only": maintainerCapabilities.count
      ],
      agentPlan: agentPlan.map(redactedPlan),
      stepExecutions: agentPlanStepExecutions.values
        .sorted { ($0.finishedAt ?? .distantPast) < ($1.finishedAt ?? .distantPast) }
        .map(redactedStepExecution),
      workflowRecoveryState: workflowRecoveryState.map(redactedWorkflowRecoveryState),
      jobs: jobs.prefix(50).map(redactedJob),
      recentMessages: agentChatMessages.suffix(20).map(redactedChatMessage),
      lastWorkflowSummaryPath: lastWorkflowSummaryPath.map(redactSecrets),
      lastExportedPlanPath: lastExportedPlanPath.map(redactSecrets)
    )
  }

  private func redactedChecklistItem(_ item: SetupChecklistItem) -> SetupChecklistItem {
    SetupChecklistItem(
      id: item.id,
      title: redactSecrets(item.title),
      detail: redactSecrets(item.detail),
      state: item.state,
      systemImage: item.systemImage,
      isRequired: item.isRequired
    )
  }

  private func redactedSetupRecoveryState(_ recovery: SetupRecoveryState) -> SetupRecoveryState {
    SetupRecoveryState(
      title: redactSecrets(recovery.title),
      detail: redactSecrets(recovery.detail),
      blockingItemIDs: recovery.blockingItemIDs.map(redactSecrets),
      recommendedActions: recovery.recommendedActions.map(redactSecrets)
    )
  }

  private func redactedEnvironmentStatus(_ status: EnvironmentStatus) -> EnvironmentStatus {
    EnvironmentStatus(
      status: redactSecrets(status.status),
      skillRoot: redactSecrets(status.skillRoot),
      datanalysisPython: status.datanalysisPython.map(redactSecrets),
      datanalysisRoot: status.datanalysisRoot.map(redactSecrets),
      details: redactSecrets(status.details),
      warnings: status.warnings.map(redactSecrets),
      refreshedAt: status.refreshedAt
    )
  }

  private func redactedOllamaSetupStatus(_ status: OllamaSetupStatus) -> OllamaSetupStatus {
    OllamaSetupStatus(
      cliPath: status.cliPath.map(redactSecrets),
      serverReachable: status.serverReachable,
      installedModels: status.installedModels.map(redactSecrets),
      targetModel: redactSecrets(status.targetModel),
      message: redactSecrets(status.message),
      checkedAt: status.checkedAt
    )
  }

  private func redactedAIConnectionStatus(_ status: AIConnectionStatus) -> AIConnectionStatus {
    AIConnectionStatus(
      state: status.state,
      message: redactSecrets(status.message),
      checkedAt: status.checkedAt
    )
  }

  private func redactedWorkflowRecoveryState(_ recovery: WorkflowRecoveryState) -> WorkflowRecoveryState {
    WorkflowRecoveryState(
      id: recovery.id,
      completedCount: recovery.completedCount,
      totalCount: recovery.totalCount,
      resumeStepIndex: recovery.resumeStepIndex,
      resumeStepCapabilityID: redactSecrets(recovery.resumeStepCapabilityID),
      resumeStepSummary: redactSecrets(recovery.resumeStepSummary),
      stoppedStatus: recovery.stoppedStatus,
      stoppedJobID: recovery.stoppedJobID,
      stoppedJobLabel: recovery.stoppedJobLabel.map(redactSecrets),
      recoveryAdvice: recovery.recoveryAdvice.map(redactSecrets),
      canResume: recovery.canResume
    )
  }

  private func redactedStepExecution(_ execution: AgentPlanStepExecution) -> AgentPlanStepExecution {
    AgentPlanStepExecution(
      id: execution.id,
      stepID: execution.stepID,
      capabilityID: redactSecrets(execution.capabilityID),
      jobID: execution.jobID,
      status: execution.status,
      runDirectory: redactSecrets(execution.runDirectory),
      finishedAt: execution.finishedAt
    )
  }

  private func redactedChatMessage(_ message: AgentChatMessage) -> AgentChatMessage {
    AgentChatMessage(
      id: message.id,
      role: message.role,
      text: redactSecrets(message.text),
      createdAt: message.createdAt
    )
  }

  private func redactedArtifact(_ artifact: Artifact) -> Artifact {
    Artifact(
      id: artifact.id,
      path: redactSecrets(artifact.path),
      relativePath: redactSecrets(artifact.relativePath),
      byteCount: artifact.byteCount,
      artifactType: artifact.artifactType,
      label: artifact.label.map(redactSecrets),
      primary: artifact.primary
    )
  }

  private func redactedJob(_ job: JobRecord) -> JobRecord {
    var job = job
    job.requestInputPaths = job.requestInputPaths.map(redactSecrets)
    job.requestRawArguments = redactSecrets(job.requestRawArguments)
    job.command = redactSecrets(job.command)
    job.stdout = redactSecrets(job.stdout)
    job.stderr = redactSecrets(job.stderr)
    job.runDirectory = redactSecrets(job.runDirectory)
    job.artifacts = job.artifacts.map(redactedArtifact)
    job.parsedTool = job.parsedTool.map(redactSecrets)
    job.parsedStatus = job.parsedStatus.map(redactSecrets)
    job.message = job.message.map(redactSecrets)
    job.contractVersion = job.contractVersion.map(redactSecrets)
    job.appStatus = job.appStatus.map(redactSecrets)
    job.shortSummary = job.shortSummary.map(redactSecrets)
    job.severity = job.severity.map(redactSecrets)
    job.originalModified = job.originalModified.map(redactSecrets)
    job.warnings = job.warnings.map(redactSecrets)
    job.structuredErrors = job.structuredErrors.map {
      JobStructuredError(
        kind: redactSecrets($0.kind),
        message: redactSecrets($0.message),
        recoveryHint: $0.recoveryHint.map(redactSecrets)
      )
    }
    job.nextActions = job.nextActions.map {
      JobNextAction(
        label: redactSecrets($0.label),
        kind: $0.kind.map(redactSecrets),
        priority: $0.priority.map(redactSecrets)
      )
    }
    job.previewArtifactTypes = job.previewArtifactTypes.map(redactSecrets)
    job.tags = job.tags.map(redactSecrets)
    return job
  }

  private func writeLaunchTranscript(to path: String) {
    guard let destination = approvedLaunchTranscriptDestination(path) else { return }
    do {
      try launchTranscriptService.write(
        to: destination.path,
        snapshot: LaunchTranscriptSnapshot(
          generatedAt: Date(),
          inputPaths: inputPaths,
          outputRootPath: outputRootPath,
          agentMode: agentMode,
          aiProvider: aiProvider,
          aiModel: selectedAIModel,
          aiBaseURL: selectedAIBaseURL,
          autoRun: agentAutoRun,
          status: agentStatusMessage,
          setupChecklistItems: setupChecklistItems,
          setupRecoveryState: setupRecoveryState,
          agentPlan: agentPlan,
          messages: agentChatMessages,
          jobs: jobs
        ),
        redact: redactSecrets
      )
    } catch {
      agentStatusMessage = "Could not write launch transcript: \(error.localizedDescription)"
    }
  }

  private func approvedLaunchTranscriptDestination(_ path: String) -> URL? {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return nil }
    let destination = canonicalFilesystemURL(path)
    let outputRoot = canonicalFilesystemURL(outputRootPath)
    guard destination.deletingLastPathComponent().path == outputRoot.path else {
      agentStatusMessage = "Launch transcript blocked: choose a new file directly inside the output root."
      return nil
    }
    guard !FileManager.default.fileExists(atPath: destination.path) else {
      agentStatusMessage = "Launch transcript blocked: the destination already exists and will not be overwritten."
      return nil
    }
    for inputPath in inputPaths {
      let input = canonicalFilesystemURL(inputPath)
      if filesystemURL(input, contains: destination) || filesystemURL(destination, contains: input) {
        agentStatusMessage = "Launch transcript blocked: the destination overlaps an attached input."
        return nil
      }
    }

    switch filesystemSafetyPolicy.assessOutputRoot(
      destination.deletingLastPathComponent().path,
      inputPaths: []
    ) {
    case .safe:
      return destination
    case .requiresConfirmation(let reason):
      guard outputRootRiskApprovalIsCurrent(inputPaths: inputPaths) else {
        agentStatusMessage = "Launch transcript blocked until you confirm the path in Settings: \(reason)"
        return nil
      }
      return destination
    case .blocked(let reason):
      agentStatusMessage = "Unsafe launch transcript destination: \(reason)"
      return nil
    }
  }

  private func approvedExportDestination(_ path: String) -> URL? {
    let destination = canonicalFilesystemURL(path)
    let outputRoot = canonicalFilesystemURL(outputRootPath)
    guard destination.path != outputRoot.path, filesystemURL(outputRoot, contains: destination) else {
      agentStatusMessage = "Export blocked: choose a new file inside the configured output root."
      return nil
    }
    guard !FileManager.default.fileExists(atPath: destination.path) else {
      agentStatusMessage = "Export blocked: the destination already exists and will not be overwritten."
      return nil
    }
    for inputPath in inputPaths {
      let input = canonicalFilesystemURL(inputPath)
      if filesystemURL(input, contains: destination) || filesystemURL(destination, contains: input) {
        agentStatusMessage = "Export blocked: the destination overlaps an attached input."
        return nil
      }
    }
    return destination
  }

  private func canonicalFilesystemURL(_ path: String) -> URL {
    FilesystemPath.canonicalURL(path)
  }

  private func filesystemURL(_ parent: URL, contains child: URL) -> Bool {
    if parent.path == child.path { return true }
    let prefix = parent.path == "/" ? "/" : parent.path + "/"
    return child.path.hasPrefix(prefix)
  }

  @discardableResult
  func writeWorkflowSummary(
    plan: AgentPlan,
    enabledSteps: [AgentPlanStep],
    jobIDs: [UUID],
    status: String,
    startedAt: Date,
    finishedAt: Date
  ) -> String? {
    guard ensureOutputRootWriteApproved(inputPaths: inputPaths) else { return nil }
    do {
      let fileURL = try workflowSummaryService.write(
        request: WorkflowSummaryRequest(
          plan: plan,
          enabledSteps: enabledSteps,
          jobs: jobs,
          jobIDs: jobIDs,
          inputPaths: inputPaths,
          outputRootPath: outputRootPath,
          status: status,
          startedAt: startedAt,
          finishedAt: finishedAt
        ),
        redact: redactSecrets
      )
      lastWorkflowSummaryPath = fileURL.path
      return fileURL.path
    } catch {
      agentStatusMessage = "Could not write workflow summary: \(error.localizedDescription)"
      return nil
    }
  }

  private var configuredSecrets: [String] {
    [
      openAIAPIKey,
      grokAPIKey,
      geminiAPIKey
    ]
  }

  private func redactSecrets(_ text: String) -> String {
    SecretsRedactor.redact(text, secrets: configuredSecrets)
  }

  private func redactingConfiguredCloudSecrets(in text: String) -> String {
    let normalizedSecrets = configuredSecrets
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
      .sorted { lhs, rhs in
        if lhs.count != rhs.count { return lhs.count > rhs.count }
        return lhs < rhs
      }
    return normalizedSecrets.reduce(text) { partiallyRedacted, secret in
      partiallyRedacted.replacingOccurrences(of: secret, with: "[REDACTED]")
    }
  }

  private func loadSavedSecretIfNeeded(for provider: AIProvider) {
    guard provider.requiresAPIKey else { return }
    guard !editedCredentialProviders.contains(provider) else { return }
    guard apiKey(for: provider).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
    switch provider {
    case .ollama:
      break
    case .openAI:
      openAIAPIKey = credentialStore.readKey(for: .openAI)
    case .grok:
      grokAPIKey = credentialStore.readKey(for: .grok)
    case .gemini:
      geminiAPIKey = credentialStore.readKey(for: .gemini)
    }
  }

  private func invalidateAIConnectionStatus(for provider: AIProvider) {
    aiConnectionStatuses[provider] = .unknown
  }

  private func aiConnectionRequest(for provider: AIProvider) -> AIConnectionRequest {
    AIConnectionRequest(
      provider: provider,
      apiKey: apiKey(for: provider),
      model: model(for: provider),
      baseURL: baseURL(for: provider),
      secretsToRedact: configuredSecrets
    )
  }

  private func redactedPlan(_ plan: AgentPlan) -> AgentPlan {
    var plan = plan
    plan.title = redactSecrets(plan.title)
    plan.rationale = redactSecrets(plan.rationale)
    plan.steps = plan.steps.map { step in
      var step = step
      step.summary = redactSecrets(step.summary)
      step.rawArguments = redactSecrets(step.rawArguments)
      return step
    }
    return plan
  }

  private func deduplicatedPersistedPlan(
    _ source: AgentPlan
  ) -> (plan: AgentPlan, removed: Int) {
    var plan = source
    var seen: Set<AgentPlanStep.ID> = []
    var removed = 0
    plan.steps = source.steps.filter { step in
      let inserted = seen.insert(step.id).inserted
      if !inserted { removed += 1 }
      return inserted
    }
    return (plan, removed)
  }
}

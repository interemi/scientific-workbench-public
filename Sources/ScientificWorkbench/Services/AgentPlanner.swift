import Foundation

private struct PlannerCapabilitySummaryPayload: Encodable {
  var block: String
  var description: String
  var guidedRequirement: String
  var id: String
  var label: String
  var appReadiness: String
  var workflowMode: String

  enum CodingKeys: String, CodingKey {
    case block
    case description
    case guidedRequirement = "guided_requirement"
    case id
    case label
    case appReadiness = "app_readiness"
    case workflowMode = "workflow_mode"
  }
}

struct AgentPlanner: Sendable {
  var cloudAIClient: CloudAIPlannerClient
  var skillRouterClient: SkillWorkflowRouterClient
  private let legacySpectroscopyPlanner: LegacySpectroscopyPlanner

  init(
    cloudAIClient: CloudAIPlannerClient = CloudAIPlannerClient(),
    skillRouterClient: SkillWorkflowRouterClient = SkillWorkflowRouterClient(),
    legacySpectroscopyPlanner: LegacySpectroscopyPlanner = LegacySpectroscopyPlanner()
  ) {
    self.cloudAIClient = cloudAIClient
    self.skillRouterClient = skillRouterClient
    self.legacySpectroscopyPlanner = legacySpectroscopyPlanner
  }

  func plan(
    prompt: String,
    inputPaths: [String],
    capabilities: [CapabilityEntry],
    provider: AIProvider,
    apiKey: String,
    model: String,
    baseURL: String? = nil,
    attachmentContextMode: CloudAttachmentContextMode = .previews,
    skillRoot: String = DefaultPaths.motherSkillRoot,
    pythonExecutable: String = DefaultPaths.systemPython
  ) async -> AgentPlan {
    if legacySpectroscopyPlanner.shouldUseDeterministicPlan(prompt: prompt, inputPaths: inputPaths) {
      return applyWorkflowModeSafety(
        to: localPlan(prompt: prompt, inputPaths: inputPaths, capabilities: capabilities),
        capabilities: capabilities,
        allowRestrictedLocalRecipe: true
      )
    }
    if shouldUseDeterministicReadinessPlan(prompt: prompt, inputPaths: inputPaths) {
      return applyWorkflowModeSafety(
        to: localPlan(prompt: prompt, inputPaths: inputPaths, capabilities: capabilities),
        capabilities: capabilities
      )
    }

    let routerPlan: AgentPlan?
    do {
      routerPlan = try await skillRouterClient.plan(
        prompt: prompt,
        inputPaths: inputPaths,
        capabilities: capabilities,
        skillRoot: skillRoot,
        pythonExecutable: pythonExecutable
      )
    } catch let error as SkillWorkflowRouterError where error.isReleaseBlocking {
      return blockedRouterPlan(error)
    } catch {
      routerPlan = nil
    }
    let trimmedKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
    if !provider.requiresAPIKey || !trimmedKey.isEmpty {
      do {
        let cloudPlan = try await cloudAIClient.plan(
          prompt: prompt,
          inputPaths: inputPaths,
          capabilities: capabilities,
          provider: provider,
          apiKey: trimmedKey,
          model: model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? provider.defaultModel : model,
          baseURL: baseURL,
          attachmentContextMode: attachmentContextMode,
          routerPlan: routerPlan
        )
        return applyWorkflowModeSafety(
          to: cloudPlan,
          capabilities: capabilities
        )
      } catch {
        let fallback = routerPlan ?? localPlan(
          prompt: prompt,
          inputPaths: inputPaths,
          capabilities: capabilities
        )
        var plan = applyWorkflowModeSafety(to: fallback, capabilities: capabilities)
        plan.rationale = "\(planningFailurePrefix(provider: provider, model: model, baseURL: baseURL)) Error: \(error.localizedDescription)\n\n\(fallback.rationale)"
        return plan
      }
    }

    return applyWorkflowModeSafety(
      to: routerPlan ?? localPlan(prompt: prompt, inputPaths: inputPaths, capabilities: capabilities),
      capabilities: capabilities
    )
  }

  func deterministicPlan(
    prompt: String,
    inputPaths: [String],
    capabilities: [CapabilityEntry],
    skillRoot: String,
    pythonExecutable: String
  ) async -> AgentPlan {
    if legacySpectroscopyPlanner.shouldUseDeterministicPlan(prompt: prompt, inputPaths: inputPaths) ||
      shouldUseDeterministicReadinessPlan(prompt: prompt, inputPaths: inputPaths) {
      return applyWorkflowModeSafety(
        to: localPlan(prompt: prompt, inputPaths: inputPaths, capabilities: capabilities),
        capabilities: capabilities,
        allowRestrictedLocalRecipe: legacySpectroscopyPlanner.shouldUseDeterministicPlan(prompt: prompt, inputPaths: inputPaths)
      )
    }
    do {
      let routerPlan = try await skillRouterClient.plan(
        prompt: prompt,
        inputPaths: inputPaths,
        capabilities: capabilities,
        skillRoot: skillRoot,
        pythonExecutable: pythonExecutable
      )
      return applyWorkflowModeSafety(to: routerPlan, capabilities: capabilities)
    } catch let error as SkillWorkflowRouterError where error.isReleaseBlocking {
      return blockedRouterPlan(error)
    } catch {
      var fallback = localPlan(prompt: prompt, inputPaths: inputPaths, capabilities: capabilities)
      fallback = applyWorkflowModeSafety(to: fallback, capabilities: capabilities)
      fallback.rationale = "The skill router was unavailable, so the app used its local compatibility planner. Error: \(error.localizedDescription)\n\n\(fallback.rationale)"
      return fallback
    }
  }

  func localPlan(
    prompt: String,
    inputPaths: [String],
    capabilities: [CapabilityEntry]
  ) -> AgentPlan {
    let lowerPrompt = prompt.localizedLowercase
    let extensions = inputExtensions(from: inputPaths)
    let hasFolders = inputPaths.contains { urlIsDirectory($0) }
    let dataKindCount = detectedDataKindCount(extensions)
    var steps: [AgentPlanStep] = []

    func append(_ capabilityID: String, summary: String, usesInputs: Bool = true, usesPreviousOutput: Bool = false) {
      guard capabilities.contains(where: { $0.id == capabilityID }) else { return }
      guard !steps.contains(where: { $0.capabilityID == capabilityID }) else { return }
      steps.append(AgentPlanStep(
        capabilityID: capabilityID,
        summary: summary,
        rawArguments: "",
        usesInputs: usesInputs,
        usesPreviousOutput: usesPreviousOutput
      ))
    }

    append("datanalysis_env.status", summary: "Check that the datanalysis wrapper and Python environment are ready.", usesInputs: false)

    if inputPaths.isEmpty, isReadinessPrompt(lowerPrompt) {
      append("datanalysis_healthcheck", summary: "Run the dedicated datanalysis healthcheck without touching user inputs.", usesInputs: false)
      append("env_doctor", summary: "Summarize machine readiness and optional backend availability.", usesInputs: false)
      return AgentPlan(
        title: "Scientific Workbench readiness check",
        rationale: "The prompt asks for app or environment readiness with no attached inputs, so the local planner uses core diagnostics only and avoids optional external-tool preflights that could stop an otherwise healthy workflow.",
        steps: steps,
        source: .local
      )
    }

    if let legacyPlan = legacySpectroscopyPlanner.planIfNeeded(
      prompt: prompt,
      inputPaths: inputPaths,
      capabilities: capabilities,
      startingSteps: steps
    ) {
      return legacyPlan
    }

    if lowerPrompt.contains("fits") || lowerPrompt.contains("imagen") || lowerPrompt.contains("fotometr") ||
      !extensions.isDisjoint(with: ["fit", "fits", "fts"]) {
      append("inspect_fits", summary: "Inspect the first FITS input and create a quick readiness summary.")
    }

    if lowerPrompt.contains("tabla") || lowerPrompt.contains("csv") || lowerPrompt.contains("datos") ||
      !extensions.isDisjoint(with: ["csv", "tsv", "xlsx", "xls", "parquet"]) {
      append("profile_table", summary: "Profile the tabular input before analysis.")
    }

    if lowerPrompt.contains("document") || lowerPrompt.contains("pdf") || lowerPrompt.contains("presentaci") ||
      hasFolders || !extensions.isDisjoint(with: ["pdf", "docx", "pptx", "key", "pages", "tex", "md"]) {
      append("document_intake_workbench", summary: "Inventory the document bundle without editing original files.")
    }

    if lowerPrompt.contains("notebook") || !extensions.isDisjoint(with: ["ipynb"]) {
      append("notebook_workbench.execute-copy", summary: "Execute a copied notebook only after explicit trusted-code confirmation.")
    }

    if lowerPrompt.contains("mixed") || lowerPrompt.contains("mixto") ||
      lowerPrompt.contains("práctica") || lowerPrompt.contains("practica") || inputPaths.count > 1 ||
      dataKindCount > 1 {
      append("cross_domain_data_workbench", summary: "Run a mixed-data inventory and first-pass report.")
    }

    if steps.count == 1, !inputPaths.isEmpty {
      append("inspect_data_container", summary: "Inspect the selected file or folder as a generic data container.")
    }

    if steps.isEmpty {
      append("datanalysis_env.status", summary: "Start by checking environment readiness.", usesInputs: false)
    }

    return AgentPlan(
      title: "Local workflow plan",
      rationale: "Built from the prompt text, selected input extensions, and guided capabilities available in the installed skill.",
      steps: steps,
      source: .local
    )
  }

  private func urlIsDirectory(_ path: String) -> Bool {
    var isDirectory: ObjCBool = false
    return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) && isDirectory.boolValue
  }

  private func inputExtensions(from inputPaths: [String], maxFilesPerFolder: Int = 300) -> Set<String> {
    var extensions = Set<String>()

    for path in inputPaths {
      let url = URL(fileURLWithPath: path)
      let directExtension = url.pathExtension.localizedLowercase
      if !directExtension.isEmpty {
        extensions.insert(directExtension)
      }

      var isDirectory: ObjCBool = false
      guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory), isDirectory.boolValue else {
        continue
      }
      guard let enumerator = FileManager.default.enumerator(
        at: url,
        includingPropertiesForKeys: [.isRegularFileKey],
        options: [.skipsHiddenFiles]
      ) else {
        continue
      }

      var scannedFiles = 0
      for case let fileURL as URL in enumerator {
        if scannedFiles >= maxFilesPerFolder { break }
        guard let values = try? fileURL.resourceValues(forKeys: [.isRegularFileKey]),
              values.isRegularFile == true else {
          continue
        }
        scannedFiles += 1
        let ext = fileURL.pathExtension.localizedLowercase
        if !ext.isEmpty {
          extensions.insert(ext)
        }
      }
    }

    return extensions
  }

  private func detectedDataKindCount(_ extensions: Set<String>) -> Int {
    let hasFITS = !extensions.isDisjoint(with: ["fit", "fits", "fts"])
    let hasTables = !extensions.isDisjoint(with: ["csv", "tsv", "xlsx", "xls", "parquet"])
    let hasDocuments = !extensions.isDisjoint(with: ["pdf", "docx", "pptx", "key", "pages", "tex", "md", "html"])
    return [hasFITS, hasTables, hasDocuments].filter { $0 }.count
  }

  private func shouldUseDeterministicReadinessPlan(prompt: String, inputPaths: [String]) -> Bool {
    inputPaths.isEmpty && isReadinessPrompt(prompt.localizedLowercase)
  }

  private func isReadinessPrompt(_ lowerPrompt: String) -> Bool {
    let readinessHints = [
      "environment", "readiness", "ready", "setup", "health", "healthcheck", "doctor",
      "entorno", "preparado", "preparada", "estado", "diagnostico", "diagnóstico"
    ]
    return readinessHints.contains { lowerPrompt.contains($0) }
  }

  private func planningFailurePrefix(provider: AIProvider, model: String, baseURL: String?) -> String {
    guard provider == .ollama else {
      return "\(provider.title) planning failed, so the app used the local planner instead."
    }
    let endpoint = baseURL?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
      ? baseURL!
      : AIProvider.ollama.defaultBaseURL ?? "http://localhost:11434"
    let selectedModel = model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      ? provider.defaultModel
      : model
    return "Ollama planning failed, so the app used the deterministic local planner instead. Make sure Ollama is running at \(endpoint) and `ollama pull \(selectedModel)` has completed."
  }

  private func applyWorkflowModeSafety(
    to plan: AgentPlan,
    capabilities: [CapabilityEntry],
    allowRestrictedLocalRecipe: Bool = false
  ) -> AgentPlan {
    let capabilitiesByID = Dictionary(uniqueKeysWithValues: capabilities.map { ($0.id, $0) })
    var safePlan = plan
    safePlan.steps = plan.steps.compactMap { step in
      guard let capability = capabilitiesByID[step.capabilityID],
            !capability.isMaintainerOnly,
            capability.appReadiness.isPlannerVisible || allowRestrictedLocalRecipe else {
        return nil
      }
      guard capability.requiresPlannerConfirmation else {
        return step
      }
      var protected = step
      protected.isEnabled = false
      if !protected.summary.localizedCaseInsensitiveContains("enable it explicitly") {
        protected.summary += " Review this \(capability.workflowMode.rawValue) step and enable it explicitly."
      }
      return protected
    }
    return safePlan
  }

  private func blockedRouterPlan(_ error: SkillWorkflowRouterError) -> AgentPlan {
    AgentPlan(
      title: "Skill router blocked plan",
      rationale: error.localizedDescription,
      steps: [],
      source: .skillRouter
    )
  }
}

struct CloudAIPlannerClient: Sendable {
  var client = CloudAIClient()

  func plan(
    prompt: String,
    inputPaths: [String],
    capabilities: [CapabilityEntry],
    provider: AIProvider,
    apiKey: String,
    model: String,
    baseURL: String? = nil,
    attachmentContextMode: CloudAttachmentContextMode = .previews,
    routerPlan: AgentPlan? = nil
  ) async throws -> AgentPlan {
    let capabilitySummary = capabilities.plannerVisible.map { capability in
      PlannerCapabilitySummaryPayload(
        block: CloudPrivacySanitizer.withholdingAbsolutePaths(in: capability.visibleBlock),
        description: CloudPrivacySanitizer.withholdingAbsolutePaths(in: capability.shortDescription),
        guidedRequirement: capability.guidedRunRequirement.title,
        id: capability.id,
        label: CloudPrivacySanitizer.withholdingAbsolutePaths(in: capability.label),
        appReadiness: capability.appReadiness.rawValue,
        workflowMode: capability.workflowMode.rawValue
      )
    }

    let system = """
    You are the planning brain inside a macOS scientific workbench. Build a safe multi-step workflow from installed capabilities.
    Return only strict JSON with this shape:
    {"title":"...","rationale":"...","steps":[{"capability_id":"...","summary":"...","raw_arguments":"","uses_inputs":true,"uses_previous_output":false}]}
    Use only capability_id values from the provided capability list. Prefer guided runs with empty raw_arguments. Use raw_arguments only when the user clearly needs a capability that has no guided run. Never plan steps that edit original inputs. Treat the deterministic skill-router context as the safety baseline. Only app_ready + normal steps may be enabled automatically. app_ready_partial, blocked_optional, expert, optional, and legacy steps require explicit human review and must use is_enabled=false. cli_only, maintainer_only, and not_applicable_to_app capabilities are omitted from the list.
    """

    let user = """
    User prompt:
    \(prompt)

    Selected inputs:
    \(selectedInputSummary(for: inputPaths, mode: attachmentContextMode))

    Available capabilities:
    \(jsonString(capabilitySummary))

    Deterministic skill-router context:
    \(routerPlanSummary(routerPlan))
    """

    let output = try await client.generateText(
      provider: provider,
      apiKey: apiKey,
      model: model,
      baseURL: baseURL,
      system: system,
      user: user,
      temperature: 0.1
    )
    let payload = try decodePlanPayload(from: output)
    let knownIDs = Set(capabilities.plannerVisible.map(\.id))
    let steps = payload.steps.compactMap { step -> AgentPlanStep? in
      guard let capabilityID = step.normalizedCapabilityID, knownIDs.contains(capabilityID) else { return nil }
      return AgentPlanStep(
        capabilityID: capabilityID,
        summary: step.summary ?? "Run \(capabilityID).",
        rawArguments: step.normalizedRawArguments,
        usesInputs: step.normalizedUsesInputs,
        usesPreviousOutput: step.normalizedUsesPreviousOutput,
        isEnabled: step.normalizedIsEnabled
      )
    }

    guard !steps.isEmpty else {
      throw CloudAIError.emptyPlan
    }

    return AgentPlan(
      title: payload.title ?? "AI workflow plan",
      rationale: payload.rationale ?? "Planned from the prompt and selected inputs.",
      steps: steps,
      source: AgentPlanSource(provider: provider)
    )
  }

  private func jsonString<T: Encodable>(_ value: T) -> String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(value),
          let text = String(data: data, encoding: .utf8) else {
      return "[]"
    }
    return text
  }

  private func selectedInputSummary(for inputPaths: [String], mode: CloudAttachmentContextMode) -> String {
    guard !inputPaths.isEmpty else { return "None" }
    switch mode {
    case .previews:
      return inputPaths.map { CloudPrivacySanitizer.filename(for: $0) }.joined(separator: "\n")
    case .filenamesOnly:
      return inputPaths.map { CloudPrivacySanitizer.filename(for: $0) }.joined(separator: "\n")
    case .none:
      return "Withheld by cloud attachment privacy setting; \(inputPaths.count) attachment\(inputPaths.count == 1 ? "" : "s") selected."
    }
  }

  private func routerPlanSummary(_ plan: AgentPlan?) -> String {
    guard let plan else { return "Unavailable; remain conservative." }
    let steps = plan.steps.map { step in
      [
        "capability_id": step.capabilityID,
        "enabled": String(step.isEnabled),
        "summary": CloudPrivacySanitizer.withholdingAbsolutePaths(in: step.summary),
      ]
    }
    return jsonString(steps)
  }

  private func decodePlanPayload(from text: String) throws -> AgentPlanPayload {
    if let payload = JSONOutputExtractor.decodeLast(AgentPlanPayload.self, from: text) {
      return payload
    }
    throw CloudAIError.invalidJSON(text)
  }
}

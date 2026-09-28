import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func localAgentPlannerCreatesMultiStepPlanFromPromptAndInputs() throws {
    let capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let plan = AgentPlanner().localPlan(
      prompt: "Haz una practica con una carpeta mixta que contiene FITS y tablas CSV sin tocar originales.",
      inputPaths: ["/tmp/ucm_safe_copy/image.fits", "/tmp/ucm_safe_copy/table.csv"],
      capabilities: capabilities
    )

    let ids = plan.steps.map(\.capabilityID)
    #expect(ids.first == "datanalysis_env.status")
    #expect(ids.contains("inspect_fits"))
    #expect(ids.contains("profile_table"))
    #expect(ids.contains("cross_domain_data_workbench"))
    #expect(plan.source == .local)
  }

  @Test
  func localAgentPlannerInspectsNonDOCUSFolderContentsForRouting() throws {
    let root = try makeScenarioFixture(
      name: "mixed-non-docus",
      files: [
        "spectra/target_a.fits": "SIMPLE  =                    T",
        "tables/measurements.csv": "time,flux\n1,2\n",
        "docs/readme.pdf": "%PDF-1.4\n"
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let plan = AgentPlanner().localPlan(
      prompt: "Analiza esta carpeta de laboratorio sin tocar los originales.",
      inputPaths: [root.path],
      capabilities: capabilities
    )

    let ids = plan.steps.map(\.capabilityID)
    #expect(plan.title == "Local workflow plan")
    #expect(ids.first == "datanalysis_env.status")
    #expect(ids.contains("inspect_fits"))
    #expect(ids.contains("profile_table"))
    #expect(ids.contains("document_intake_workbench"))
    #expect(ids.contains("cross_domain_data_workbench"))
    #expect(!ids.contains("legacy_spectroscopy_envcheck"))
  }

  @Test
  func localAgentPlannerRoutesNotebookInputsToSafeCopyExecution() throws {
    let notebook = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Notebook-\(UUID().uuidString)")
      .appendingPathExtension("ipynb")
    try """
    {"cells":[{"cell_type":"markdown","metadata":{},"source":["# Notebook smoke\\n"]}],"metadata":{},"nbformat":4,"nbformat_minor":5}
    """.write(to: notebook, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: notebook) }

    let capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let plan = AgentPlanner().localPlan(
      prompt: "Inspect this notebook safely.",
      inputPaths: [notebook.path],
      capabilities: capabilities
    )

    let ids = plan.steps.map(\.capabilityID)
    #expect(ids.first == "datanalysis_env.status")
    #expect(ids.contains("notebook_workbench.execute-copy"))
  }

  @Test
  func localAgentPlannerTreatsMultipleKindsInOneFolderAsCrossDomain() throws {
    let root = try makeScenarioFixture(
      name: "implicit-cross-domain",
      files: [
        "a.fits": "SIMPLE  =                    T",
        "b.csv": "x,y\n1,2\n",
        "c.pdf": "%PDF-1.4\n"
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let plan = AgentPlanner().localPlan(
      prompt: "Analyze this dataset safely.",
      inputPaths: [root.path],
      capabilities: capabilities
    )

    #expect(plan.steps.map(\.capabilityID).contains("cross_domain_data_workbench"))
  }

  @Test
  func localAgentPlannerScenarioMatrixIsNotDOCUSOnly() throws {
    let capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let scenarios: [(name: String, files: [String: String], expected: [String], unexpected: [String])] = [
      (
        name: "csv-only",
        files: ["measurements/table.csv": "x,y\n1,2\n"],
        expected: ["profile_table"],
        unexpected: ["inspect_fits", "cross_domain_data_workbench", "legacy_spectroscopy_envcheck"]
      ),
      (
        name: "fits-only",
        files: ["images/source.fits": "SIMPLE  =                    T"],
        expected: ["inspect_fits"],
        unexpected: ["profile_table", "cross_domain_data_workbench", "legacy_spectroscopy_envcheck"]
      ),
      (
        name: "documents-only",
        files: ["papers/reference.pdf": "%PDF-1.4\n", "notes/report.md": "# Notes\n"],
        expected: ["document_intake_workbench"],
        unexpected: ["inspect_fits", "profile_table", "cross_domain_data_workbench", "legacy_spectroscopy_envcheck"]
      )
    ]

    for scenario in scenarios {
      let root = try makeScenarioFixture(name: scenario.name, files: scenario.files)
      defer { try? FileManager.default.removeItem(at: root) }

      let plan = AgentPlanner().localPlan(
        prompt: "Analyze this folder and explain the safe next workflow.",
        inputPaths: [root.path],
        capabilities: capabilities
      )
      let ids = plan.steps.map(\.capabilityID)

      #expect(ids.first == "datanalysis_env.status")
      for expected in scenario.expected {
        #expect(ids.contains(expected), "\(scenario.name) should include \(expected)")
      }
      for unexpected in scenario.unexpected {
        #expect(!ids.contains(unexpected), "\(scenario.name) should not include \(unexpected)")
      }
    }
  }

  @Test
  func agentPlanEstimateExcludesDisabledStepsAndShowsLocalCost() {
    let plan = AgentPlan(
      title: "Small local plan",
      rationale: "Estimate a small local run.",
      steps: [
        AgentPlanStep(
          capabilityID: "datanalysis_env.status",
          summary: "Check environment.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: "fxcor_iraf_workbench.run-auto",
          summary: "Disabled long external step.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: true,
          isEnabled: false
        )
      ],
      source: .ollama
    )

    let estimate = AgentPlanEstimate.estimate(plan: plan)

    #expect(estimate.enabledStepCount == 1)
    #expect(estimate.maxSeconds <= 10)
    #expect(estimate.costNote.contains("no cloud API cost"))
    #expect(estimate.caution == nil)
  }

  @Test
  func agentPlanEstimateFlagsLongCloudPlannedWorkflows() {
    let plan = AgentPlan(
      title: "Long cloud-planned workflow",
      rationale: "Estimate a realistic multi-step run.",
      steps: [
        AgentPlanStep(
          capabilityID: "document_intake_workbench",
          summary: "Read documents.",
          rawArguments: "",
          usesInputs: true,
          usesPreviousOutput: false
        ),
        AgentPlanStep(
          capabilityID: "fxcor_iraf_workbench.run-auto",
          summary: "Run external spectroscopy automation.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: true
        ),
        AgentPlanStep(
          capabilityID: "latex_workbench.compile",
          summary: "Compile report.",
          rawArguments: "",
          usesInputs: false,
          usesPreviousOutput: true
        )
      ],
      source: .openAI
    )

    let estimate = AgentPlanEstimate.estimate(plan: plan)

    #expect(estimate.enabledStepCount == 3)
    #expect(estimate.maxSeconds >= 600)
    #expect(estimate.runtimeText.contains("Estimated runtime"))
    #expect(estimate.costNote.contains("OpenAI API quota"))
    #expect(estimate.caution?.contains("Long workflow") == true)
  }

  @Test
  func localAgentPlannerRecognizesLegacySpectroscopyPracticeFolders() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-DOCUS-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(
      at: root.appendingPathComponent("fits_p1", isDirectory: true),
      withIntermediateDirectories: true
    )
    try FileManager.default.createDirectory(
      at: root.appendingPathComponent("iSTARMOD", isDirectory: true),
      withIntermediateDirectories: true
    )
    try "fwhm,vsini\n1,2\n".write(
      to: root.appendingPathComponent("FWHM_vsini_datafit.csv"),
      atomically: true,
      encoding: .utf8
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let plan = AgentPlanner().localPlan(
      prompt: "Haz la practica UCM con esta carpeta DOCUS sin tocar originales.",
      inputPaths: [root.path],
      capabilities: capabilities
    )

    let ids = plan.steps.map(\.capabilityID)
    #expect(plan.title.contains("UCM"))
    #expect(ids.contains("legacy_spectroscopy_envcheck"))
    #expect(ids.contains("echelle_multispec_inventory"))
    #expect(ids.contains("fxcor_iraf_workbench.prepare-session"))
    #expect(ids.contains("legacy_rv_coursework_workbench.analyze"))
    let rvStep = try #require(plan.steps.first { $0.capabilityID == "legacy_rv_coursework_workbench.analyze" })
    #expect(rvStep.usesInputs)
    #expect(rvStep.usesPreviousOutput)
    let referenceStep = try #require(plan.steps.first { $0.capabilityID == "legacy_external_reference_check" })
    #expect(referenceStep.usesInputs)
    #expect(referenceStep.usesPreviousOutput)
    #expect(ids.contains("legacy_spectroscopy_report_builder.populate"))
    #expect(ids.contains("latex_workbench.review"))
    #expect(ids.contains("latex_workbench.compile"))
  }

  @Test
  func localAgentPlannerUsesCoreReadinessPlanForNoInputEnvironmentPrompts() throws {
    let capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let plan = AgentPlanner().localPlan(
      prompt: "Check the Scientific Workbench environment readiness and write a safe summary.",
      inputPaths: [],
      capabilities: capabilities
    )

    #expect(plan.title == "Scientific Workbench readiness check")
    #expect(plan.source == .local)
    #expect(plan.steps.map(\.capabilityID) == [
      "datanalysis_env.status",
      "datanalysis_healthcheck",
      "env_doctor"
    ])
  }

  @Test
  func cloudAIPlannerClientDecodesMockedWorkflowJSON() async throws {
    let planJSON = """
    {"title":"Mocked AI plan","rationale":"Because the prompt asked for a table profile.","steps":[{"capability_id":"profile_table","summary":"Profile the table.","raw_arguments":"","uses_inputs":true,"uses_previous_output":false}]}
    """
    let responseData = try JSONSerialization.data(withJSONObject: ["output_text": planJSON])
    let response = String(data: responseData, encoding: .utf8)!
    let recorder = RequestRecorder(responseBody: response)
    let planner = CloudAIPlannerClient(client: CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    }))
    let capabilities = [
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

    let plan = try await planner.plan(
      prompt: "Profile this CSV",
      inputPaths: ["/tmp/data.csv"],
      capabilities: capabilities,
      provider: AIProvider.openAI,
      apiKey: "sk-test",
      model: "gpt-test"
    )

    #expect(plan.title == "Mocked AI plan")
    #expect(plan.source == AgentPlanSource.openAI)
    #expect(plan.steps.map { $0.capabilityID } == ["profile_table"])

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let input = try #require(body["input"] as? String)
    #expect(input.contains("data.csv"))
    #expect(!input.contains("/tmp/data.csv"))
    #expect(input.contains("""
    Available capabilities:
    [{"app_readiness":"app_ready","block":"notebooks + cross-domain","description":"Profile a table.","guided_requirement":"Needs one input","id":"profile_table","label":"profile_table.py","workflow_mode":"normal"}]
    """))
  }

  @Test
  func agentPlannerFallsBackToLocalPlanWhenCloudPlanningFails() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "router-fallback",
      files: ["scripts/scientific_workflow_router.py": "# router fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let routerPayload = """
    {"status":"ok","app_status":"PASS","input_kind":"table_csv","recommended_capabilities":[{"capability_id":"profile_table","reason":"Profile the copied table.","workflow_mode":"normal","requires_confirmation":false,"uses_inputs":true,"uses_previous_output":false,"app_raw_arguments":""}],"safety_notes":["Dry-run only."],"warnings":[]}
    """
    let planner = AgentPlanner(
      cloudAIClient: CloudAIPlannerClient(
        client: CloudAIClient(dataLoader: { _ in
          throw CloudAIError.requestFailed("simulated provider outage")
        })
      ),
      skillRouterClient: SkillWorkflowRouterClient(runCommand: { _ in
        ProcessResult(
          exitCode: 0,
          stdout: routerPayload,
          stderr: "",
          startedAt: Date(timeIntervalSince1970: 1),
          finishedAt: Date(timeIntervalSince1970: 2)
        )
      })
    )
    let capabilities = [
      environmentCapability(),
      sampleCapability()
    ]

    let plan = await planner.plan(
      prompt: "Profile this CSV table safely.",
      inputPaths: ["/tmp/synthetic-table.csv"],
      capabilities: capabilities,
      provider: AIProvider.openAI,
      apiKey: "sk-test-secret",
      model: "gpt-test",
      skillRoot: skillRoot.path
    )

    #expect(plan.source == .skillRouter)
    #expect(plan.rationale.contains("OpenAI planning failed"))
    #expect(plan.rationale.contains("simulated provider outage"))
    #expect(plan.steps.map(\.capabilityID) == ["datanalysis_env.status", "profile_table"])
  }

  @Test
  func agentPlannerAppliesSafetyWhenRouterAndCloudBothFail() async throws {
    let skillRoot = try makeScenarioFixture(name: "double-planner-fallback", files: [:])
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let planner = AgentPlanner(
      cloudAIClient: CloudAIPlannerClient(
        client: CloudAIClient(dataLoader: { _ in
          throw CloudAIError.requestFailed("simulated provider outage")
        })
      ),
      skillRouterClient: SkillWorkflowRouterClient(runCommand: { _ in
        Issue.record("The router command must not run when its script is missing.")
        throw SkillWorkflowRouterError.invalidPayload("unexpected invocation")
      })
    )

    let plan = await planner.plan(
      prompt: "Inspect this FITS image safely.",
      inputPaths: ["/tmp/synthetic-image.fits"],
      capabilities: [environmentCapability(), expertFITSCapability()],
      provider: .openAI,
      apiKey: "sk-test-secret",
      model: "gpt-test",
      skillRoot: skillRoot.path
    )

    let fitsStep = try #require(plan.steps.first { $0.capabilityID == "inspect_fits" })
    #expect(!fitsStep.isEnabled)
    #expect(fitsStep.summary.contains("enable it explicitly"))
    #expect(plan.rationale.contains("OpenAI planning failed"))
  }

  @Test
  func agentPlannerStopsOnReleaseBlockingRouterStatusBeforeCallingCloud() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "blocking-router-status",
      files: ["scripts/scientific_workflow_router.py": "# router fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let routerPayload = """
    {"status":"ROTO","app_status":"ROTO","input_kind":"fits","recommended_capabilities":[{"capability_id":"inspect_fits","reason":"Inspect the image.","workflow_mode":"normal","app_readiness":"app_ready","requires_confirmation":false}],"safety_notes":[],"warnings":[]}
    """
    let planner = AgentPlanner(
      cloudAIClient: CloudAIPlannerClient(
        client: CloudAIClient(dataLoader: { _ in
          Issue.record("Cloud planning must not override a release-blocking router status.")
          throw CloudAIError.requestFailed("unexpected cloud invocation")
        })
      ),
      skillRouterClient: SkillWorkflowRouterClient(runCommand: { _ in
        ProcessResult(
          exitCode: 0,
          stdout: routerPayload,
          stderr: "",
          startedAt: Date(timeIntervalSince1970: 1),
          finishedAt: Date(timeIntervalSince1970: 2)
        )
      })
    )

    let plan = await planner.plan(
      prompt: "Inspect this FITS image.",
      inputPaths: ["/tmp/synthetic-image.fits"],
      capabilities: [environmentCapability(), expertFITSCapability()],
      provider: .openAI,
      apiKey: "sk-test-secret",
      model: "gpt-test",
      skillRoot: skillRoot.path
    )

    #expect(plan.source == .skillRouter)
    #expect(plan.steps.isEmpty)
    #expect(plan.title == "Skill router blocked plan")
    #expect(plan.rationale.contains("ROTO"))
  }

  @Test
  func agentPlanPayloadSupportsDisabledSteps() throws {
    let json = """
    {
      "title": "Editable plan",
      "rationale": "Test",
      "steps": [
        {
          "capability_id": "profile_table",
          "summary": "Profile",
          "raw_arguments": "",
          "uses_inputs": true,
          "uses_previous_output": false,
          "is_enabled": false
        }
      ]
    }
    """

    let payload = try JSONDecoder().decode(AgentPlanPayload.self, from: Data(json.utf8))
    #expect(payload.steps.first?.normalizedCapabilityID == "profile_table")
    #expect(payload.steps.first?.normalizedIsEnabled == false)
  }

  @Test
  func agentRoutingServiceResolvesAutoModeWithoutUIState() {
    let service = AgentRoutingService()

    #expect(
      service.resolvedMode(
        configuredMode: .auto,
        prompt: "Necesito analizar DOCUS y generar un informe PDF.",
        hasInputs: true
      ) == .workflow
    )
    #expect(
      service.resolvedMode(
        configuredMode: .auto,
        prompt: "Implementa tests Swift para este repo.",
        hasInputs: false
      ) == .chat
    )
    #expect(
      service.resolvedMode(
        configuredMode: .codex,
        prompt: "Implementa tests Swift para este repo.",
        hasInputs: false
      ) == .codex
    )
    #expect(
      service.resolvedMode(
        configuredMode: .auto,
        prompt: "Hola, explicame que puedes hacer.",
        hasInputs: false
      ) == .chat
    )
    #expect(
      service.resolvedMode(
        configuredMode: .chat,
        prompt: "Run this CSV workflow.",
        hasInputs: true
      ) == .chat
    )
  }

  @Test
  func agentRoutingServiceDescribesExactCloudConsentCategories() throws {
    let service = AgentRoutingService()

    let chat = try #require(service.cloudConsentRequest(
      provider: .openAI,
      model: "gpt-test",
      purpose: .chat,
      hasConversationHistory: true,
      inputCount: 2,
      attachmentContextMode: .previews,
      hasWorkflowRecovery: true
    ))
    #expect(chat.provider == .openAI)
    #expect(chat.model == "gpt-test")
    #expect(chat.categories == [
      .currentMessage,
      .recentConversation,
      .attachmentFilenames,
      .attachmentPreviews,
      .workflowRecoveryStatus,
      .workflowRecoveryFilenames,
      .workflowRecoveryExcerpts,
    ])

    let planning = try #require(service.cloudConsentRequest(
      provider: .gemini,
      model: "gemini-test",
      purpose: .workflowPlanning,
      hasConversationHistory: true,
      inputCount: 1,
      attachmentContextMode: .none,
      hasWorkflowRecovery: true
    ))
    #expect(planning.categories == [
      .currentMessage,
      .attachmentCount,
      .capabilityCatalog,
      .deterministicRouterPlan,
    ])

    #expect(service.cloudConsentRequest(
      provider: .ollama,
      model: "qwen-test",
      purpose: .chat,
      hasConversationHistory: true,
      inputCount: 1,
      attachmentContextMode: .previews,
      hasWorkflowRecovery: true
    ) == nil)
  }

  @Test
  func agentRoutingServiceBuildsRedactedRecoveryContext() {
    let service = AgentRoutingService()
    let capability = CapabilityEntry(
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
    var job = JobRecord(capability: capability, runDirectory: "/tmp/sk-secret-run")
    job.status = .timedOut
    job.parsedStatus = "blocked by sk-secret-token"
    job.exitCode = 124
    job.message = "Timeout after reading sk-secret-token"
    job.stderr = "stderr contained sk-secret-token"
    job.stdout = "stdout contained sk-secret-token"

    let recovery = WorkflowRecoveryState(
      id: UUID(),
      completedCount: 1,
      totalCount: 3,
      resumeStepIndex: 2,
      resumeStepCapabilityID: "profile_table",
      resumeStepSummary: "Continue from sk-secret-token",
      stoppedStatus: .timedOut,
      stoppedJobID: job.id,
      stoppedJobLabel: job.capabilityLabel,
      recoveryAdvice: ["Inspect sk-secret-token before resuming."],
      canResume: true
    )

    let context = service.workflowRecoveryPromptContext(
      recovery: recovery,
      stoppedJob: job,
      lastWorkflowSummaryPath: "/tmp/sk-secret-summary.md",
      attachmentContextMode: .previews,
      redact: { $0.replacingOccurrences(of: "sk-secret-token", with: "[REDACTED]") }
    )

    #expect(context?.contains("Workflow recovery state:") == true)
    #expect(context?.contains("- Stopped status: Timed Out") == true)
    #expect(context?.contains("- Can use Run Remaining: yes") == true)
    #expect(context?.contains("[REDACTED]") == true)
    #expect(context?.contains("sk-secret-token") == false)
    #expect(context?.contains("sk-secret-run") == true)
    #expect(context?.contains("sk-secret-summary.md") == true)
    #expect(context?.contains("/tmp/") == false)
  }

  @Test
  func agentRoutingServiceAppliesRecoveryPrivacyModeToNamesContentAndLogs() {
    let service = AgentRoutingService()
    let capability = CapabilityEntry(
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
    var job = JobRecord(capability: capability, runDirectory: "/Users/researcher/Private Runs/run-42")
    job.status = .failed
    job.parsedStatus = "failed while opening /Users/researcher/raw/private.csv"
    job.exitCode = 2
    job.message = "Could not read /Users/researcher/raw/private.csv"
    job.stderr = "trace at /Users/researcher/scripts/private.py"
    job.stdout = "partial private output"

    let recovery = WorkflowRecoveryState(
      id: UUID(),
      completedCount: 1,
      totalCount: 3,
      resumeStepIndex: 2,
      resumeStepCapabilityID: "profile_table",
      resumeStepSummary: "Continue with private table content",
      stoppedStatus: .failed,
      stoppedJobID: job.id,
      stoppedJobLabel: job.capabilityLabel,
      recoveryAdvice: ["Inspect /Users/researcher/raw/private.csv before resuming."],
      canResume: true
    )

    let filenamesOnly = service.workflowRecoveryPromptContext(
      recovery: recovery,
      stoppedJob: job,
      lastWorkflowSummaryPath: "/Users/researcher/Private Runs/workflow-summary.md",
      attachmentContextMode: .filenamesOnly,
      redact: { $0 }
    ) ?? ""
    #expect(filenamesOnly.contains("run-42"))
    #expect(filenamesOnly.contains("workflow-summary.md"))
    #expect(filenamesOnly.contains("profile_table"))
    #expect(!filenamesOnly.contains("Private Runs"))
    #expect(!filenamesOnly.contains("private table content"))
    #expect(!filenamesOnly.contains("partial private output"))
    #expect(!filenamesOnly.contains("trace at"))
    #expect(!filenamesOnly.contains("/Users/"))

    let none = service.workflowRecoveryPromptContext(
      recovery: recovery,
      stoppedJob: job,
      lastWorkflowSummaryPath: "/Users/researcher/Private Runs/workflow-summary.md",
      attachmentContextMode: .none,
      redact: { $0 }
    ) ?? ""
    #expect(none.contains("Completed enabled steps: 1/3"))
    #expect(none.contains("Stopped status: Failed"))
    #expect(!none.contains("profile_table"))
    #expect(!none.contains("run-42"))
    #expect(!none.contains("workflow-summary.md"))
    #expect(!none.contains("private"))
    #expect(!none.contains("stdout"))
    #expect(!none.contains("stderr"))
    #expect(!none.contains("/Users/"))
  }

}

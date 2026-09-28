import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func launchAutomationParsesAgentArguments() {
    let options = LaunchAutomationOptions.parse([
      "Scientific Workbench",
      "--agent-input", "~/Desktop/DOCUS",
      "--agent-mode", "codex",
      "--agent-auto-run",
      "--agent-output-root", "/tmp/sw",
      "--agent-codex-sandbox", "workspace-write",
      "--agent-ai-provider", "gemini",
      "--agent-ai-model", "gemini-2.5-pro",
      "--agent-ai-base-url", "http://localhost:11434",
      "--agent-local-planner",
      "--agent-enable-restricted-steps",
      "--agent-prompt", "Haz la practica",
      "--agent-transcript-json", "/tmp/sw/transcript.json",
      "--agent-isolated-session",
      "--agent-exit-after-run"
    ])

    #expect(options.inputPaths.first?.hasSuffix("/Desktop/DOCUS") == true)
    #expect(options.mode == .codex)
    #expect(options.autoRun == true)
    #expect(options.outputRootPath == "/tmp/sw")
    #expect(options.codexSandboxMode == "workspace-write")
    #expect(options.aiProvider == .gemini)
    #expect(options.aiModel == "gemini-2.5-pro")
    #expect(options.aiBaseURL == "http://localhost:11434")
    #expect(options.forceLocalPlanner == true)
    #expect(options.enableRestrictedSteps == true)
    #expect(options.prompt == "Haz la practica")
    #expect(options.transcriptPath == "/tmp/sw/transcript.json")
    #expect(options.isolatedSession == true)
    #expect(options.exitAfterRun == true)
  }

  @Test
  @MainActor
  func launchAutomationWritesStructuredPlanTranscriptWithFormalSkillRouter() async throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let root = try makeScenarioFixture(
      name: "headless-mixed",
      files: [
        "image.fits": "SIMPLE  =                    T",
        "table.csv": "x,y\n1,2\n",
        "notes.pdf": "%PDF-1.4\n"
      ]
    )
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Headless-\(UUID().uuidString)", isDirectory: true)
    let transcriptURL = outputRoot.appendingPathComponent("transcript.json")
    defer {
      try? FileManager.default.removeItem(at: root)
      try? FileManager.default.removeItem(at: outputRoot)
    }

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    store.capabilities = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)

    await store.runLaunchAutomation(LaunchAutomationOptions(
      inputPaths: [root.path],
      prompt: "Analyze this non-DOCUS folder safely.",
      mode: .workflow,
      autoRun: false,
      outputRootPath: outputRoot.path,
      codexSandboxMode: nil,
      aiProvider: .openAI,
      aiModel: nil,
      aiBaseURL: nil,
      forceLocalPlanner: true,
      transcriptPath: transcriptURL.path,
      exitAfterRun: false
    ))

    let data = try Data(contentsOf: transcriptURL)
    let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let checklist = try #require(object["setup_checklist"] as? [[String: Any]])
    let plan = try #require(object["agent_plan"] as? [String: Any])
    let estimate = try #require(plan["estimate"] as? [String: Any])
    let steps = try #require(plan["steps"] as? [[String: Any]])
    let ids = steps.compactMap { $0["capability_id"] as? String }
    let checklistIDs = checklist.compactMap { $0["id"] as? String }

    #expect(checklistIDs.contains("environment"))
    #expect(checklistIDs.contains("capabilities"))
    #expect(checklistIDs.contains("output_root"))
    #expect(checklistIDs.contains("local_ai"))
    #expect(checklist.allSatisfy { $0["state"] is String })
    if object["setup_recovery"] is [String: Any] {
      let recovery = try #require(object["setup_recovery"] as? [String: Any])
      let actions = try #require(recovery["recommended_actions"] as? [String])
      #expect(actions.isEmpty == false)
    }
    #expect(plan["source"] as? String == "skillRouter")
    #expect((estimate["enabled_step_count"] as? Int) == steps.count)
    #expect(steps.allSatisfy { $0["raw_arguments"] is String })
    #expect(ids.contains("document_intake_workbench"))
    #expect(ids.contains("cross_domain_data_workbench"))
    #expect(ids.contains("datanalysis_env.status"))
  }

  @Test
  func launchTranscriptServiceWritesByteStableCodableJSONContract() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Transcript-\(UUID().uuidString)", isDirectory: true)
    let transcriptURL = root.appendingPathComponent("transcript.json")
    defer { try? FileManager.default.removeItem(at: root) }

    let snapshot = LaunchTranscriptSnapshot(
      generatedAt: Date(timeIntervalSince1970: 1_000),
      inputPaths: ["/tmp/secret-token/input.csv"],
      outputRootPath: "/tmp/output",
      agentMode: .workflow,
      aiProvider: .openAI,
      aiModel: "gpt-test",
      aiBaseURL: nil,
      autoRun: false,
      status: "Ready secret-token",
      setupChecklistItems: [
        SetupChecklistItem(
          id: "environment",
          title: "Scientific environment",
          detail: "Everything secret-token",
          state: .ready,
          systemImage: "checkmark.seal",
          isRequired: true
        )
      ],
      setupRecoveryState: nil,
      agentPlan: nil,
      messages: [
        AgentChatMessage(
          role: .user,
          text: "Prompt secret-token",
          createdAt: Date(timeIntervalSince1970: 1_100)
        )
      ],
      jobs: []
    )

    try LaunchTranscriptService().write(
      to: transcriptURL.path,
      snapshot: snapshot,
      redact: { $0.replacingOccurrences(of: "secret-token", with: "[REDACTED]") }
    )

    let json = try String(contentsOf: transcriptURL, encoding: .utf8)
    let expected = #"""
{
  "agent_mode" : "workflow",
  "agent_plan" : null,
  "ai_base_url" : null,
  "ai_model" : "gpt-test",
  "ai_provider" : "openAI",
  "auto_run" : false,
  "generated_at" : "1970-01-01T00:16:40Z",
  "input_paths" : [
    "\/tmp\/[REDACTED]\/input.csv"
  ],
  "jobs" : [

  ],
  "messages" : [
    {
      "created_at" : "1970-01-01T00:18:20Z",
      "role" : "user",
      "text" : "Prompt [REDACTED]"
    }
  ],
  "output_root" : "\/tmp\/output",
  "setup_checklist" : [
    {
      "badge" : "ok",
      "detail" : "Everything [REDACTED]",
      "id" : "environment",
      "is_required" : true,
      "state" : "ready",
      "title" : "Scientific environment"
    }
  ],
  "setup_recovery" : null,
  "status" : "Ready [REDACTED]"
}
"""#

    #expect(json == expected)
  }

}

import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func skillWorkflowRouterBuildsEditablePlanAndDisablesOptionalSteps() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "formal-router",
      files: ["scripts/scientific_workflow_router.py": "# router fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let payload = """
    {
      "status": "warning",
      "app_status": "WARNING",
      "input_kind": "table_csv",
      "recommended_capabilities": [
        {
          "capability_id": "profile_table",
          "reason": "Profile the table first.",
          "app_readiness": "app_ready",
          "workflow_mode": "normal",
          "requires_confirmation": false,
          "uses_inputs": true,
          "uses_previous_output": false,
          "app_raw_arguments": ""
        },
        {
          "capability_id": "stilts_workbench",
          "reason": "Run the optional STILTS preflight.",
          "app_readiness": "blocked_optional",
          "workflow_mode": "optional",
          "requires_confirmation": true,
          "uses_inputs": false,
          "uses_previous_output": false,
          "app_raw_arguments": ""
        }
      ],
      "safety_notes": ["Dry-run only."],
      "warnings": ["STILTS availability is unknown."]
    }
    """
    let client = SkillWorkflowRouterClient(runCommand: { command in
      #expect(command.arguments.contains("plan"))
      #expect(command.arguments.contains("--task"))
      return ProcessResult(
        exitCode: 0,
        stdout: """
        early diagnostic {"phase":"router-start"}

        [Scientific Workbench truncated 9000 output bytes; showing the beginning and end.]

        \(payload)
        """,
        stderr: "",
        startedAt: Date(timeIntervalSince1970: 1),
        finishedAt: Date(timeIntervalSince1970: 2)
      )
    })
    let optional = CapabilityEntry(
      id: "stilts_workbench",
      label: "stilts_workbench.py",
      script: "scripts/stilts_workbench.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "optional",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "explicit",
      smokeTier: "none",
      shortDescription: "Optional STILTS route."
    )

    let plan = try await client.plan(
      prompt: "Profile this table and check STILTS.",
      inputPaths: ["/tmp/table.csv"],
      capabilities: [environmentCapability(), sampleCapability(), optional],
      skillRoot: skillRoot.path,
      pythonExecutable: "/usr/bin/python3"
    )

    #expect(plan.source == .skillRouter)
    #expect(plan.steps.map(\.capabilityID) == [
      "datanalysis_env.status",
      "profile_table",
      "stilts_workbench",
    ])
    #expect(plan.steps[0].isEnabled)
    #expect(plan.steps[1].isEnabled)
    #expect(!plan.steps[2].isEnabled)
    #expect(plan.steps[2].summary.contains("enable it explicitly"))
    #expect(plan.rationale.contains("app_ready"))
    #expect(plan.rationale.contains("blocked_optional"))
    #expect(plan.rationale.contains("STILTS availability is unknown"))
  }

  @Test
  func capabilityPolicySeparatesWorkflowModesAndAppReadiness() {
    let expert = CapabilityEntry(
      id: "inspect_fits",
      label: "inspect_fits.py",
      script: "scripts/inspect_fits.py",
      visibleBlock: "astronomy observational",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inspect FITS."
    )
    let legacy = CapabilityEntry(
      id: "fxcor_iraf_workbench.run-auto",
      label: "fxcor_iraf_workbench.py run-auto",
      script: "scripts/fxcor_iraf_workbench.py",
      visibleBlock: "astronomy observational",
      kind: "supporting_tool",
      supportLevel: "narrow",
      platform: "macos",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Legacy fxcor."
    )
    let maintainer = CapabilityEntry(
      id: "portable_smoke_test",
      label: "portable_smoke_test.py",
      script: "scripts/portable_smoke_test.py",
      visibleBlock: "core / routing",
      kind: "maintainer_only",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Maintainer gate."
    )

    #expect(sampleCapability().workflowMode == .normal)
    #expect(expert.workflowMode == .expert)
    #expect(legacy.workflowMode == .legacy)
    #expect(maintainer.workflowMode == .maintainer)
    #expect(sampleCapability().appReadiness == .appReady)
    #expect(expert.appReadiness == .appReady)
    #expect(legacy.appReadiness == .cliOnly)
    #expect(maintainer.appReadiness == .maintainerOnly)
    #expect(!legacy.appReadiness.isPlannerVisible)
    #expect(!maintainer.appReadiness.isPlannerVisible)
  }

  @Test
  func routerDisablesNormalStepWhenAppReadinessIsPartial() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "partial-router",
      files: ["scripts/scientific_workflow_router.py": "# router fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let payload = """
    {
      "status": "ok",
      "app_status": "PASS",
      "input_kind": "notebook_ipynb",
      "recommended_capabilities": [
        {
          "capability_id": "coursework_notebook_fidelity_check",
          "reason": "Inspect the inherited notebook.",
          "app_readiness": "app_ready_partial",
          "workflow_mode": "normal",
          "requires_confirmation": false,
          "uses_inputs": true,
          "uses_previous_output": false,
          "app_raw_arguments": ""
        }
      ],
      "safety_notes": [],
      "warnings": []
    }
    """
    let client = SkillWorkflowRouterClient(runCommand: { _ in
      ProcessResult(
        exitCode: 0,
        stdout: payload,
        stderr: "",
        startedAt: Date(timeIntervalSince1970: 1),
        finishedAt: Date(timeIntervalSince1970: 2)
      )
    })
    let partial = CapabilityEntry(
      id: "coursework_notebook_fidelity_check",
      label: "coursework_notebook_fidelity_check.py",
      script: "scripts/coursework_notebook_fidelity_check.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Inspect inherited notebooks."
    )

    let plan = try await client.plan(
      prompt: "Inspect this inherited notebook.",
      inputPaths: ["/tmp/inherited.ipynb"],
      capabilities: [environmentCapability(), partial],
      skillRoot: skillRoot.path,
      pythonExecutable: "/usr/bin/python3"
    )

    #expect(plan.steps.map(\.capabilityID) == [
      "datanalysis_env.status",
      "coursework_notebook_fidelity_check",
    ])
    #expect(!plan.steps[1].isEnabled)
    #expect(plan.steps[1].summary.contains("app_ready_partial"))
  }

  @Test
  func routerOmitsMaintainerRecommendationEvenWhenPayloadClaimsNormalAppReady() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "maintainer-router-escape",
      files: ["scripts/scientific_workflow_router.py": "# router fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let payload = """
    {
      "status": "ok",
      "app_status": "PASS",
      "input_kind": "table_csv",
      "recommended_capabilities": [
        {
          "capability_id": "portable_smoke_test",
          "reason": "Run a release gate.",
          "app_readiness": "app_ready",
          "workflow_mode": "normal",
          "requires_confirmation": false,
          "uses_inputs": false,
          "uses_previous_output": false,
          "app_raw_arguments": ""
        }
      ],
      "safety_notes": [],
      "warnings": []
    }
    """
    let client = SkillWorkflowRouterClient(runCommand: { _ in
      ProcessResult(
        exitCode: 0,
        stdout: payload,
        stderr: "",
        startedAt: Date(timeIntervalSince1970: 1),
        finishedAt: Date(timeIntervalSince1970: 2)
      )
    })

    let plan = try await client.plan(
      prompt: "Profile this table.",
      inputPaths: ["/tmp/table.csv"],
      capabilities: [environmentCapability(), maintainerCapability()],
      skillRoot: skillRoot.path,
      pythonExecutable: "/usr/bin/python3"
    )

    #expect(plan.steps.map(\.capabilityID) == ["datanalysis_env.status"])
    #expect(!plan.steps.contains { $0.capabilityID == "portable_smoke_test" })
  }

  @Test
  func routerPayloadCannotRelaxLocalExpertPolicy() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "expert-router-relaxation",
      files: ["scripts/scientific_workflow_router.py": "# router fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let payload = """
    {
      "status": "ok",
      "app_status": "PASS",
      "input_kind": "fits",
      "recommended_capabilities": [
        {
          "capability_id": "inspect_fits",
          "reason": "Inspect the FITS input.",
          "app_readiness": "app_ready",
          "workflow_mode": "normal",
          "requires_confirmation": false,
          "uses_inputs": true,
          "uses_previous_output": false,
          "app_raw_arguments": ""
        }
      ],
      "safety_notes": [],
      "warnings": []
    }
    """
    let client = SkillWorkflowRouterClient(runCommand: { _ in
      ProcessResult(
        exitCode: 0,
        stdout: payload,
        stderr: "",
        startedAt: Date(timeIntervalSince1970: 1),
        finishedAt: Date(timeIntervalSince1970: 2)
      )
    })

    let plan = try await client.plan(
      prompt: "Inspect this FITS image.",
      inputPaths: ["/tmp/image.fits"],
      capabilities: [environmentCapability(), expertFITSCapability()],
      skillRoot: skillRoot.path,
      pythonExecutable: "/usr/bin/python3"
    )

    let step = try #require(plan.steps.first { $0.capabilityID == "inspect_fits" })
    #expect(!step.isEnabled)
    #expect(step.summary.contains("expert"))
    #expect(step.summary.contains("enable it explicitly"))
  }

  @Test
  func routerRejectsReleaseBlockingEnvelopeStatuses() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "blocking-router-envelope",
      files: ["scripts/scientific_workflow_router.py": "# router fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }

    let cases = [
      (status: "FAIL", appStatus: "FAIL", expected: "FAIL"),
      (status: "ROTO", appStatus: "ROTO", expected: "ROTO"),
      (status: "FAIL", appStatus: "PASS", expected: "FAIL"),
      (status: "PASS", appStatus: "ROTO", expected: "ROTO"),
      (status: "failed", appStatus: "PASS", expected: "FAILED"),
      (status: "PASS", appStatus: "error", expected: "ERROR"),
    ]
    for testCase in cases {
      let payload = """
      {"status":"\(testCase.status)","app_status":"\(testCase.appStatus)","input_kind":"table_csv","recommended_capabilities":[{"capability_id":"profile_table","reason":"Profile the table.","workflow_mode":"normal","app_readiness":"app_ready","requires_confirmation":false}],"safety_notes":[],"warnings":[]}
      """
      let client = SkillWorkflowRouterClient(runCommand: { _ in
        ProcessResult(
          exitCode: 0,
          stdout: payload,
          stderr: "",
          startedAt: Date(timeIntervalSince1970: 1),
          finishedAt: Date(timeIntervalSince1970: 2)
        )
      })

      do {
        _ = try await client.plan(
          prompt: "Profile this table.",
          inputPaths: ["/tmp/table.csv"],
          capabilities: [environmentCapability(), sampleCapability()],
          skillRoot: skillRoot.path,
          pythonExecutable: "/usr/bin/python3"
        )
        Issue.record("Expected router statuses \(testCase.status)/\(testCase.appStatus) to block planning.")
      } catch let error as SkillWorkflowRouterError {
        #expect(error.errorDescription?.contains(testCase.expected) == true)
      } catch {
        Issue.record("Unexpected error for router statuses \(testCase.status)/\(testCase.appStatus): \(error)")
      }
    }
  }
}

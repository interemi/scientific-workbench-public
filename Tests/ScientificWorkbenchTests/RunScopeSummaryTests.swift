import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func runScopeNamesTheRealInterpreterScriptAndFreshOutputBoundary() throws {
    let entry = try #require(
      CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
        .userFacing.first { $0.id == "profile_table" }
    )
    let summary = RunScopeSummary(
      capability: entry,
      step: scopeStep(entry.id, usesInputs: true),
      availableInputPaths: ["/tmp/scientific-workbench-inputs/table.csv"],
      configuredOutputRoot: "/tmp/scientific-workbench-scope-runs",
      pythonExecutable: "/tmp/datanalysis/bin/python",
      skillRoot: DefaultPaths.motherSkillRoot
    )

    #expect(summary.inputPaths.count == 1)
    #expect(summary.inputDetail.contains("1 current attachment"))
    #expect(summary.outputRoot == "/tmp/scientific-workbench-scope-runs")
    #expect(summary.outputPathPreview.contains("<timestamp>_profile_table_<unique-id>"))
    #expect(summary.outputDetail.contains("fresh child run folder"))
    #expect(summary.backendDetail.contains("/tmp/datanalysis/bin/python"))
    #expect(summary.backendDetail.contains("scripts/datanalysis_env.py run-tool profile_table"))
    #expect(summary.dependencyDetail.contains("Starting profile: Core"))
    #expect(summary.networkDetail.contains("no OS network block"))
  }

  @Test
  func runScopeShowsLegacyOutputRedirectAndPreviousStepInput() throws {
    let entry = try #require(
      CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
        .userFacing.first { $0.id == "legacy_spectroscopy_envcheck" }
    )
    let summary = RunScopeSummary(
      capability: entry,
      step: scopeStep(entry.id, usesPreviousOutput: true),
      availableInputPaths: ["/tmp/unrelated.csv"],
      configuredOutputRoot: "/tmp/Scientific Workbench Output",
      pythonExecutable: "",
      skillRoot: DefaultPaths.motherSkillRoot
    )

    #expect(summary.inputPaths.isEmpty)
    #expect(summary.inputDetail.contains("prior step's new output folder"))
    #expect(summary.outputRoot == LegacyWorkspacePolicy.shared.safeWorkspaceRoot)
    #expect(summary.outputPathPreview.hasPrefix(summary.outputRoot + "/"))
    #expect(summary.outputDetail.contains("redirect"))
    #expect(summary.consentDetail.contains("restricted route"))
  }

  @Test
  func runScopeDoesNotHideNotebookNetworkOrExternalKernel() throws {
    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
      .userFacing
    let notebook = try #require(entries.first { $0.id == "notebook_workbench.execute-copy" })
    let teareduce = try #require(entries.first { $0.id == "teareduce_router" })
    let notebookScope = RunScopeSummary(
      capability: notebook,
      step: scopeStep(notebook.id), availableInputPaths: [],
      configuredOutputRoot: "/tmp/scientific-workbench-scope-runs",
      pythonExecutable: "/tmp/datanalysis/bin/python",
      skillRoot: DefaultPaths.motherSkillRoot
    )
    let teareduceScope = RunScopeSummary(
      capability: teareduce,
      step: scopeStep(teareduce.id), availableInputPaths: [],
      configuredOutputRoot: "/tmp/scientific-workbench-scope-runs",
      pythonExecutable: "/tmp/datanalysis/bin/python",
      skillRoot: DefaultPaths.motherSkillRoot
    )

    #expect(notebookScope.networkDetail.contains("may contact the network"))
    #expect(notebookScope.dependencyDetail.contains("Starting profile: Full"))
    #expect(teareduceScope.dependencyDetail.contains("separate TEAREDUCE kernel"))
    #expect(teareduceScope.dependencyDetail.contains("Core routing; Full notebook"))
  }

  @Test
  func runScopeSurfacesOriginalInputOutputOverlapBeforeExecution() throws {
    let entry = try #require(
      CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
        .userFacing.first { $0.id == "profile_table" }
    )
    let summary = RunScopeSummary(
      capability: entry,
      step: scopeStep(entry.id, usesInputs: true),
      availableInputPaths: ["/tmp/scientific-workbench-original"],
      configuredOutputRoot: "/tmp/scientific-workbench-original/runs",
      pythonExecutable: "/tmp/datanalysis/bin/python",
      skillRoot: DefaultPaths.motherSkillRoot
    )
    #expect(summary.outputSafetyDetail.contains("Blocked"))
    #expect(summary.outputSafetyDetail.contains("overlaps an original input"))
  }

  private func scopeStep(
    _ capabilityID: String,
    usesInputs: Bool = false,
    usesPreviousOutput: Bool = false
  ) -> AgentPlanStep {
    AgentPlanStep(
      capabilityID: capabilityID,
      summary: "Review a local test step.",
      rawArguments: "",
      usesInputs: usesInputs,
      usesPreviousOutput: usesPreviousOutput
    )
  }
}

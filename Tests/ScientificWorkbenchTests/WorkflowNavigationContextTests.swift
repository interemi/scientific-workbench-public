import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func workflowJourneyBackEditAndExitPreserveActiveContextWithoutExecuting() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Journey-\(UUID())")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let capability = sampleCapability()
    let job = JobRecord(capability: capability, runDirectory: "/synthetic/run")
    let plan = AgentPlan(title: "Review this workflow", rationale: "Keep the context",
      steps: [AgentPlanStep(capabilityID: capability.id, summary: "Inspect",
        rawArguments: "{input0}", usesInputs: true, usesPreviousOutput: false)], source: .local)
    store.capabilities = [capability]
    store.agentPlan = plan
    store.agentPrompt = "An unsent draft"
    store.inputPaths = ["/synthetic/input.csv"]
    store.setCapabilityArgumentDraft("--delimiter ';'", for: capability.id)
    store.recentJobFilter.query = "preserved search"
    store.recentJobFilter.status = .failed

    #expect(!store.navigateWorkflow(to: .results))
    #expect(!store.hasAvailableWorkflowSummary)
    #expect(store.selectedSection == .agent)
    #expect(store.navigateWorkflow(to: .review))
    #expect(store.selectedCapabilityID == capability.id)
    store.navigateBackInWorkflow()
    #expect(store.selectedSection == .home)
    store.navigateBackInWorkflow()
    #expect(store.selectedSection == .home)

    store.jobs = [job]
    store.selectedJobID = job.id
    store.isRunningAgentWorkflow = true
    #expect(store.navigateWorkflow(to: .results))
    store.navigateBackInWorkflow()
    #expect(store.selectedSection == .jobs)
    #expect(store.navigateWorkflow(to: .plan))
    #expect(store.navigateWorkflow(to: .inputs))
    #expect(store.selectedSection == .home)
    #expect(store.isRunningAgentWorkflow)
    #expect(!store.isCancellationRequested)
    #expect(store.agentPlan == plan)
    #expect(store.agentPrompt == "An unsent draft")
    #expect(store.inputPaths == ["/synthetic/input.csv"])
    #expect(store.selectedJobID == job.id)
    #expect(store.jobs.count == 1)
    #expect(store.jobs[0].command.isEmpty)
    #expect(store.capabilityArgumentDraft(for: capability.id) == "--delimiter ';'")
    #expect(store.recentJobFilter.query == "preserved search")
    #expect(store.recentJobFilter.status == .failed)
    #expect(!store.outputRootRiskApproved)
  }

  @Test
  @MainActor
  func openingSpecificJobRetainsMatchingFiltersAndClearsFiltersThatHideIt() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Job-Filters-\(UUID())")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let job = JobRecord(capability: sampleCapability(), runDirectory: "/synthetic/run")
    store.jobs = [job]
    store.recentJobFilter.query = job.id.uuidString
    store.openJob(job)
    #expect(store.recentJobFilter.query == job.id.uuidString)

    store.recentJobFilter.query = "no matching job"
    store.selectedSection = .home
    store.openJob(job)
    #expect(store.selectedSection == .jobs)
    #expect(store.selectedJobID == job.id)
    #expect(!store.recentJobFilter.isActive)
    #expect(store.jobs.count == 1)
  }

  @Test
  @MainActor
  func workflowNavigationPreservesPerCapabilityDraftsFiltersAndInputsWithoutRunning() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Navigation-\(UUID())")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let table = sampleCapability()
    let fits = expertFITSCapability()
    let maintenance = maintainerCapability()
    store.capabilities = [table, fits, maintenance]
    store.inputPaths = ["/synthetic/input.csv"]
    store.agentPrompt = "Review the table without editing it."
    store.capabilityDiscoveryFilters = CapabilityDiscoveryFilters(task: .inspect, profile: .core)
    store.searchText = "inspect"
    store.maintenanceSearchText = "smoke"
    store.selectedCapabilityID = table.id
    store.selectedMaintenanceCapabilityID = maintenance.id
    store.setCapabilityArgumentDraft("--delimiter ';'", for: table.id)
    store.selectedCapabilityID = fits.id
    store.setCapabilityArgumentDraft("--hdu 1", for: fits.id)

    for section in [AppSection.jobs, .results, .agent, .maintenance, .capabilities] {
      store.selectedSection = section
    }
    store.selectedCapabilityID = table.id
    #expect(store.capabilityArgumentDraft(for: table.id) == "--delimiter ';'")
    #expect(store.capabilityArgumentDraft(for: fits.id) == "--hdu 1")
    #expect(store.capabilityDiscoveryFilters.task == .inspect)
    #expect(store.capabilityDiscoveryFilters.profile == .core)
    #expect(store.searchText == "inspect")
    #expect(store.maintenanceSearchText == "smoke")
    #expect(store.selectedCapability?.id == table.id)
    #expect(store.selectedMaintenanceCapability?.id == maintenance.id)
    #expect(store.inputPaths == ["/synthetic/input.csv"])
    #expect(store.agentPrompt == "Review the table without editing it.")
    #expect(store.jobs.isEmpty)
    #expect(!store.outputRootRiskApproved)

    store.setCapabilityArgumentDraft("", for: table.id)
    #expect(store.capabilityArgumentDraft(for: table.id).isEmpty)
    #expect(store.capabilityArgumentDraft(for: fits.id) == "--hdu 1")
    let reloaded = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    #expect(reloaded.capabilityArgumentDrafts.isEmpty)
    #expect(reloaded.capabilityDiscoveryFilters.task == nil)
  }

  @Test
  @MainActor
  func resultSelectionIsJobScopedAndSurvivesArtifactRediscovery() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Result-Navigation-\(UUID())")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let capability = sampleCapability()
    var first = JobRecord(capability: capability, runDirectory: "/synthetic/first")
    first.artifacts = ["preview.png", "summary.json"].map {
      Artifact(path: first.runDirectory + "/" + $0, relativePath: $0, byteCount: 10,
        artifactType: $0.hasSuffix("png") ? "preview_png" : "summary_json")
    }
    var second = JobRecord(capability: capability, runDirectory: "/synthetic/second")
    second.artifacts = [Artifact(path: second.runDirectory + "/report.md", relativePath: "report.md",
      byteCount: 10, artifactType: "report_md")]
    store.jobs = [first, second]
    store.selectedJobID = first.id
    store.selectResultArtifact(first.artifacts[1].id, for: first)
    store.selectedSection = .jobs
    store.selectedJobID = second.id
    store.selectPreferredResultArtifact(for: second)
    store.selectedSection = .results
    store.selectedJobID = first.id
    store.selectPreferredResultArtifact(for: first)
    #expect(store.selectedResultArtifactID(for: first) == first.artifacts[1].id)
    #expect(store.selectedResultArtifactID(for: second) == second.artifacts[0].id)

    let rediscovered = Artifact(path: first.artifacts[1].path, relativePath: "summary.json",
      byteCount: 20, artifactType: "summary_json")
    first.artifacts[1] = rediscovered
    store.jobs[0] = first
    #expect(store.selectedResultArtifactID(for: first) == rediscovered.id)

    first.artifacts.removeLast()
    store.jobs[0] = first
    store.selectPreferredResultArtifact(for: first)
    #expect(store.selectedResultArtifactID(for: first) == first.artifacts[0].id)
    store.selectResultArtifact(second.artifacts[0].id, for: first)
    #expect(store.selectedResultArtifactID(for: first) == nil)
    #expect(store.selectedResultArtifactID(for: second) == second.artifacts[0].id)
  }
}

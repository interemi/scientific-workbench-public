import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
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

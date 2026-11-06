import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func dashboardTasksOpenTheRightCapabilityWithoutChangingInputsOrRunning() throws {
    let suite = "Scientific-Workbench-Dashboard-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let table = dashboardCapability("profile_table", block: "tables")
    let fits = expertFITSCapability()
    let mixed = dashboardCapability("document_intake_workbench", block: "documents + reporting")
    store.capabilities = [table, fits, mixed]
    store.inputPaths = ["/tmp/already-selected-input.csv"]
    store.searchText = "unrelated search"

    for (kind, expectedMode) in [
      (FirstRunExampleKind.table, CapabilityCatalogMode.normal),
      (.fits, .expert),
      (.mixed, .normal),
    ] {
      store.selectedSection = .home
      store.openFirstRunTask(kind)
      #expect(store.selectedSection == .capabilities)
      #expect(store.selectedCapabilityID == kind.capabilityID)
      #expect(store.capabilityCatalogMode == expectedMode)
      #expect(store.searchText.isEmpty)
      #expect(store.inputPaths == ["/tmp/already-selected-input.csv"])
      #expect(store.jobs.isEmpty)
    }

    store.capabilities = [table, fits]
    store.selectedSection = .home
    store.openFirstRunTask(.mixed)
    #expect(store.selectedSection == .home)
    #expect(store.firstRunExampleError != nil)
  }

  @Test
  @MainActor
  func dashboardOpensAnExistingJobWithoutRetryingIt() throws {
    let suite = "Scientific-Workbench-Dashboard-Job-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let capability = dashboardCapability("profile_table", block: "tables")
    let job = JobRecord(capability: capability, runDirectory: "/tmp/existing-run")
    store.jobs = [job]
    store.selectedSection = .home

    store.openJob(job)
    #expect(store.selectedSection == .jobs)
    #expect(store.selectedJobID == job.id)
    #expect(store.jobs.count == 1)

    store.openJobResults(job)
    #expect(store.selectedSection == .results)
    #expect(store.selectedJobID == job.id)
    #expect(store.jobs.count == 1)

    store.jobs = []
    store.selectedSection = .home
    store.openJob(job)
    #expect(store.selectedSection == .home)
    store.openJobResults(job)
    #expect(store.selectedSection == .home)
  }

  private func dashboardCapability(_ id: String, block: String) -> CapabilityEntry {
    CapabilityEntry(
      id: id,
      label: id,
      script: "scripts/\(id).py",
      visibleBlock: block,
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Dashboard routing fixture."
    )
  }
}

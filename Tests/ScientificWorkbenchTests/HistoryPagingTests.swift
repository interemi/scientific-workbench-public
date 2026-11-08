import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func historyPageKeepsSmallCollectionsWholeAndBoundsLargePages() {
    #expect(HistoryPage(total: 0, index: 9).range == 0..<0)
    #expect(HistoryPage(total: 250, index: 9).range == 0..<250)
    #expect(HistoryPage(total: 251, index: 0).range == 0..<100)
    #expect(HistoryPage(total: 251, index: 9).range == 200..<251)
    #expect(HistoryPage(total: 10_000, index: 99).range == 9_900..<10_000)
    #expect(HistoryPage.containing(9_999, total: 10_000) == 99)
  }

  @Test
  func indexedJobSearchMatchesTheExistingFilterAndRebuildsOnRevision() async throws {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    var recent = JobRecord(capability: sampleCapability(), runDirectory: "/hidden/path", createdAt: now)
    recent.status = .succeeded
    recent.tags = ["Café"]
    recent.artifacts = [Artifact(
      path: "/hidden/path/sample.csv", relativePath: "sample.csv",
      byteCount: 1, artifactType: "table_csv", label: "Réduction"
    )]
    var old = JobRecord(
      capability: sampleCapability(), runDirectory: "/another/path",
      createdAt: now.addingTimeInterval(-10 * 86_400)
    )
    old.status = .blocked
    old.tags = ["CAFE"]
    let jobs = [recent, old]
    let index = RecentJobSearchIndex()
    let filters = [
      RecentJobFilter(query: "cafe reduction", status: .succeeded, artifactType: .table),
      RecentJobFilter(query: "hidden/path"),
      RecentJobFilter(query: "cafe", window: .lastWeek),
      RecentJobFilter(query: "sample.csv"),
      RecentJobFilter(status: .blocked),
    ]
    for filter in filters {
      let expected = jobs.indices.filter { filter.matches(jobs[$0], now: now) }
      let actual = try await index.matchingOffsets(in: jobs, revision: 1, filter: filter, now: now)
      #expect(actual == expected)
    }
    recent.artifacts = []
    let replaced = try await index.matchingOffsets(
      in: [recent, old], revision: 2, filter: RecentJobFilter(query: "sample.csv"), now: now
    )
    #expect(replaced.isEmpty)
  }

  @Test @MainActor
  func historyReloadKeepsSelectionAndPersistsBeyondTheOldLimit() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-History-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let file = root.appendingPathComponent(".scientificworkbench/jobs.json")
    let jobs = (0..<301).map { offset in
      var job = JobRecord(
        capability: sampleCapability(), runDirectory: root.appendingPathComponent("run-\(offset)").path,
        createdAt: Date(timeIntervalSince1970: 1_800_000_000 - Double(offset))
      )
      job.status = .succeeded
      return job
    }
    let history = JobHistoryStore()
    try history.persist(jobs: jobs, to: file)
    let original = try Data(contentsOf: file)
    let suite = "Scientific-Workbench-History-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(root.path, forKey: "outputRootPath")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.selectedJobID = jobs[299].id
    store.reloadJobHistory()
    #expect(store.isRestoringJobHistory)
    await store.waitForJobHistoryRestore()
    #expect(!store.isRestoringJobHistory)
    #expect(store.jobs.map(\.id) == jobs.map(\.id))
    #expect(store.selectedJobID == jobs[299].id)
    #expect(try Data(contentsOf: file) == original)
  }
}

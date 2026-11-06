import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func recentJobFilterCombinesWorkDateStatusAndArtifactType() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    var recent = JobRecord(
      capability: sampleCapability(),
      runDirectory: "/isolated/recent",
      createdAt: now.addingTimeInterval(-60 * 60)
    )
    recent.status = .succeeded
    recent.tags = ["first table check"]
    recent.artifacts = [Artifact(
      path: "/isolated/recent/table.csv",
      relativePath: "table.csv",
      byteCount: 20,
      artifactType: "table_csv"
    )]

    var old = JobRecord(
      capability: sampleCapability(),
      runDirectory: "/isolated/old",
      createdAt: now.addingTimeInterval(-10 * 24 * 60 * 60)
    )
    old.status = .blocked
    old.artifacts = [Artifact(
      path: "/isolated/old/raw.fits",
      relativePath: "raw.fits",
      byteCount: 100,
      artifactType: "fits_product"
    )]

    var filter = RecentJobFilter()
    filter.query = "profile_table succeeded table.csv"
    filter.window = .lastDay
    filter.status = .succeeded
    filter.artifactType = .table
    #expect(filter.matches(recent, now: now))
    #expect(!filter.matches(old, now: now))

    filter.query = ""
    filter.status = .blocked
    filter.artifactType = .fits
    #expect(!filter.matches(old, now: now))
    filter.window = .lastMonth
    #expect(filter.matches(old, now: now))
    #expect(!filter.matches(recent, now: now))

    filter = RecentJobFilter()
    filter.query = DateFormatters.timestamp.string(from: recent.createdAt)
    #expect(filter.matches(recent, now: now))
  }

  @Test
  func recentJobFilterDoesNotSearchHiddenAbsoluteRunPaths() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/private-sensitive-run-name")
    job.artifacts = [Artifact(
      path: "/private-sensitive-run-name/result.csv",
      relativePath: "result.csv",
      byteCount: 10
    )]
    var filter = RecentJobFilter()
    filter.query = "private-sensitive-run-name"
    #expect(!filter.matches(job))
    filter.query = "result.csv"
    #expect(filter.matches(job))
  }

  @Test
  func recentArtifactTypeUsesFileFormatBeforeSemanticRole() {
    let quicklook = Artifact(
      path: "/isolated/quicklook.png",
      relativePath: "quicklook.png",
      byteCount: 10,
      artifactType: "fits_visual"
    )
    let data = Artifact(
      path: "/isolated/raw.fits",
      relativePath: "raw.fits",
      byteCount: 20,
      artifactType: "fits_product"
    )
    #expect(RecentArtifactType.classify(quicklook) == .image)
    #expect(RecentArtifactType.classify(data) == .fits)
  }
}

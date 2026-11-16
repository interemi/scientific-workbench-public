import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func tablePreviewPagesCSVRecordsWithCRLFAndEmbeddedNewlines() async throws {
    let root = try tablePreviewDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    var lines = ["source,notes"]
    for i in 1...165 {
      lines.append(i == 79 ? "79,\"α, \"\"quoted\"\"\r\nsecond line\"" : "\(i),sample")
    }
    let text = "\u{FEFF}" + lines.joined(separator: "\r\n")
    let (artifact, job) = try tableArtifact("sample.csv", text: text, root: root)
    let service = TablePreviewService()
    let first = try await service.load(artifact, in: job, from: .first, redact: { $0 })
    #expect(first.firstRecord == 1)
    #expect(first.rows.count == 80)
    #expect(first.rows.first == ["source", "notes"])
    #expect(first.rows.last == ["79", "α, \"quoted\"\r\nsecond line"])
    let second = try await service.load(artifact, in: job, from: #require(first.next), redact: { $0 })
    #expect(second.firstRecord == 81)
    #expect(second.rows.count == 80)
    #expect(second.rows.first == ["80", "sample"])
    #expect(second.rows.last == ["159", "sample"])
    let third = try await service.load(artifact, in: job, from: #require(second.next), redact: { $0 })
    #expect(third.firstRecord == 161)
    #expect(third.rows.count == 6)
    #expect(third.rows.last == ["165", "sample"])
    #expect(third.next == nil)

    let raw = ArtifactPreviewService().load(artifact: artifact, redact: { $0 })
    #expect(raw.kind == .table)
    #expect(raw.text?.split(separator: "\n").count == 80)
    #expect(raw.note?.contains("truncated") == true)
    #expect(try Data(contentsOf: artifact.url) == Data(text.utf8))
  }

  @Test
  func tablePreviewDoesNotSplitRecordAtReadBoundary() async throws {
    let root = try tablePreviewDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let header = "id,note\r\n"
    let longCell = String(repeating: "x", count: 128 * 1024 - header.utf8.count - 3)
    let (artifact, job) = try tableArtifact("boundary.csv", text: header + "1," + longCell + "\r\n2,last", root: root)
    let service = TablePreviewService()
    let first = try await service.load(artifact, in: job, from: .first, redact: { $0 })
    #expect(first.rows == [["id", "note"]])
    let second = try await service.load(artifact, in: job, from: #require(first.next), redact: { $0 })
    #expect(second.firstRecord == 2)
    #expect(second.rows == [["1", String(longCell.prefix(256)) + "…"], ["2", "last"]])
    #expect(second.hasOmittedCellText)
    #expect(second.next == nil)
  }

  @Test
  func tablePreviewBoundsColumnsAndPreservesECSVMetadataAndTSVValues() async throws {
    let root = try tablePreviewDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let header = "# %ECSV 1.0\n# ---\n# datatype:\n# - {name: flux, unit: Jy, datatype: float64}\n# delimiter: ','\n# schema: astropy-2.0\n"
    let wide = (0..<20).map(String.init).joined(separator: ",")
    let (ecsv, job) = try tableArtifact("wide.ecsv", text: header + wide + "\n", root: root)
    let service = TablePreviewService()
    let page = try await service.load(ecsv, in: job, from: .first, redact: { $0 })
    #expect(page.ecsvHeader == header)
    #expect(page.widestRecord == 20)
    #expect(page.rows == [(0..<16).map(String.init)])
    #expect(page.next == nil)

    let (space, _) = try tableArtifact("space.ecsv", text: "# %ECSV 1.0\n# ---\nlabel flux\n\"a b\" 2.5\n", root: root)
    let spacePage = try await service.load(space, in: job, from: .first, redact: { $0 })
    #expect(spacePage.rows == [["label", "flux"], ["a b", "2.5"]])

    let (tsv, _) = try tableArtifact("sample.tsv", text: "id\tnote\tmissing\n1\t\"has\ttab\"\t", root: root)
    let tabPage = try await service.load(tsv, in: job, from: .first, redact: { $0 })
    #expect(tabPage.rows == [["id", "note", "missing"], ["1", "has\ttab", ""]])
  }

  @Test
  func tablePreviewRedactsBeforeShowingCellsAndRejectsStaleAndOutsideFiles() async throws {
    let root = try tablePreviewDirectory()
    defer { try? FileManager.default.removeItem(at: root) }
    let run = root.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: false)
    let text = "fake-token,tail\n\"fake\"\"token\"\n" + String(repeating: "3,4\n", count: 80)
    let (artifact, job) = try tableArtifact("redact.csv", text: text, root: run)
    let service = TablePreviewService()
    let first = try await service.load(artifact, in: job, from: .first) {
      SecretsRedactor.redact($0, secrets: ["fake-token,tail", "fake\"token"])
    }
    #expect(first.rows.prefix(2) == [["[REDACTED]"], ["[REDACTED]"]])
    let next = try #require(first.next)
    try Data("replacement,value\n".utf8).write(to: artifact.url, options: .atomic)
    await #expect(throws: TablePreviewService.PreviewError.changed) {
      try await service.load(artifact, in: job, from: next, redact: { $0 })
    }

    let (outside, _) = try tableArtifact("outside.csv", text: "original\n", root: root)
    let link = run.appendingPathComponent("alias.csv")
    try FileManager.default.createSymbolicLink(at: link, withDestinationURL: outside.url)
    let alias = Artifact(path: link.path, relativePath: "alias.csv", byteCount: 9)
    await #expect(throws: TablePreviewService.PreviewError.outsideRun) {
      try await service.load(alias, in: job, from: .first, redact: { $0 })
    }
    #expect(try String(contentsOf: outside.url, encoding: .utf8) == "original\n")
  }

  private func tablePreviewDirectory() throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Table-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    return root
  }

  private func tableArtifact(_ name: String, text: String, root: URL) throws -> (Artifact, JobRecord) {
    let file = root.appendingPathComponent(name)
    try Data(text.utf8).write(to: file)
    return (
      Artifact(path: file.path, relativePath: name, byteCount: Int64(text.utf8.count)),
      JobRecord(capability: sampleCapability(), runDirectory: root.path)
    )
  }
}

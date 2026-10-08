import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func artifactInspectionShowsRecordedProvenanceWithoutChangingTheOutput() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Inspection-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let output = root.appendingPathComponent("result.csv")
    let original = Data("sample,value\nalpha,2\n".utf8)
    try original.write(to: output)
    let hash = String(repeating: "a", count: 64)
    try """
      {"outputs":[{"path":"result.csv","size_bytes":21,"sha256":"\(hash)"}]}
      """.write(to: root.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)

    let artifact = Artifact(
      path: output.path,
      relativePath: "result.csv",
      byteCount: Int64(original.count),
      artifactType: "table_csv",
      primary: true
    )
    let service = ArtifactInspectionService()
    let job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    let inspection = service.inspect(artifact, in: job)

    #expect(inspection.role == .primaryResult)
    #expect(inspection.canPreview)
    #expect(inspection.currentByteCount == Int64(original.count))
    #expect(inspection.modifiedAt != nil)
    #expect(inspection.recordedByteCount == 21)
    #expect(inspection.recordedSHA256 == hash)
    #expect(try Data(contentsOf: output) == original)
    #expect(service.comparisonSummary(inspection, inspection).contains("Recorded SHA-256 values match"))
  }

  @Test
  func artifactInspectionRejectsAFileThatResolvesOutsideItsRunFolder() throws {
    let parent = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Inspection-Escape-\(UUID().uuidString)", isDirectory: true)
    let run = parent.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: parent) }
    let outside = parent.appendingPathComponent("original.csv")
    try "original\n".write(to: outside, atomically: true, encoding: .utf8)
    let link = run.appendingPathComponent("result.csv")
    try FileManager.default.createSymbolicLink(at: link, withDestinationURL: outside)

    let artifact = Artifact(path: link.path, relativePath: "result.csv", byteCount: 9)
    let job = JobRecord(capability: sampleCapability(), runDirectory: run.path)
    let inspection = ArtifactInspectionService().inspect(artifact, in: job)

    #expect(!inspection.isInsideRun)
    #expect(!inspection.canPreview)
    #expect(inspection.recordedSHA256 == nil)
    #expect(try String(contentsOf: outside, encoding: .utf8) == "original\n")
  }

  @Test
  func artifactInspectionResolvesHomeAbbreviatedManifestPathsWithinTheRun() throws {
    let home = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Inspection-Home-\(UUID().uuidString)", isDirectory: true)
    let run = home.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }
    let output = run.appendingPathComponent("summary.json")
    try "{}".write(to: output, atomically: true, encoding: .utf8)
    let hash = String(repeating: "b", count: 64)
    try """
      {"outputs":[{"path":"~/run/summary.json","size_bytes":2,"sha256":"\(hash)"}]}
      """.write(to: run.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)

    let artifact = Artifact(path: output.path, relativePath: "summary.json", byteCount: 2)
    let job = JobRecord(capability: sampleCapability(), runDirectory: run.path)
    let inspection = ArtifactInspectionService(homeDirectory: home).inspect(artifact, in: job)

    #expect(inspection.canPreview)
    #expect(inspection.recordedByteCount == 2)
    #expect(inspection.recordedSHA256 == hash)
  }

  @Test
  func artifactRolesDistinguishResultsEvidenceAndLogs() {
    let service = ArtifactInspectionService()
    func artifact(_ name: String, type: String? = nil, primary: Bool? = nil) -> Artifact {
      Artifact(path: "/runs/\(name)", relativePath: name, byteCount: 1,
               artifactType: type, primary: primary)
    }
    #expect(service.role(for: artifact("plot.png", primary: true)) == .primaryResult)
    #expect(service.role(for: artifact("table.csv", type: "table_csv")) == .result)
    #expect(service.role(for: artifact("manifest.json", type: "manifest_json")) == .evidence)
    #expect(service.role(for: artifact("stdout.txt", type: "log_txt")) == .log)
  }
}

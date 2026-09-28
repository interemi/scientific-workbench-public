import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func artifactDiscoveryPreservesTypedMetadataAcrossSummaryAndManifest() throws {
    for version in ["1.8", "1.9", "2.0", "2.8"] {
      let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("Scientific-Workbench-Metadata-\(UUID().uuidString)", isDirectory: true)
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: root) }
      try "{}".write(to: root.appendingPathComponent("quality.json"), atomically: true, encoding: .utf8)
      let summary = """
      {
        "contract_version": "\(version)",
        "typed_artifacts": [
          {"path": "./quality.json", "artifact_type": "qa_report", "label": "Scientific QA", "primary": true}
        ],
        "outputs": [{"path": "quality.json", "exists": true}]
      }
      """
      let manifest = #"{"outputs":[{"path":"quality.json","exists":true,"size":2}]}"#
      try summary.write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)
      try manifest.write(to: root.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)

      let artifact = try #require(ArtifactDiscovery().discover(in: root.path).first {
        $0.relativePath == "quality.json"
      })
      #expect(artifact.artifactType == "qa_report")
      #expect(artifact.label == "Scientific QA")
      #expect(artifact.primary == true)
    }
  }

  @Test
  func artifactDiscoveryMergesPartialMetadataAndPrefersTypedDeclarations() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Metadata-Merge-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    for name in ["quality.json", "legacy.json"] {
      try "{}".write(to: root.appendingPathComponent(name), atomically: true, encoding: .utf8)
    }
    let summary = #"""
    {
      "typed_artifacts": [
        {"path":"quality.json","artifact_type":"qa_report","label":"Scientific QA","primary":true}
      ],
      "artifacts": [
        {"path":"legacy.json","artifact_type":"qa_report","label":"Legacy QA","primary":false}
      ]
    }
    """#
    let manifest = #"""
    {
      "typed_artifacts": [{"path":"quality.json","primary":false}],
      "outputs": [
        {"path":"quality.json","artifact_type":"metadata_json","label":"Inventory"},
        {"path":"legacy.json","exists":true}
      ]
    }
    """#
    try summary.write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)
    try manifest.write(to: root.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)

    let artifacts = ArtifactDiscovery().discover(in: root.path)
    let typed = try #require(artifacts.first { $0.relativePath == "quality.json" })
    #expect(typed.artifactType == "qa_report")
    #expect(typed.label == "Scientific QA")
    #expect(typed.primary == false)
    let legacy = try #require(artifacts.first { $0.relativePath == "legacy.json" })
    #expect(legacy.artifactType == "qa_report")
    #expect(legacy.label == "Legacy QA")
    #expect(legacy.primary == false)
  }
}

import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func evidenceStagesKeepProcessToolArtifactsQAAndHumanReviewSeparate() throws {
    let root = try makeScenarioFixture(name: "evidence-stages", files: [
      "artifacts/matches.ecsv": "a,b\n1,2\n",
      "manifest.json": """
      {"outputs":[{"path":"artifacts/matches.ecsv","exists":true,"size_bytes":8,
      "sha256":"492d5ea496056f1a6a6592241032fab764c321596317930b4fa0e1e8bc3b7470"}]}
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }

    let cases: [(String, String, EvidenceLevel)] = [
      ("PASS", "ok", .pass),
      ("WARNING", "warning", .warning),
      ("BLOCKED_CONTROLADO", "blocked", .blocked),
      ("FAIL", "fail", .fail)
    ]
    for (toolStatus, qaStatus, expected) in cases {
      let summary = """
      {"tool":"catalog_workbench.crossmatch-sky","status":"\(toolStatus)",
      "app_status":"\(toolStatus)","qa":{"status":"\(qaStatus)","findings":[]}}
      """
      try summary.write(to: root.appendingPathComponent("summary.json"),
                        atomically: true, encoding: .utf8)
      var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
      job.status = toolStatus == "BLOCKED_CONTROLADO" ? .blocked
        : toolStatus == "FAIL" ? .failed : .succeeded
      job.exitCode = 0
      job.appStatus = toolStatus

      let stages = JobEvidenceAssessmentService().assess(job: job).stages
      func level(_ title: String) -> EvidenceLevel? {
        stages.first { $0.title == title }?.level
      }
      #expect(level("Process") == .pass)
      #expect(level("Tool outcome") == expected)
      #expect(level("Artifact contract") == .pass)
      #expect(level("Automatic QA") == expected)
      #expect(level("Human scientific review") == .incomplete)
    }
  }

  @Test
  func evidenceStagesMarkMissingOrChangedEvidenceWithoutClaimingPass() throws {
    let root = try makeScenarioFixture(name: "evidence-missing", files: [
      "summary.json": """
      {"tool":"profile_table","status":"ok","app_status":"PASS"}
      """,
      "artifacts/table.csv": "a,b\n1,2\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    job.status = .succeeded
    job.exitCode = 0
    job.appStatus = "PASS"

    func level(_ title: String) -> EvidenceLevel? {
      JobEvidenceAssessmentService().assess(job: job).stages
        .first { $0.title == title }?.level
    }
    #expect(level("Artifact contract") == .incomplete)
    #expect(level("Automatic QA") == .incomplete)

    let malformedQA = """
    {"tool":"profile_table","status":"ok","app_status":"PASS",
    "qa":{"status":"ok","findings":"not-an-array"}}
    """
    try malformedQA.write(to: root.appendingPathComponent("summary.json"),
                          atomically: true, encoding: .utf8)
    #expect(level("Automatic QA") == .incomplete)

    let manifest = """
    {"outputs":[{"path":"artifacts/table.csv","exists":true,"size_bytes":8,
    "sha256":"492d5ea496056f1a6a6592241032fab764c321596317930b4fa0e1e8bc3b7470"}]}
    """
    try manifest.write(to: root.appendingPathComponent("manifest.json"),
                       atomically: true, encoding: .utf8)
    #expect(level("Artifact contract") == .pass)
    let missingSize = """
    {"outputs":[{"path":"artifacts/table.csv","exists":true,
    "sha256":"492d5ea496056f1a6a6592241032fab764c321596317930b4fa0e1e8bc3b7470"}]}
    """
    try missingSize.write(to: root.appendingPathComponent("manifest.json"),
                          atomically: true, encoding: .utf8)
    #expect(level("Artifact contract") == .incomplete)
    try manifest.write(to: root.appendingPathComponent("manifest.json"),
                       atomically: true, encoding: .utf8)
    try "changed\n".write(to: root.appendingPathComponent("artifacts/table.csv"),
                           atomically: true, encoding: .utf8)
    #expect(level("Artifact contract") == .fail)
  }

  @Test
  func evidenceStagesRefuseManifestPathsOutsideRunFolder() throws {
    let root = try makeScenarioFixture(name: "evidence-path", files: [
      "summary.json": """
      {"tool":"profile_table","status":"ok","app_status":"PASS",
      "qa":{"status":"ok","findings":[]}}
      """,
      "manifest.json": """
      {"outputs":[{"path":"../outside.csv","exists":true,
      "sha256":"492d5ea496056f1a6a6592241032fab764c321596317930b4fa0e1e8bc3b7470"}]}
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    job.status = .succeeded
    job.exitCode = 0
    let stages = JobEvidenceAssessmentService().assess(job: job).stages
    #expect(stages.first { $0.title == "Artifact contract" }?.level == .incomplete)
  }
}

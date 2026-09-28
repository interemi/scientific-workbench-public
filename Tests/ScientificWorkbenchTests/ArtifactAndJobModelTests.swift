import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func toolEnvelopeParserRecoversFromUnclosedLogBrace() throws {
    let text = """
    progress log {unfinished diagnostic
    {"tool":"profile_table","status":"PASS","warnings":[]}
    """

    let envelope = try #require(ToolEnvelopeParser().parse(text))
    #expect(envelope.tool == "profile_table")
    #expect(envelope.status == "PASS")
  }

  @Test
  func toolEnvelopeParserRejectsUnrelatedJSONObject() {
    let text = #"log {"event":"process_finished","exit_code":0}"#

    #expect(ToolEnvelopeParser().parse(text) == nil)
  }

  @Test
  func toolEnvelopeParserDoesNotReplaceFailureWithNestedOrWeakTelemetry() throws {
    let text = """
    {"tool":"profile_table","status":"FAIL","errors":[{"message":"Invalid table."}]}
    {"event":{"tool":"telemetry","status":"PASS"}}
    {"contract_version":"telemetry"}
    {"tool":"telemetry","status":"done"}
    {"event":"process_finished","status":"PASS","warnings":[]}
    """

    let envelope = try #require(ToolEnvelopeParser().parse(text))
    #expect(envelope.tool == "profile_table")
    #expect(envelope.status == "FAIL")
    #expect(envelope.errors.first?.message == "Invalid table.")
  }

  @Test
  func jobStatusIncludesCancelledState() {
    #expect(JobStatus.cancelled.title == "Cancelled")
    #expect(JobStatus.allCases.contains(.cancelled))
  }

  @Test
  func jobStatusIncludesDedicatedTimeoutState() {
    #expect(JobStatus.timedOut.rawValue == "timeout")
    #expect(JobStatus.timedOut.title == "Timed Out")
    #expect(JobStatus.allCases.contains(.timedOut))
  }

  @Test
  func toolEnvelopeParserFindsToolAndStatus() {
    let text = """
    leading text
    {
      "tool": "profile_table",
      "status": "ok",
      "results": {"rows": 3}
    }
    trailing text
    """
    let envelope = ToolEnvelopeParser().parse(text)
    #expect(envelope?.tool == "profile_table")
    #expect(envelope?.status == "ok")
  }

  @Test
  func toolEnvelopeParserIgnoresBalancedBracesInLogsAndJSONStrings() throws {
    let text = #"""
    preflight log {not-json}
    {"tool":"profile_table","status":"WARNING","app_status":"WARNING","message":"kept {inside} a string with an escaped quote: \"ok\""}
    cleanup log {also-not-json}
    """#

    let envelope = try #require(ToolEnvelopeParser().parse(text))

    #expect(envelope.tool == "profile_table")
    #expect(envelope.status == "WARNING")
    #expect(envelope.appStatus == "WARNING")
  }

  @Test
  func toolEnvelopeParserIgnoresAdditionalJSONLogObjects() throws {
    let text = #"""
    {"level":"info","context":{"phase":"preflight"}}
    {"tool":"profile_table","status":"PASS","contract_version":"2.0"}
    {"level":"info","message":"finished {cleanly}"}
    """#

    let envelope = try #require(ToolEnvelopeParser().parse(text))

    #expect(envelope.tool == "profile_table")
    #expect(envelope.status == "PASS")
    #expect(envelope.contractVersion == "2.0")
  }

  @Test
  func toolEnvelopeParserSelectsLastValidEnvelope() throws {
    let text = #"""
    {"tool":"profile_table","status":"PASS","contract_version":"1.8"}
    {"tool":"profile_table","status":"WARNING","app_status":"WARNING","contract_version":"2.0"}
    """#

    let envelope = try #require(ToolEnvelopeParser().parse(text))

    #expect(envelope.status == "WARNING")
    #expect(envelope.appStatus == "WARNING")
    #expect(envelope.contractVersion == "2.0")
  }

  @Test
  func toolEnvelopeParserReadsV2ContractFields() throws {
    let text = """
    {
      "contract_version": "2.0",
      "tool": "profile_table",
      "status": "PASS",
      "app_status": "PASS",
      "command": {
        "argv": ["python", "scripts/profile_table.py", "input.csv"],
        "cwd": "/skill/root",
        "redacted": true
      },
      "inputs": [
        {
          "path": "input.csv",
          "role": "primary_input",
          "kind": "table_csv",
          "exists": true
        }
      ],
      "outputs": [
        {
          "path": "summary.json",
          "role": "summary",
          "artifact_type": "summary_json",
          "exists": true
        }
      ],
      "typed_artifacts": [
        {
          "path": "summary.json",
          "artifact_type": "summary_json",
          "label": "Summary",
          "primary": true
        },
        {
          "path": "tables/profile.csv",
          "artifact_type": "table_csv",
          "label": "Profile table",
          "primary": false
        }
      ],
      "errors": [
        {
          "kind": "missing_optional_backend",
          "message": "Optional backend unavailable.",
          "recovery_hint": "Use native route."
        }
      ],
      "next_actions": [
        {
          "label": "Open summary",
          "kind": "inspect_artifact",
          "priority": "normal"
        }
      ],
      "original_modified": false,
      "app_hints": {
        "short_summary": "Profile completed.",
        "severity": "ok",
        "preview_artifact_types": ["summary_json", "table_csv"],
        "tags": ["table", "v2.0"]
      }
    }
    """

    let envelope = try #require(ToolEnvelopeParser().parse(text))
    #expect(envelope.contractVersion == "2.0")
    #expect(envelope.appStatus == "PASS")
    #expect(envelope.command?.argv == ["python", "scripts/profile_table.py", "input.csv"])
    #expect(envelope.command?.cwd == "/skill/root")
    #expect(envelope.command?.redacted == true)
    #expect(envelope.inputs.first?.path == "input.csv")
    #expect(envelope.inputs.first?.kind == "table_csv")
    #expect(envelope.inputs.first?.exists == true)
    #expect(envelope.outputs.first?.artifactType == "summary_json")
    #expect(envelope.typedArtifacts.map(\.artifactType) == ["summary_json", "table_csv"])
    #expect(envelope.typedArtifacts.first?.primary == true)
    #expect(envelope.errors.first?.kind == "missing_optional_backend")
    #expect(envelope.errors.first?.recoveryHint == "Use native route.")
    #expect(envelope.nextActions.first?.kind == "inspect_artifact")
    #expect(envelope.originalModified == "false")
    #expect(envelope.appHints?.shortSummary == "Profile completed.")
    #expect(envelope.appHints?.previewArtifactTypes == ["summary_json", "table_csv"])
    #expect(envelope.appHints?.tags == ["table", "v2.0"])
  }

  @Test
  func artifactDiscoveryFindsNestedFiles() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Artifacts-\(UUID().uuidString)", isDirectory: true)
    let nested = root.appendingPathComponent("nested", isDirectory: true)
    try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
    try "hello".write(to: nested.appendingPathComponent("report.md"), atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: root) }

    let artifacts = ArtifactDiscovery().discover(in: root.path)
    #expect(artifacts.map(\.relativePath) == ["nested/report.md"])
    #expect(artifacts.first?.byteCount == 5)
  }

  @Test
  func artifactDiscoveryReadsTypedRunBundleMetadata() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-RunBundle-\(UUID().uuidString)", isDirectory: true)
    let reports = root.appendingPathComponent("reports", isDirectory: true)
    let tables = root.appendingPathComponent("tables", isDirectory: true)
    let logs = root.appendingPathComponent("logs", isDirectory: true)
    try FileManager.default.createDirectory(at: reports, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: tables, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
    try "{}".write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)
    try "report".write(to: reports.appendingPathComponent("report.md"), atomically: true, encoding: .utf8)
    try "a,b\n1,2\n".write(to: tables.appendingPathComponent("profile.csv"), atomically: true, encoding: .utf8)
    try "stderr".write(to: logs.appendingPathComponent("stderr.txt"), atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: root) }

    let summary = """
    {
      "contract_version": "2.0",
      "tool": "profile_table",
      "status": "PASS",
      "typed_artifacts": [
        {"path": "summary.json", "artifact_type": "summary_json", "label": "Summary", "primary": true},
        {"path": "reports/report.md", "artifact_type": "report_md", "label": "Report", "primary": false},
        {"path": "tables/profile.csv", "artifact_type": "table_csv", "label": "Profile CSV", "primary": false},
        {"path": "logs/stderr.txt", "artifact_type": "log_txt", "label": "stderr", "primary": false}
      ]
    }
    """
    try summary.write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)

    let artifacts = ArtifactDiscovery().discover(in: root.path)
    let byRelativePath = Dictionary(uniqueKeysWithValues: artifacts.map { ($0.relativePath, $0) })

    #expect(byRelativePath["summary.json"]?.artifactType == "summary_json")
    #expect(byRelativePath["summary.json"]?.primary == true)
    #expect(byRelativePath["reports/report.md"]?.artifactType == "report_md")
    #expect(byRelativePath["reports/report.md"]?.label == "Report")
    #expect(byRelativePath["tables/profile.csv"]?.artifactType == "table_csv")
    #expect(byRelativePath["logs/stderr.txt"]?.artifactType == "log_txt")
  }

  @Test
  func artifactDiscoveryReadsFitsRGBPreviewAndManifestMetadata() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-FitsRGBBundle-\(UUID().uuidString)", isDirectory: true)
    let artifacts = root.appendingPathComponent("artifacts", isDirectory: true)
    let previews = artifacts.appendingPathComponent("rgb_png", isDirectory: true)
    try FileManager.default.createDirectory(at: previews, withIntermediateDirectories: true)
    try "{}".write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)
    try "{}".write(to: artifacts.appendingPathComponent("manifest.json"), atomically: true, encoding: .utf8)
    try Data([0x89, 0x50, 0x4E, 0x47]).write(to: previews.appendingPathComponent("target_true_rgb.png"))
    defer { try? FileManager.default.removeItem(at: root) }

    let summary = """
    {
      "contract_version": "1.8",
      "tool": "fits_rgb_batch",
      "status": "warning",
      "typed_artifacts": [
        {"path": "summary.json", "artifact_type": "summary_json", "label": "Summary", "primary": true},
        {"path": "artifacts/manifest.json", "artifact_type": "manifest_json", "label": "Manifest", "primary": false},
        {"path": "artifacts/rgb_png/target_true_rgb.png", "artifact_type": "preview_png", "label": "RGB preview", "primary": false}
      ],
      "app_hints": {
        "preview_artifact_types": ["preview_png", "manifest_json"]
      }
    }
    """
    try summary.write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)

    let discovered = ArtifactDiscovery().discover(in: root.path)
    let byRelativePath = Dictionary(uniqueKeysWithValues: discovered.map { ($0.relativePath, $0) })

    #expect(byRelativePath["artifacts/rgb_png/target_true_rgb.png"]?.artifactType == "preview_png")
    #expect(byRelativePath["artifacts/rgb_png/target_true_rgb.png"]?.label == "RGB preview")
    #expect(byRelativePath["artifacts/manifest.json"]?.artifactType == "manifest_json")
  }

  @Test
  func artifactDiscoveryInfersCanonicalFitsProductsAndKeepsGenericJSONMetadata() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-FitsFallback-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try Data([0x53, 0x49, 0x4D, 0x50, 0x4C, 0x45]).write(to: root.appendingPathComponent("science.fit"))
    try Data([0x53, 0x49, 0x4D, 0x50, 0x4C, 0x45]).write(to: root.appendingPathComponent("master.FITS"))
    try Data([0x53, 0x49, 0x4D, 0x50, 0x4C, 0x45]).write(to: root.appendingPathComponent("legacy.fts"))
    try #"{"instrument":"example"}"#.write(
      to: root.appendingPathComponent("metadata.json"),
      atomically: true,
      encoding: .utf8
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let discovered = ArtifactDiscovery().discover(in: root.path)
    let byRelativePath = Dictionary(uniqueKeysWithValues: discovered.map { ($0.relativePath, $0) })

    #expect(byRelativePath["science.fit"]?.artifactType == "fits_product")
    #expect(byRelativePath["master.FITS"]?.artifactType == "fits_product")
    #expect(byRelativePath["legacy.fts"]?.artifactType == "fits_product")
    #expect(byRelativePath["metadata.json"]?.artifactType == "metadata_json")
  }

  @Test
  func artifactDiscoveryKeepsRelativePathsUnderTmpSymlink() throws {
    let root = URL(fileURLWithPath: "/tmp")
      .appendingPathComponent("Scientific-Workbench-Artifacts-Tmp-\(UUID().uuidString)", isDirectory: true)
    let nested = root.appendingPathComponent("nested", isDirectory: true)
    try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
    try "hello".write(to: nested.appendingPathComponent("report.md"), atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: root) }

    let artifacts = ArtifactDiscovery().discover(in: root.path)
    #expect(artifacts.map(\.relativePath) == ["nested/report.md"])
    #expect(artifacts.first?.path.contains("/Scientific-Workbench-Artifacts-Tmp-") == true)
  }

  @Test
  func jobRecordLifecycleFields() {
    let entry = CapabilityEntry(
      id: "profile_table",
      label: "profile_table.py",
      script: "scripts/profile_table.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Profile a table."
    )
    var job = JobRecord(capability: entry, runDirectory: "/tmp/run")
    #expect(job.status == .queued)
    job.status = .running
    job.startedAt = Date()
    job.status = .succeeded
    job.exitCode = 0
    job.finishedAt = Date()
    #expect(job.status == .succeeded)
    #expect(job.exitCode == 0)
    #expect(job.startedAt != nil)
    #expect(job.finishedAt != nil)
  }

  @Test
  func jobRecordRecoveryAdviceIsEmptyForSuccessfulJobs() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = .succeeded
    job.exitCode = 0

    #expect(job.recoveryAdvice.isEmpty)
  }

  @Test
  func jobRecordRecoveryAdviceExplainsMissingInputs() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = .blocked
    job.message = "This guided run needs at least one input file or folder."
    job.requestInputPaths = []

    #expect(job.recoveryAdvice.contains("This job needs input paths that were not available."))
    #expect(job.recoveryAdvice.contains("Attach the required files or folders, then run Dry Run before retrying."))
  }

  @Test
  func jobRecordRecoveryAdviceExplainsStructuredBlockedFailures() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = .failed
    job.exitCode = 2
    job.parsedStatus = "blocked"
    job.stdout = #"{"status": "blocked", "notes": ["missing cl/mkiraf"]}"#

    #expect(job.recoveryAdvice.contains("The process ran, but the tool reported a blocked structured status."))
    #expect(job.recoveryAdvice.contains("Use the tool notes in stdout to fix the precondition; retrying unchanged may fail again."))
  }

  @Test
  func jobRecordRecoveryAdviceExplainsTimeouts() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = .timedOut
    job.message = "Run timed out after 1800 seconds."

    #expect(job.recoveryAdvice.contains("The job reached the configured capability timeout."))
    #expect(job.recoveryAdvice.contains("Increase Capability timeout in Settings for legitimately long tools; otherwise inspect logs or reduce inputs before retrying."))
  }

  @Test
  func jobRecordRecoveryAdviceStillExplainsLegacyFailedTimeouts() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = .failed
    job.message = "Codex CLI did not finish within 180 seconds."

    #expect(job.recoveryAdvice.contains("The job reached the configured capability timeout."))
    #expect(job.recoveryAdvice.contains("Increase Capability timeout in Settings for legitimately long tools; otherwise inspect logs or reduce inputs before retrying."))
  }

  @Test
  func jobRecordCodableRoundTripsTimedOutStatus() throws {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = .timedOut
    job.message = "Run timed out after 1800 seconds."
    job.startedAt = Date(timeIntervalSince1970: 1_800)
    job.finishedAt = Date(timeIntervalSince1970: 3_600)

    let data = try JSONEncoder.scientificWorkbench.encode(job)
    let json = String(data: data, encoding: .utf8)
    let decoded = try JSONDecoder.scientificWorkbench.decode(JobRecord.self, from: data)

    #expect(json?.contains(#""status" : "timeout""#) == true)
    #expect(decoded.status == .timedOut)
    #expect(decoded.message == "Run timed out after 1800 seconds.")
  }

}

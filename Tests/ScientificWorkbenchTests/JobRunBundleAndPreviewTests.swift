import AppKit
import CoreGraphics
import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func runBundleExposesWarningBadgeWithoutWarningMessages() throws {
    let root = try makeScenarioFixture(
      name: "run-bundle-warning-badge",
      files: [
        "summary.json": """
        {
          "contract_version": "2.0",
          "tool": "profile_table",
          "status": "WARNING",
          "app_status": "WARNING",
          "warnings": [],
          "app_hints": {"severity": "warning"}
        }
        """
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }

    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    job.status = .succeeded
    JobRunBundleService().hydrate(&job)

    #expect(job.status == .succeeded)
    #expect(job.warnings.isEmpty)
    #expect(job.displaySeverity == "warning")
  }

  @Test
  func structuredFailStatusWinsOverZeroExitCode() {
    #expect(JobStatus.resolved(exitCode: 0, envelopeStatus: "FAIL", appStatus: "FAIL") == .failed)
    #expect(JobStatus.resolved(exitCode: 0, envelopeStatus: "ROTO", appStatus: nil) == .failed)
    #expect(JobStatus.resolved(exitCode: 0, envelopeStatus: " error ", appStatus: nil) == .failed)
    #expect(JobStatus.resolved(exitCode: 0, envelopeStatus: "PASS", appStatus: "FAILED") == .failed)
    #expect(JobStatus.resolved(exitCode: 0, envelopeStatus: "FAIL", appStatus: "BLOCKED_CONTROLADO") == .failed)
    #expect(JobStatus.resolved(exitCode: 0, envelopeStatus: "BLOCKED", appStatus: "ROTO") == .failed)
    #expect(JobStatus.resolved(exitCode: 0, envelopeStatus: "WARNING", appStatus: "WARNING") == .succeeded)
  }

  @Test
  func warningOutcomeKeepsSuccessfulLifecycleWithWarningDisplaySeverity() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = JobStatus.resolved(
      exitCode: 0,
      envelopeStatus: "WARNING",
      appStatus: "WARNING"
    )
    job.parsedStatus = "WARNING"
    job.appStatus = "WARNING"
    job.severity = nil
    job.warnings = []

    #expect(job.status == .succeeded)
    #expect(job.displaySeverity == "warning")
  }

  @Test
  func terminalFailureTakesDisplayPrecedenceOverWarningMetadata() {
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/run")
    job.status = .failed
    job.appStatus = "WARNING"
    job.severity = "warning"
    job.warnings = ["Partial output exists."]

    #expect(job.displaySeverity == JobStatus.failed.rawValue)
  }

  @Test
  func runBundleHydratesJobMetadataAndCanonicalArtifacts() throws {
    let root = try makeScenarioFixture(
      name: "run-bundle-hydration",
      files: [
        "summary.json": """
        {
          "contract_version": "2.0",
          "tool": "profile_table",
          "status": "WARNING",
          "app_status": "WARNING",
          "warnings": ["Non-finite values were excluded."],
          "errors": [],
          "next_actions": [
            {"label": "Inspect the profile table.", "kind": "inspect_artifact", "priority": "normal"}
          ],
          "original_modified": false,
          "app_hints": {
            "short_summary": "Profile completed with exclusions.",
            "severity": "warning",
            "preview_artifact_types": ["table_csv"],
            "tags": ["table", "qa"]
          },
          "typed_artifacts": [
            {"path": "tables/profile.csv", "artifact_type": "table_csv", "label": "Profile", "primary": true}
          ]
        }
        """,
        "manifest.json": "{}",
        "stdout.txt": "done",
        "stderr.txt": "",
        "command.txt": "python profile_table.py",
        "next_steps.md": "# Next steps\n\n- Inspect the profile table.\n",
        "tables/profile.csv": "column,count\nvalue,3\n"
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }

    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    JobRunBundleService().hydrate(&job)

    #expect(job.contractVersion == "2.0")
    #expect(job.appStatus == "WARNING")
    #expect(job.shortSummary == "Profile completed with exclusions.")
    #expect(job.originalModified == "false")
    #expect(job.warnings == ["Non-finite values were excluded."])
    #expect(job.nextActions.map(\.label) == ["Inspect the profile table."])
    #expect(job.previewArtifactTypes == ["table_csv"])
    #expect(job.tags == ["table", "qa"])
    #expect(job.artifacts.contains { $0.relativePath == "stdout.txt" && $0.artifactType == "log_txt" })
    #expect(job.artifacts.contains { $0.relativePath == "next_steps.md" && $0.artifactType == "report_md" })
    #expect(job.artifacts.contains { $0.relativePath == "tables/profile.csv" && $0.primary == true })
  }

  @Test
  func runBundleWritesCaptureAndRecoveryFilesForTerminalJobs() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Capture-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let service = JobRunBundleService()
    service.writeCaptureFiles(
      runDirectory: root.path,
      command: "python safe.py",
      stdout: "partial output",
      stderr: "cancelled"
    )
    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    job.status = .cancelled
    service.writeNextStepsIfMissing(for: job)
    service.hydrate(&job)

    #expect(job.artifacts.contains { $0.relativePath == "command.txt" })
    #expect(job.artifacts.contains { $0.relativePath == "stdout.txt" })
    #expect(job.artifacts.contains { $0.relativePath == "stderr.txt" })
    #expect(job.artifacts.contains { $0.relativePath == "next_steps.md" })
    let nextSteps = try String(contentsOf: root.appendingPathComponent("next_steps.md"), encoding: .utf8)
    #expect(nextSteps.contains("Retry the job"))
  }

  @Test
  func runBundleFallsBackToStdoutWhenManifestIsNotAnEnvelope() throws {
    let root = try makeScenarioFixture(
      name: "run-bundle-stdout-fallback",
      files: [
        "manifest.json": "{}",
        "next_steps.md": "# Next steps\n\n- Review the fallback envelope.\n"
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    job.stdout = #"{"tool":"profile_table","status":"PASS","app_status":"PASS"}"#

    JobRunBundleService().hydrate(&job)

    #expect(job.parsedTool == "profile_table")
    #expect(job.appStatus == "PASS")
    #expect(job.nextActions.map(\.label) == ["Review the fallback envelope."])
  }

  @Test
  func runBundleRestoresRedactedSidecarsAndNextStepsAfterReload() throws {
    let secret = "sk-sidecar-secret-123456789"
    let root = try makeScenarioFixture(
      name: "run-bundle-sidecar-reload",
      files: [
        "summary.json": """
        {
          "tool": "profile_table",
          "status": "WARNING",
          "warnings": ["Review \(secret)."],
          "next_actions": [],
          "app_hints": {"short_summary": "Completed with \(secret)."}
        }
        """,
        "command.txt": "python profile_table.py --token \(secret)",
        "stdout.txt": "stdout \(secret)",
        "stderr.txt": "stderr \(secret)",
        "next_steps.md": "# Next steps\n\n- Inspect \(secret) report.\n"
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }

    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    job.command = "stale command"
    job.stdout = "stale stdout"
    job.stderr = "stale stderr"
    JobRunBundleService().hydrate(
      &job,
      redact: { $0.replacingOccurrences(of: secret, with: "[REDACTED]") }
    )

    #expect(job.command == "python profile_table.py --token [REDACTED]")
    #expect(job.stdout == "stdout [REDACTED]")
    #expect(job.stderr == "stderr [REDACTED]")
    #expect(job.warnings == ["Review [REDACTED]."])
    #expect(job.shortSummary == "Completed with [REDACTED].")
    #expect(job.nextActions.map(\.label) == ["Inspect [REDACTED] report."])
    #expect(!job.command.contains(secret))
    #expect(!job.stdout.contains(secret))
    #expect(!job.stderr.contains(secret))
  }

  @Test
  @MainActor
  func persistedInterruptedJobRecoversRunBundleArtifacts() throws {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Recovery-\(UUID().uuidString)")!
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Recovery-\(UUID().uuidString)", isDirectory: true)
    let runRoot = outputRoot.appendingPathComponent("run", isDirectory: true)
    let historyURL = outputRoot
      .appendingPathComponent(".scientificworkbench", isDirectory: true)
      .appendingPathComponent("jobs.json")
    try FileManager.default.createDirectory(at: runRoot, withIntermediateDirectories: true)
    try "{}".write(to: runRoot.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)
    try "partial".write(to: runRoot.appendingPathComponent("stdout.txt"), atomically: true, encoding: .utf8)
    try FileManager.default.createDirectory(at: historyURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    defaults.set(outputRoot.path, forKey: "outputRootPath")
    defer { try? FileManager.default.removeItem(at: outputRoot) }

    let jobID = UUID()
    let payload = """
    {
      "version": 1,
      "generatedAt": "2026-06-15T10:00:00Z",
      "jobs": [{
        "id": "\(jobID.uuidString)",
        "capabilityID": "profile_table",
        "capabilityLabel": "profile_table.py",
        "status": "running",
        "runDirectory": "\(runRoot.path)",
        "createdAt": "2026-06-15T10:00:00Z"
      }]
    }
    """
    try payload.write(to: historyURL, atomically: true, encoding: .utf8)

    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)
    let recovered = try #require(store.jobs.first)
    #expect(recovered.status == .cancelled)
    #expect(recovered.artifacts.contains { $0.relativePath == "summary.json" })
    #expect(recovered.artifacts.contains { $0.relativePath == "stdout.txt" })
  }

  @Test
  @MainActor
  func artifactPreviewCoversImagePDFTableMarkdownNotebookAndLogs() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Previews-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let pngURL = root.appendingPathComponent("preview.png")
    let image = NSImage(size: NSSize(width: 32, height: 32))
    image.lockFocus()
    NSColor.systemTeal.setFill()
    NSBezierPath(rect: NSRect(x: 0, y: 0, width: 32, height: 32)).fill()
    image.unlockFocus()
    let tiffData = try #require(image.tiffRepresentation)
    let bitmap = try #require(NSBitmapImageRep(data: tiffData))
    try #require(bitmap.representation(using: .png, properties: [:])).write(to: pngURL)

    let pdfURL = root.appendingPathComponent("preview.pdf")
    var mediaBox = CGRect(x: 0, y: 0, width: 300, height: 200)
    let consumer = try #require(CGDataConsumer(url: pdfURL as CFURL))
    let context = try #require(CGContext(consumer: consumer, mediaBox: &mediaBox, nil))
    context.beginPDFPage(nil)
    context.setFillColor(NSColor.systemBlue.cgColor)
    context.fill(CGRect(x: 20, y: 20, width: 100, height: 60))
    context.endPDFPage()
    context.closePDF()

    try "a,b\n1,2\n".write(to: root.appendingPathComponent("table.csv"), atomically: true, encoding: .utf8)
    try "# %ECSV 1.0\na b\n1 2\n".write(to: root.appendingPathComponent("table.ecsv"), atomically: true, encoding: .utf8)
    try "# Report\n\nSafe text.".write(to: root.appendingPathComponent("report.md"), atomically: true, encoding: .utf8)
    try "token=secret-value-123".write(to: root.appendingPathComponent("stdout.log"), atomically: true, encoding: .utf8)
    try """
    {"cells":[{"cell_type":"markdown","source":["# Notebook\\n"]},{"cell_type":"code","source":["print(1)\\n"]}]}
    """.write(to: root.appendingPathComponent("analysis.ipynb"), atomically: true, encoding: .utf8)

    let service = ArtifactPreviewService()
    let redact: (String) -> String = { $0.replacingOccurrences(of: "secret-value-123", with: "[REDACTED]") }
    func artifact(_ name: String) throws -> Artifact {
      let url = root.appendingPathComponent(name)
      let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
      return Artifact(path: url.path, relativePath: name, byteCount: Int64(size))
    }

    #expect(service.load(artifact: try artifact("preview.png"), redact: redact).kind == .image)
    #expect(service.load(artifact: try artifact("preview.pdf"), redact: redact).kind == .pdf)
    #expect(service.load(artifact: try artifact("table.csv"), redact: redact).kind == .table)
    let ecsv = service.load(artifact: try artifact("table.ecsv"), redact: redact)
    #expect(ecsv.kind == .table)
    #expect(ecsv.text?.contains("# %ECSV 1.0") == true)
    #expect(service.load(artifact: try artifact("report.md"), redact: redact).kind == .markdown)
    #expect(service.load(artifact: try artifact("analysis.ipynb"), redact: redact).kind == .notebook)
    let log = service.load(artifact: try artifact("stdout.log"), redact: redact)
    #expect(log.kind == .log)
    #expect(log.text?.contains("[REDACTED]") == true)
    #expect(log.text?.contains("secret-value-123") == false)
  }

  @Test
  func jobSupportBundleCopiesOnlyRedactedSafeSidecars() throws {
    let root = try makeScenarioFixture(
      name: "job-support",
      files: [
        "summary.json": #"{"token":"secret-value-123"}"#,
        "manifest.json": "{}",
        "stdout.txt": "secret-value-123",
        "artifacts/private.csv": "personal,data\n"
      ]
    )
    let secretRoot = root.deletingLastPathComponent()
      .appendingPathComponent("Scientific-Workbench-secret-value-123-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.moveItem(at: root, to: secretRoot)
    let supportRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Support-\(UUID().uuidString)", isDirectory: true)
    defer {
      try? FileManager.default.removeItem(at: secretRoot)
      try? FileManager.default.removeItem(at: supportRoot)
    }

    let redact: (String) -> String = {
      $0.replacingOccurrences(of: "secret-value-123", with: "[REDACTED]")
    }
    var job = JobRecord(capability: sampleCapability(), runDirectory: secretRoot.path)
    JobRunBundleService().hydrate(&job, redact: redact)
    var redactedJob = job
    redactedJob.runDirectory = job.runDirectory.replacingOccurrences(of: "secret-value-123", with: "[REDACTED]")
    redactedJob.artifacts = job.artifacts.map {
      Artifact(
        id: $0.id,
        path: $0.path.replacingOccurrences(of: "secret-value-123", with: "[REDACTED]"),
        relativePath: $0.relativePath,
        byteCount: $0.byteCount,
        artifactType: $0.artifactType,
        label: $0.label,
        primary: $0.primary
      )
    }
    let result = try SupportBundleService().exportJob(
      job: job,
      redactedJob: redactedJob,
      supportBundlesDirectory: supportRoot,
      redact: redact
    )
    let summary = try String(
      contentsOf: result.bundleURL.appendingPathComponent("summary.json"),
      encoding: .utf8
    )
    let state = try String(
      contentsOf: result.bundleURL.appendingPathComponent("job_state.json"),
      encoding: .utf8
    )
    #expect(summary.contains("[REDACTED]"))
    #expect(state.contains("[REDACTED]"))
    #expect(!state.contains("secret-value-123"))
    #expect(!FileManager.default.fileExists(atPath: result.bundleURL.appendingPathComponent("artifacts/private.csv").path))
    #expect(FileManager.default.fileExists(atPath: result.bundleURL.appendingPathComponent("job_state.json").path))
  }
}

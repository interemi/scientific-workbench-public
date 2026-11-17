import AppKit
import CoreGraphics
import Foundation
import ImageIO
@testable import ScientificWorkbench
import Testing
import UniformTypeIdentifiers

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
  func artifactPreviewCoversImagePDFTableMarkdownNotebookAndLogs() async throws {
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
    try "SIMPLE  = T".write(to: root.appendingPathComponent("raw.fits"), atomically: true, encoding: .utf8)
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
    let pdfBefore = try Data(contentsOf: pdfURL)
    let job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    let pdf = try #require(await ArtifactPreviewLoader().load(
      try artifact("preview.pdf"), in: job, includePreview: true, redact: { $0 }
    ))
    #expect(pdf.inspection.currentByteCount == Int64(pdfBefore.count))
    #expect(pdf.payload?.kind == .pdf)
    guard case .pdfThumbnail(let thumbnail) = pdf.payload?.image else {
      Issue.record("Expected a rendered first-page thumbnail.")
      return
    }
    #expect(thumbnail.width > 0 && thumbnail.height > 0)
    #expect(try Data(contentsOf: pdfURL) == pdfBefore)
    #expect(service.load(artifact: try artifact("table.csv"), redact: redact).kind == .table)
    let ecsv = service.load(artifact: try artifact("table.ecsv"), redact: redact)
    #expect(ecsv.kind == .table)
    #expect(ecsv.text?.contains("# %ECSV 1.0") == true)
    #expect(service.load(artifact: try artifact("report.md"), redact: redact).kind == .markdown)
    #expect(service.load(artifact: try artifact("analysis.ipynb"), redact: redact).kind == .notebook)
    let rawFITS = service.load(artifact: try artifact("raw.fits"), redact: redact)
    #expect(rawFITS.kind == .unavailable)
    #expect(rawFITS.note?.contains("PNG quicklook") == true)
    let log = service.load(artifact: try artifact("stdout.log"), redact: redact)
    #expect(log.kind == .log)
    #expect(log.text?.contains("[REDACTED]") == true)
    #expect(log.text?.contains("secret-value-123") == false)
  }

  @Test
  func rasterPreviewDownsamplesAReorientedJPEGWithoutWritingIt() throws {
    let root = try makeScenarioFixture(name: "raster-orientation", files: [:])
    defer { try? FileManager.default.removeItem(at: root) }
    let url = root.appendingPathComponent("rotated.jpg")
    try writeRasterFixture(to: url, width: 2_000, height: 1_000, type: .jpeg, orientation: 6)
    let original = try Data(contentsOf: url)
    let artifact = Artifact(path: url.path, relativePath: url.lastPathComponent, byteCount: Int64(original.count))
    let preview = ArtifactPreviewService().load(artifact: artifact, redact: { $0 })

    #expect(preview.kind == .image)
    guard case .raster(let thumbnail) = preview.image else {
      Issue.record("Expected a decoded raster thumbnail")
      return
    }
    #expect(thumbnail.width == 800)
    #expect(thumbnail.height == 1_600)
    #expect(thumbnail.bytesPerRow * thumbnail.height <= 12 * 1024 * 1024)
    func redDominates(atY y: Int) throws -> Bool {
      let sample = try #require(thumbnail.cropping(to: CGRect(x: thumbnail.width / 2, y: y, width: 1, height: 1)))
      let context = try #require(CGContext(
        data: nil, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
      ))
      context.draw(sample, in: CGRect(x: 0, y: 0, width: 1, height: 1))
      let channels = try #require(context.data).assumingMemoryBound(to: UInt8.self)
      return channels[0] > channels[2]
    }
    #expect(try redDominates(atY: thumbnail.height / 4))
    #expect(try !redDominates(atY: thumbnail.height * 3 / 4))
    #expect(preview.note?.contains("original artifact for measurements") == true)
    #expect(try Data(contentsOf: url) == original)
  }

  @Test
  func rasterPreviewRejectsOversizedAndCorruptImages() throws {
    let root = try makeScenarioFixture(name: "raster-preview-limits", files: ["corrupt.png": "not a PNG"])
    defer { try? FileManager.default.removeItem(at: root) }
    let wide = root.appendingPathComponent("wide.png")
    try writeRasterFixture(to: wide, width: 16_385, height: 1, type: .png)
    let oversized = root.appendingPathComponent("oversized.png")
    try Data().write(to: oversized)
    let handle = try FileHandle(forWritingTo: oversized)
    try handle.truncate(atOffset: 256 * 1024 * 1024 + 1)
    try handle.close()

    for url in [wide, oversized, root.appendingPathComponent("corrupt.png")] {
      let artifact = Artifact(path: url.path, relativePath: url.lastPathComponent, byteCount: 1)
      let preview = ArtifactPreviewService().load(artifact: artifact, redact: { $0 })
      #expect(preview.kind == .unavailable)
      #expect(preview.image == nil)
      let expectedMessage = url.lastPathComponent == "corrupt.png" ? "could not be decoded" : "size limit"
      #expect(preview.note?.contains(expectedMessage) == true)
    }
  }

  @Test
  func rasterPreviewDropsCancelledRequestsAndRejectsFilesOutsideTheRun() async throws {
    let root = try makeScenarioFixture(name: "raster-preview-scope", files: ["outside.png": "outside"])
    defer { try? FileManager.default.removeItem(at: root) }
    let run = root.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    let job = JobRecord(capability: sampleCapability(), runDirectory: run.path)
    let url = root.appendingPathComponent("outside.png")
    let artifact = Artifact(path: url.path, relativePath: url.lastPathComponent, byteCount: 7)
    let service = ArtifactPreviewService()
    let outside = await service.loadRaster(artifact, in: job)
    #expect(outside?.kind == .unavailable)
    #expect(outside?.note?.contains("outside its recorded run folder") == true)

    let cancelled = Task {
      while !Task.isCancelled { await Task.yield() }
      return await service.loadRaster(artifact, in: job)
    }
    cancelled.cancel()
    #expect(await cancelled.value == nil)

    let link = run.appendingPathComponent("outside.txt")
    try FileManager.default.createSymbolicLink(at: link, withDestinationURL: url)
    let linked = Artifact(path: link.path, relativePath: link.lastPathComponent, byteCount: 7)
    let loader = ArtifactPreviewLoader()
    let document = try #require(await loader.load(linked, in: job, includePreview: true, redact: { $0 }))
    #expect(!document.inspection.canPreview)
    #expect(document.payload?.title == "Preview unavailable")
    #expect(document.payload?.text == nil)
    let cancelledDocument = Task {
      while !Task.isCancelled { await Task.yield() }
      return await loader.load(linked, in: job, includePreview: true, redact: { $0 })
    }
    cancelledDocument.cancel()
    #expect(await cancelledDocument.value == nil)
  }

  @Test
  func fitsInspectionReadsRetainedSummaryThroughArtifactLoader() async throws {
    let summaryText = """
    {"tool":"inspect_fits","results":{"hdus":[
      {"index":0,"name":"PRIMARY","type":"PrimaryHDU","has_data":false,"header":{},"wcs":null},
      {"index":1,"name":"SCI","type":"ImageHDU","has_data":true,"data_kind":"image",
       "header":{"BUNIT":"adu","BLANK":-32768},
       "wcs":{"ctype":["RA---TAN","DEC--TAN"],"axis_units":["deg","deg"],"reference_frame":"ICRS",
              "crpix":[5,4],"crval":[150,-30],"projection_plane_scale_arcsec":[1,1]},
       "data_summary":{"shape":[8,10],"dtype":"float32","sampled_pixels":80,"nonfinite_sampled_pixels":1}},
      {"index":2,"name":"DQ","type":"ImageHDU","has_data":true,"header":{},"wcs":null}
    ],"preview_extension":1,"preview":{"status":"rendered","hdu_index":1,"region_xywh":[2,1,5,4],
      "plane_indices":[],"coordinates":"wcs","display_only":true},"pixel_lookup":{"hdu_index":1,
      "image_xy":[2,1],"plane_indices":[],"pixel_value":12.5,"pixel_unit":"adu","pixel_status":"finite",
      "world_axes":[{"name":"RA---TAN","value":150.0,"unit":"deg"}],"reference_frame":"ICRS"}}}
    """
    let root = try makeScenarioFixture(name: "fits-inspection-summary", files: ["summary.json": summaryText])
    defer { try? FileManager.default.removeItem(at: root) }
    let file = root.appendingPathComponent("summary.json")
    let artifact = Artifact(path: file.path, relativePath: "summary.json", byteCount: Int64(summaryText.utf8.count),
                            artifactType: "summary_json")
    let job = JobRecord(capability: expertFITSCapability(), runDirectory: root.path)
    let snapshot = await ArtifactPreviewLoader().load(artifact, in: job, includePreview: true, redact: { $0 })
    let inspection = try #require(snapshot?.fitsInspection)
    #expect(snapshot?.payload?.text?.contains("inspect_fits") == true)
    #expect(inspection.hdus.map(\.name) == ["PRIMARY", "SCI", "DQ"])
    #expect(inspection.hdus[1].dataSummary?.nonfiniteSampledPixels == 1)
    #expect(inspection.hdus[1].wcs?.projectionPlaneScaleArcsec == [1, 1])
    #expect(inspection.hdus[1].header["BLANK"]?.text == "-32768")
    #expect(inspection.preview?.hduIndex == 1)
    #expect(inspection.preview?.regionXywh == [2, 1, 5, 4])
    #expect(inspection.pixelLookup?.imageXy == [2, 1])
    #expect(inspection.pixelLookup?.pixelValue?.text == "12.5")
    #expect(inspection.pixelLookup?.worldAxes.first?.unit == "deg")
    #expect(try String(contentsOf: file, encoding: .utf8) == summaryText)
  }

  @Test
  @MainActor
  func fitsFollowUpsUseRecordedInputsAndKeepPriorArtifacts() async throws {
    let root = try makeScenarioFixture(
      name: "fits-inspection-follow-up",
      files: [
        "input/science.fits": "source bytes",
        "unattached.fits": "another file",
        "scripts/datanalysis_env.py": """
        import json
        import sys
        from pathlib import Path
        assert sys.argv[1:3] == ["run-tool", "inspect_fits"]
        path = Path(sys.argv[3])
        assert path.read_text() == "source bytes"
        assert sys.argv[sys.argv.index("--extension") + 1] == "1"
        output = Path(sys.argv[sys.argv.index("--summary-json") + 1])
        if "--preview" in sys.argv:
            preview = Path(sys.argv[sys.argv.index("--preview") + 1])
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_bytes(b"test quicklook")
        output.write_text(json.dumps({"tool": "inspect_fits", "app_status": "PASS", "arguments": sys.argv[4:]}))
        """
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let input = root.appendingPathComponent("input/science.fits")
    let priorOutput = root.appendingPathComponent("prior-run")
    try FileManager.default.createDirectory(at: priorOutput, withIntermediateDirectories: true)
    let summaryURL = priorOutput.appendingPathComponent("summary.json")
    func retainedSummary(for source: URL) throws -> Data {
      try JSONSerialization.data(withJSONObject: [
        "tool": "inspect_fits", "results": ["path": source.path, "hdus": []]
      ])
    }
    let priorBytes = try retainedSummary(for: input)
    try priorBytes.write(to: summaryURL)
    let summary = try #require(FITSInspectionSummary.load(from: summaryURL))
    let suite = "Scientific-Workbench-Tests-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.outputRootPath = root.appendingPathComponent("new-runs").path
    store.skillRootPath = root.path
    store.pythonExecutable = "/usr/bin/python3"

    var original = JobRecord(capability: expertFITSCapability(), runDirectory: priorOutput.path)
    original.status = .succeeded
    original.requestInputPaths = [input.path]
    store.capabilities = [expertFITSCapability()]
    #expect(await store.runFITSFollowUp(from: original, summary: summary, hdu: 1, action: .lookup(x: 2, y: 1)) == nil)

    store.capabilities = [expertFITSCapability(boundedPreview: true, pixelLookup: true)]
    let unrelatedURL = root.appendingPathComponent("unrelated-summary.json")
    try retainedSummary(for: root.appendingPathComponent("unattached.fits")).write(to: unrelatedURL)
    let unrelated = try #require(FITSInspectionSummary.load(from: unrelatedURL))
    #expect(await store.runFITSFollowUp(from: original, summary: unrelated, hdu: 1, action: .lookup(x: 2, y: 1)) == nil)

    let lookup = try #require(await store.runFITSFollowUp(from: original, summary: summary, hdu: 1, action: .lookup(x: 2, y: 1)))
    let crop = try #require(await store.runFITSFollowUp(from: original, summary: summary, hdu: 1,
                                                       action: .crop(x: 2, y: 1, width: 4, height: 4)))
    #expect(lookup.status == .succeeded)
    #expect(crop.status == .succeeded)
    #expect(try ShellWords.split(lookup.requestRawArguments).suffix(2) == ["--pixel", "2,1"])
    #expect(try ShellWords.split(crop.requestRawArguments).contains("2,1,4,4"))
    #expect(crop.artifacts.contains { $0.relativePath == "previews/fits_quicklook.png" })
    #expect(lookup.runDirectory != crop.runDirectory)
    #expect(lookup.runDirectory != original.runDirectory)
    #expect(try Data(contentsOf: summaryURL) == priorBytes)
    #expect(try String(contentsOf: input, encoding: .utf8) == "source bytes")
  }

  @Test
  func measurementPreviewKeepsMissingUncertaintyDistinctFromZero() async throws {
    let summaryText = """
    {
      "tool": "photometric_solution",
      "results": {
        "measurement_summary": {
          "method": "Ordinary linear least squares",
          "measurements": [
            {"label": "Zero point", "value": 1.2, "unit": "mag", "uncertainty": null},
            {"label": "Extinction", "value": -0.2, "unit": "mag per unit airmass", "uncertainty": 0}
          ],
          "diagnostics": [{"label": "Residual degrees of freedom", "value": 0, "unit": "dimensionless"}],
          "assumptions": ["Systematic errors are outside the model."]
        }
      },
      "qa": {"status": "warning", "findings": ["Residuals cannot independently check the fit."]}
    }
    """
    let root = try makeScenarioFixture(
      name: "measurement-preview",
      files: ["summary.json": summaryText, "legacy-summary.json": #"{"tool":"photometric_solution","results":{}}"#]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let capability = CapabilityEntry(
      id: "photometric_solution", label: "Photometry", script: "photometry.py", visibleBlock: "astronomy",
      kind: "supporting_tool", supportLevel: "stable", platform: "portable",
      requiresDatanalysis: true, preflightMode: "none", smokeTier: "core", shortDescription: "Photometry."
    )
    let job = JobRecord(capability: capability, runDirectory: root.path)
    let url = root.appendingPathComponent("summary.json")
    let artifact = Artifact(path: url.path, relativePath: "summary.json",
                            byteCount: Int64(summaryText.utf8.count), artifactType: "summary_json")
    let preview = try #require(await ArtifactPreviewLoader.shared.load(artifact, in: job, includePreview: true, redact: { $0 }))
    let summary = try #require(preview.measurementSummary)
    #expect(summary.measurements.map(\.uncertainty) == [nil, 0])
    #expect(summary.diagnostics.first?.value == 0)
    #expect(summary.quality.status == "warning")
    #expect(summary.quality.findings == ["Residuals cannot independently check the fit."])
    #expect(preview.payload?.kind == .json)
    #expect(ScientificMeasurementSummary.load(from: url, capabilityID: "inspect_fits") == nil)
    #expect(ScientificMeasurementSummary.load(from: root.appendingPathComponent("legacy-summary.json"),
                                             capabilityID: capability.id) == nil)
  }

  @Test
  func rasterPreviewCacheReusesOnlyTheCurrentVersionAndClearsOnlyTheReviewedEntry() async throws {
    let root = try makeScenarioFixture(name: "raster-preview-cache", files: ["stderr.txt": "failure evidence"])
    defer { try? FileManager.default.removeItem(at: root) }
    let imageURL = root.appendingPathComponent("preview.png")
    let failureLog = root.appendingPathComponent("stderr.txt")
    try writeRasterFixture(to: imageURL, width: 40, height: 30, type: .png)
    let original = try Data(contentsOf: imageURL)
    let artifact = Artifact(path: imageURL.path, relativePath: imageURL.lastPathComponent, byteCount: Int64(original.count))
    let job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    let loader = RasterPreviewLoader()

    let first = await loader.load(artifact, in: job)
    let cached = await loader.load(artifact, in: job)
    guard case .raster(let firstImage) = first?.image, case .raster(let cachedImage) = cached?.image else {
      Issue.record("Expected a raster thumbnail for both requests.")
      return
    }
    #expect(firstImage === cachedImage)
    let reviewed = await loader.cacheUsage()
    #expect(reviewed.bytes == cachedImage.bytesPerRow * cachedImage.height)
    #expect(RasterPreviewLoader.maximumCacheBytes <= 12 * 1024 * 1024)
    #expect(try Data(contentsOf: imageURL) == original)

    let replacement = root.appendingPathComponent("replacement.png")
    try writeRasterFixture(to: replacement, width: 80, height: 30, type: .png)
    let newSource = try Data(contentsOf: replacement)
    try newSource.write(to: imageURL, options: .atomic)
    let refreshed = await loader.load(artifact, in: job)
    guard case .raster(let refreshedImage) = refreshed?.image else {
      Issue.record("Expected a raster thumbnail after replacement.")
      return
    }
    #expect(refreshedImage.width == 80)
    #expect(await loader.clearCache(reviewed: reviewed) == nil)
    let latest = await loader.cacheUsage()
    #expect(latest.bytes > 0)
    #expect(await loader.clearCache(reviewed: latest)?.bytes == 0)
    #expect(try Data(contentsOf: imageURL) == newSource)
    #expect(try String(contentsOf: failureLog, encoding: .utf8) == "failure evidence")

    let rebuilt = await loader.load(artifact, in: job)
    #expect(rebuilt?.kind == .image)
    #expect(await loader.cacheUsage().bytes == latest.bytes)
  }

  private func writeRasterFixture(
    to url: URL, width: Int, height: Int, type: UTType, orientation: Int = 1
  ) throws {
    let context = try #require(CGContext(
      data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
    ))
    context.setFillColor(red: 0.25, green: 0.5, blue: 0.75, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    context.setFillColor(red: 0.85, green: 0.25, blue: 0.1, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: width / 2, height: height))
    let image = try #require(context.makeImage())
    let destination = try #require(CGImageDestinationCreateWithURL(url as CFURL, type.identifier as CFString, 1, nil))
    CGImageDestinationAddImage(destination, image, [kCGImagePropertyOrientation: orientation] as CFDictionary)
    try #require(CGImageDestinationFinalize(destination))
  }

  @Test
  func textPreviewKeepsValidUTF8WhenTheByteLimitCutsACharacter() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-UTF8-Preview-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let path = root.appendingPathComponent("table.csv")
    let data = Data((String(repeating: "a", count: 79_999) + "é").utf8)
    try data.write(to: path)
    let artifact = Artifact(path: path.path, relativePath: "table.csv", byteCount: Int64(data.count))
    let preview = ArtifactPreviewService().load(artifact: artifact, redact: { $0 })

    #expect(preview.kind == .table)
    #expect(preview.text?.utf8.count == 79_999)
    #expect(preview.note?.contains("truncated") == true)
    #expect(try Data(contentsOf: path) == data)
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

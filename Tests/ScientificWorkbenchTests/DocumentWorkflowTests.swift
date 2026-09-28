import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func documentWorkflowStagesCopyAndDetectsOriginalChanges() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-DocumentCopy-\(UUID().uuidString)", isDirectory: true)
    let source = root.appendingPathComponent("original.docx")
    let run = root.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try Data("original bytes".utf8).write(to: source)
    defer { try? FileManager.default.removeItem(at: root) }

    let service = DocumentWorkflowService()
    let staged = try service.stageDOCX(sourcePath: source.path, runDirectory: run.path)

    #expect(staged.sourcePath == source.path)
    #expect(FileManager.default.fileExists(atPath: staged.stagedPath))
    #expect(try Data(contentsOf: URL(fileURLWithPath: staged.stagedPath)) == Data("original bytes".utf8))
    #expect(service.originalIsUnchanged(staged))

    try Data("changed".utf8).write(to: source)
    #expect(!service.originalIsUnchanged(staged))
  }

  @Test
  func documentWorkflowParsesInventoryAndBuildsReviewedDiff() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-DocumentSummary-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let summary = root.appendingPathComponent("summary.json")
    try """
    {
      "app_status": "PASS",
      "results": {
        "inventory": {
          "input": "inputs/source.docx",
          "requirements": {"bold": true, "italic": false, "underline": false},
          "limitations": ["Explicit run formatting only."],
          "matches": [
            {
              "location": "body",
              "paragraph_index": 2,
              "table_index": null,
              "row_index": null,
              "cell_index": null,
              "run_index": 1,
              "text": "APPROVED draft",
              "bold": true,
              "italic": false,
              "underline": false,
              "paragraph_style": "Normal",
              "character_style": "Default Paragraph Font"
            }
          ]
        }
      },
      "qa": {"findings": []}
    }
    """.write(to: summary, atomically: true, encoding: .utf8)

    let service = DocumentWorkflowService()
    let review = try service.parseDOCXInventory(
      summaryPath: summary.path,
      originalFingerprint: "abc"
    )
    let diff = service.diff(review: review, find: "draft", replace: "final")

    #expect(review.status == .pass)
    #expect(review.matchCount == 1)
    #expect(review.matches.first?.styleLabels == ["Bold"])
    #expect(diff.count == 1)
    #expect(diff.first?.before == "APPROVED draft")
    #expect(diff.first?.after == "APPROVED final")
    #expect(diff.first?.replacementCount == 1)
  }

  @Test
  func documentWorkflowSummarizesVisibleStyleCounts() {
    let matches = [
      DOCXStyleMatch(
        location: "body",
        paragraphIndex: 1,
        tableIndex: nil,
        rowIndex: nil,
        cellIndex: nil,
        runIndex: 1,
        text: "Bold",
        bold: true,
        italic: false,
        underline: false,
        paragraphStyle: "Normal",
        characterStyle: "Default Paragraph Font"
      ),
      DOCXStyleMatch(
        location: "body",
        paragraphIndex: 1,
        tableIndex: nil,
        rowIndex: nil,
        cellIndex: nil,
        runIndex: 2,
        text: "Bold italic",
        bold: true,
        italic: true,
        underline: false,
        paragraphStyle: "Normal",
        characterStyle: "Default Paragraph Font"
      ),
      DOCXStyleMatch(
        location: "table",
        paragraphIndex: 1,
        tableIndex: 1,
        rowIndex: 1,
        cellIndex: 1,
        runIndex: 1,
        text: "Underlined table",
        bold: false,
        italic: false,
        underline: true,
        paragraphStyle: "Normal",
        characterStyle: "Default Paragraph Font"
      ),
    ]
    let review = DOCXStyleReview(
      inputPath: "inputs/varied.docx",
      status: .pass,
      requirements: ["any_special_style": true],
      matches: matches,
      findings: [],
      limitations: [],
      originalFingerprint: "abc"
    )

    #expect(
      review.styleCounts
        == DOCXStyleCounts(bold: 2, italic: 1, underline: 1, body: 2, table: 1)
    )
  }

  @Test
  func documentWorkflowRequiresReviewedConfirmationBeforeReplacement() throws {
    let match = DOCXStyleMatch(
      location: "body",
      paragraphIndex: 1,
      tableIndex: nil,
      rowIndex: nil,
      cellIndex: nil,
      runIndex: 1,
      text: "APPROVED draft",
      bold: true,
      italic: true,
      underline: true,
      paragraphStyle: "Normal",
      characterStyle: "Default Paragraph Font"
    )
    let diff = [
      DOCXStyleDiff(
        match: match,
        before: "APPROVED draft",
        after: "APPROVED final",
        replacementCount: 1
      )
    ]
    let service = DocumentWorkflowService()

    #expect(throws: DocumentWorkflowError.confirmationRequired) {
      try service.validateReplacementApproval(confirmed: false, diff: diff)
    }
    #expect(throws: DocumentWorkflowError.noReviewedChanges) {
      try service.validateReplacementApproval(confirmed: true, diff: [])
    }
    try service.validateReplacementApproval(confirmed: true, diff: diff)
  }

  @Test
  func documentWorkflowParsesControlledKeynotePreflight() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-KeynoteSummary-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let summary = root.appendingPathComponent("summary.json")
    try """
    {
      "app_status": "BLOCKED_CONTROLADO",
      "results": {
        "recommendation": "Install or authorize Keynote.",
        "blocking_findings": ["Keynote.app is unavailable."],
        "warning_findings": [],
        "capabilities": {
          "platform": "darwin",
          "osascript": true,
          "keynote_app": false
        }
      }
    }
    """.write(to: summary, atomically: true, encoding: .utf8)

    let review = try DocumentWorkflowService().parseKeynotePreflight(
      summaryPath: summary.path,
      originalFingerprint: "fingerprint"
    )

    #expect(review.status == .blocked)
    #expect(review.osascriptAvailable)
    #expect(!review.keynoteAvailable)
    #expect(!review.canExport)
    #expect(review.findings == ["Keynote.app is unavailable."])
  }

  @Test
  func documentWorkflowRequiresReadyPreflightAndKeynoteConfirmation() throws {
    let service = DocumentWorkflowService()
    let blocked = KeynotePreflightReview(
      status: .blocked,
      platform: "darwin",
      osascriptAvailable: true,
      keynoteAvailable: false,
      recommendation: "Install Keynote.",
      findings: ["Keynote.app is unavailable."],
      originalFingerprint: "blocked"
    )
    let ready = KeynotePreflightReview(
      status: .pass,
      platform: "darwin",
      osascriptAvailable: true,
      keynoteAvailable: true,
      recommendation: "Keynote export is ready.",
      findings: [],
      originalFingerprint: "ready"
    )

    #expect(throws: DocumentWorkflowError.keynoteConfirmationRequired) {
      try service.validateKeynoteExportApproval(confirmed: false, preflight: ready)
    }
    #expect(throws: DocumentWorkflowError.keynotePreflightRequired) {
      try service.validateKeynoteExportApproval(confirmed: true, preflight: blocked)
    }
    #expect(throws: DocumentWorkflowError.keynotePreflightRequired) {
      try service.validateKeynoteExportApproval(confirmed: true, preflight: nil)
    }
    try service.validateKeynoteExportApproval(confirmed: true, preflight: ready)
  }

  @Test
  func artifactDiscoveryReadsControlledKeynoteArtifacts() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-KeynoteArtifacts-\(UUID().uuidString)", isDirectory: true)
    let previews = root.appendingPathComponent("previews", isDirectory: true)
    let logs = root.appendingPathComponent("logs", isDirectory: true)
    try FileManager.default.createDirectory(at: previews, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    try Data("%PDF-1.4\n%%EOF\n".utf8).write(to: previews.appendingPathComponent("keynote_export.pdf"))
    try "status=PASS\n".write(
      to: logs.appendingPathComponent("keynote_export.txt"),
      atomically: true,
      encoding: .utf8
    )
    try """
    {
      "contract_version": "2.0",
      "typed_artifacts": [
        {
          "path": "previews/keynote_export.pdf",
          "artifact_type": "preview_pdf",
          "label": "Keynote PDF",
          "primary": true
        },
        {
          "path": "logs/keynote_export.txt",
          "artifact_type": "log_txt",
          "label": "Keynote execution log",
          "primary": false
        }
      ]
    }
    """.write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)

    let discovered = ArtifactDiscovery().discover(in: root.path)
    let byPath = Dictionary(uniqueKeysWithValues: discovered.map { ($0.relativePath, $0) })
    #expect(byPath["previews/keynote_export.pdf"]?.artifactType == "preview_pdf")
    #expect(byPath["logs/keynote_export.txt"]?.artifactType == "log_txt")
  }

  @Test
  func artifactDiscoveryReadsDocumentV2Artifacts() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-DocumentArtifacts-\(UUID().uuidString)", isDirectory: true)
    let artifacts = root.appendingPathComponent("artifacts", isDirectory: true)
    let previews = root.appendingPathComponent("previews", isDirectory: true)
    try FileManager.default.createDirectory(at: artifacts, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: previews, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    try Data("docx".utf8).write(to: artifacts.appendingPathComponent("edited_copy.docx"))
    try "{}".write(to: previews.appendingPathComponent("style_diff.json"), atomically: true, encoding: .utf8)
    try """
    {
      "contract_version": "2.0",
      "typed_artifacts": [
        {
          "path": "artifacts/edited_copy.docx",
          "artifact_type": "edited_document",
          "label": "Edited document",
          "primary": true
        },
        {
          "path": "previews/style_diff.json",
          "artifact_type": "app_preview",
          "label": "Reviewed diff",
          "primary": false
        }
      ]
    }
    """.write(to: root.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)

    let discovered = ArtifactDiscovery().discover(in: root.path)
    let byPath = Dictionary(uniqueKeysWithValues: discovered.map { ($0.relativePath, $0) })
    #expect(byPath["artifacts/edited_copy.docx"]?.artifactType == "edited_document")
    #expect(byPath["previews/style_diff.json"]?.artifactType == "app_preview")
  }
}

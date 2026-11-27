import Foundation
import PDFKit
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func technicalReportUsesVerifiedResultsAndRegeneratesFromMarkdownInANewFile() async throws {
    let root = try makeScenarioFixture(
      name: "technical-run-report",
      files: [
        "input.csv": "id,flux\n1,0.42\n",
        "run/summary.json": "{\"tool\":\"profile_table\",\"app_status\":\"PASS\",\"results\":{\"rows\":1,\"columns\":2}}",
        "run/results.csv": "id,flux\n1,0.42\n",
        "run/stdout.txt": "private console text",
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let run = root.appendingPathComponent("run")
    let capability = sampleCapability()
    var job = JobRecord(capability: capability, runDirectory: run.path)
    job.status = .succeeded
    job.requestInputPaths = [root.appendingPathComponent("input.csv").path]
    job.artifacts = ArtifactDiscovery().discover(in: run.path)
    let provenance = RunProvenanceService()
    let start = await provenance.captureStart(
      request: .init(capabilityID: job.capabilityID, inputPaths: job.requestInputPaths, outputDirectory: run.path,
                     rawArguments: ""),
      capability: capability, skillRoot: root.path, outputRootConfirmationUsed: false, secrets: []
    )
    let retained = try provenance.write(start: start, job: job)
    job.artifacts.append(retained)
    let original = try Data(contentsOf: retained.url)

    let reports = TechnicalRunReportService()
    let question = "Which rows were profiled? /Users/synthetic/private.txt"
    let draft = try reports.prepare(job: job, question: question, secrets: [])
    #expect(draft.citationCount == 2)
    #expect(draft.omittedOutputs == 0)
    #expect(draft.markdown.contains("Which rows were profiled?"))
    #expect(draft.markdown.contains("Rows profiled: 1 [A2]"))
    #expect(draft.markdown.contains("### [A2] summary.json"))
    #expect(draft.markdown.contains("Generated interpretation note"))
    #expect(!draft.markdown.contains("/Users/synthetic/"))
    #expect(!draft.markdown.contains("private console text"))

    #expect(throws: TechnicalRunReportService.Unavailable.location) {
      try reports.export(job: job, question: question, parent: run, secrets: [])
    }
    let folder = try reports.export(job: job, question: question, parent: root, secrets: [])
    let markdown = folder.appendingPathComponent("report.md")
    let firstPDF = folder.appendingPathComponent("report.pdf")
    let regenerated = root.appendingPathComponent("regenerated.pdf")
    let source = try Data(contentsOf: markdown)
    let originalPDF = try Data(contentsOf: firstPDF)
    try reports.regenerate(source: markdown, destination: regenerated)
    let first = try #require(PDFDocument(data: originalPDF))
    let second = try #require(PDFDocument(url: regenerated))
    #expect(first.pageCount == second.pageCount)
    let originalText = try #require(first.string)
    #expect(originalText == second.string)
    #expect(originalText.contains("Rows profiled: 1 [A2]"))
    #expect(try Data(contentsOf: markdown) == source)
    #expect(try Data(contentsOf: firstPDF) == originalPDF)
    #expect(try Data(contentsOf: retained.url) == original)
    #expect(throws: TechnicalRunReportService.Unavailable.location) {
      try reports.regenerate(source: markdown, destination: firstPDF)
    }

    try Data("{\"tool\":\"profile_table\",\"app_status\":\"PASS\",\"results\":{\"rows\":999,\"columns\":2}}".utf8)
      .write(to: run.appendingPathComponent("summary.json"), options: .atomic)
    let afterChange = try reports.prepare(job: job, question: question, secrets: [])
    #expect(afterChange.citationCount == 1)
    #expect(afterChange.omittedOutputs == 1)
    #expect(!afterChange.markdown.contains("Rows profiled: 999"))
    #expect(!afterChange.markdown.contains("summary.json"))
    #expect(try Data(contentsOf: retained.url) == original)
  }
}

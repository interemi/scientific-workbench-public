import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func runLogExcerptBoundsTheLatestLinesAndLeavesShortLogsUnchanged() {
    let shortLog = "first\r\nlast 🔬\r\n"
    let short = RunLogExcerpt(shortLog)
    #expect(short.text == shortLog)
    #expect(!short.isTruncated)

    let log = (1...180).map { "line \($0) 🔬\r\n" }.joined()
    let excerpt = RunLogExcerpt(log)
    let lines = excerpt.text.split(whereSeparator: \.isNewline)
    #expect(excerpt.isTruncated)
    #expect(lines.count == 120)
    #expect(lines.first == "line 61 🔬")
    #expect(lines.last == "line 180 🔬")

    let longLine = String(repeating: "x🔬", count: 20_000) + " tail"
    let bounded = RunLogExcerpt(longLine)
    #expect(bounded.isTruncated)
    #expect(bounded.text.utf8.count <= 16 * 1024)
    #expect(bounded.text.hasSuffix(" tail"))
    #expect(!bounded.text.contains("�"))
  }

  @Test
  func runBundleRestoresBoundedLogTailAndTheFinalEnvelope() throws {
    let stdout = "beginning of stdout\n" + String(repeating: "log entry 🔬\n", count: 42_000)
      + "{\"tool\":\"log.fixture\",\"status\":\"OK\",\"contract_version\":\"2\"}\n"
    let stderr = "beginning of stderr\n" + String(repeating: "stderr line\n", count: 45_000) + "end of stderr\n"
    let root = try makeScenarioFixture(
      name: "large-log-sidecar",
      files: ["stdout.txt": stdout, "stderr.txt": stderr]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    var job = JobRecord(capability: sampleCapability(), runDirectory: root.path)
    JobRunBundleService().hydrate(&job)

    #expect(job.stdout.hasPrefix("beginning of stdout"))
    #expect(job.stdout.contains("Scientific Workbench truncated"))
    #expect(job.parsedTool == "log.fixture")
    #expect(job.stderr.hasSuffix("end of stderr\n"))
    #expect(job.stdout.utf8.count < 512_200)
    #expect(job.stderr.utf8.count < 512_200)
    #expect(RunLogExcerpt(job.stderr).text.hasSuffix("end of stderr\n"))
    #expect(try Data(contentsOf: root.appendingPathComponent("stdout.txt")) == Data(stdout.utf8))
    #expect(try Data(contentsOf: root.appendingPathComponent("stderr.txt")) == Data(stderr.utf8))
  }

  @Test
  func boundedLogReadRejectsSymlinkAndKeepsEmptyLogDistinctFromMissing() throws {
    let root = try makeScenarioFixture(name: "log-link", files: ["empty.txt": "", "source.txt": "retained"])
    defer { try? FileManager.default.removeItem(at: root) }
    let link = root.appendingPathComponent("stdout.txt")
    let source = root.appendingPathComponent("source.txt")
    try FileManager.default.createSymbolicLink(at: link, withDestinationURL: source)
    #expect(BoundedProcessOutput.read(at: link, maximumBytes: 100) == nil)
    #expect(BoundedProcessOutput.read(at: root.appendingPathComponent("missing.txt"), maximumBytes: 100) == nil)
    let empty = try #require(BoundedProcessOutput.read(at: root.appendingPathComponent("empty.txt"), maximumBytes: 100))
    #expect(empty.text.isEmpty && empty.totalBytes == 0 && !empty.wasTruncated)
  }
}

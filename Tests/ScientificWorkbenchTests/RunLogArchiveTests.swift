import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func workflowRetainsCompleteRedactedStreamsBeyondTheExcerptLimit() async throws {
    let startSecret = "fixture-boundary-key"
    let root = try makeScenarioFixture(
      name: "complete-redacted-logs",
      files: ["scripts/datanalysis_env.py": #"""
        import sys
        sys.stdout.write("x" * 65529 + "fixture-boundary-key" + "\n")
        for index in range(90000):
            sys.stdout.write(f"{index:06} " + "q" * 60 + "\n")
        sys.stdout.write('{"tool":"archive.fixture","status":"OK","contract_version":"2"}\n')
        sys.stderr.write("before 🔬 fixture-boundary-key after\n")
        """#]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let output = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Archive-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: output) }
    let suite = "Scientific-Workbench-Archive-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(root.path, forKey: "skillRootPath")
    defaults.set(output.path, forKey: "outputRootPath")
    defaults.set("/usr/bin/python3", forKey: "pythonExecutable")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.openAIAPIKey = startSecret
    let capability = environmentCapability()
    store.capabilities = [capability]

    let job = try #require(await store.run(capability: capability, rawArguments: ""))
    let run = URL(fileURLWithPath: job.runDirectory)
    let tail = "{\"tool\":\"archive.fixture\",\"status\":\"OK\",\"contract_version\":\"2\"}\n"
    var expected = Data((String(repeating: "x", count: 65_529) + "[REDACTED]\n").utf8)
    for i in 0..<90_000 {
      expected.append(contentsOf: (String(format: "%06d", i) + " " + String(repeating: "q", count: 60) + "\n").utf8)
    }
    expected.append(contentsOf: tail.utf8)
    let stdout = run.appendingPathComponent("stdout.txt")
    #expect(try Data(contentsOf: stdout) == expected)
    #expect(try String(contentsOf: run.appendingPathComponent("stderr.txt"), encoding: .utf8)
      == "before 🔬 [REDACTED] after\n")
    #expect(job.status == .succeeded)
    #expect(job.parsedTool == "archive.fixture")
    #expect(job.stdout.hasSuffix(tail))
    #expect(job.stdout.utf8.count < 512_200)
    #expect(!job.stdout.contains(startSecret))
    #expect(!job.stderr.contains(startSecret))
  }

  @Test
  func logArchiveHandlesUTF8AndCanonicalSecretsAcrossChunksWithoutFollowingDestinationLinks() throws {
    let secret = "léttér123"
    let prefix = String(repeating: "x", count: RunLogArchive.chunkBytes - 1)
    let text = prefix + "🔬 le\u{301}ttér123 then retained\r\n"
    let root = try makeScenarioFixture(
      name: "log-archive-canonical",
      files: ["source.txt": text, "outside.txt": "original input"]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let run = root.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: false)
    let outside = root.appendingPathComponent("outside.txt")
    let target = run.appendingPathComponent("stdout.txt")
    try FileManager.default.createSymbolicLink(at: target, withDestinationURL: outside)
    let archive = RunLogArchive(runDirectory: run.path, secrets: [])
    let result = try #require(archive.retain(
      from: root.appendingPathComponent("source.txt"), stream: .stdout,
      maximumInputBytes: 100_000, maximumExcerptBytes: 256, additionalSecrets: [secret]
    ))
    #expect(result.totalBytes == text.utf8.count)
    #expect(result.wasTruncated)
    #expect(try Data(contentsOf: target) == Data((prefix + "🔬 [REDACTED] then retained\r\n").utf8))
    #expect(try String(contentsOf: outside, encoding: .utf8) == "original input")
    #expect(try FileManager.default.contentsOfDirectory(atPath: run.path) == ["stdout.txt"])
    let permissions = try FileManager.default.attributesOfItem(atPath: target.path)[.posixPermissions] as? NSNumber
    #expect(permissions?.intValue == 0o600)
  }

  @Test
  func processRunnerRetainsBoundedRedactedPrefixWhenStoppedByOutputLimit() async throws {
    let root = try makeScenarioFixture(name: "log-archive-limit", files: ["original.txt": "unchanged"])
    defer { try? FileManager.default.removeItem(at: root) }
    let secret = "fixture-limit-token"
    let archive = RunLogArchive(runDirectory: root.path, secrets: [secret])
    let runner = ProcessRunner(maximumCapturedOutputBytes: 256, maximumTemporaryOutputBytesPerStream: 4096)
    let command = ProcessCommand(
      executable: "/usr/bin/python3",
      arguments: ["-c", #"""
        import sys
        print("first fixture-limit-token")
        sys.stdout.write("x" * (4096 - 27 - 4) + "fixture-limit-token" + "z" * 50000)
        """#],
      workingDirectory: nil
    )
    await #expect(throws: ProcessRunnerError.outputLimitExceeded(stream: "stdout", limitBytes: 4096)) {
      try await runner.run(command, retainingLogs: archive)
    }
    let log = try String(contentsOf: root.appendingPathComponent("stdout.txt"), encoding: .utf8)
    #expect(log.hasPrefix("first [REDACTED]\n"))
    #expect(log.hasSuffix("exceeded its output limit.]\n"))
    #expect(!log.contains("fixture-"))
    #expect(log.utf8.count < 4200)
    #expect(try String(contentsOf: root.appendingPathComponent("original.txt"), encoding: .utf8) == "unchanged")
  }
}

import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func cancellingJobRetainsPartialFilesAndCapturedLogsInItsRunFolder() async throws {
    let skillRoot = try makeScenarioFixture(
      name: "cancelled-job",
      files: [
        "scripts/datanalysis_env.py": """
          import sys
          import time
          from pathlib import Path

          if sys.argv[1:4] != ["run-tool", "datanalysis_env", "status"]:
              raise SystemExit(2)
          summary = Path(sys.argv[5])
          print("partial stdout", flush=True)
          print("partial stderr", file=sys.stderr, flush=True)
          (summary.parent / "partial.txt").write_text("retained", encoding="utf-8")
          time.sleep(30)
          """
      ]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Cancel-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }
    let suite = "Scientific-Workbench-Cancel-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(skillRoot.path, forKey: "skillRootPath")
    defaults.set(outputRoot.path, forKey: "outputRootPath")
    defaults.set("/usr/bin/python3", forKey: "pythonExecutable")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let capability = environmentCapability()
    store.capabilities = [capability]

    let task = Task { await store.run(capability: capability, rawArguments: "") }
    let deadline = Date().addingTimeInterval(5)
    while Date() < deadline {
      if let job = store.jobs.first,
         FileManager.default.fileExists(
           atPath: URL(fileURLWithPath: job.runDirectory)
             .appendingPathComponent("partial.txt").path
         ) {
        break
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    let runningJob = try #require(store.jobs.first)
    let runURL = URL(fileURLWithPath: runningJob.runDirectory)
    let partialURL = runURL.appendingPathComponent("partial.txt")
    guard FileManager.default.fileExists(atPath: partialURL.path) else {
      store.cancelActiveRun()
      _ = await task.value
      Issue.record("The synthetic process did not reach its partial-output marker.")
      return
    }

    store.cancelActiveRun()
    let result = try #require(await task.value)
    #expect(result.status == .cancelled)
    #expect(result.stdout.contains("partial stdout"))
    #expect(result.stderr.contains("partial stderr"))
    #expect(try String(contentsOf: partialURL, encoding: .utf8) == "retained")
    #expect(try String(contentsOf: runURL.appendingPathComponent("stdout.txt"), encoding: .utf8).contains("partial stdout"))
    #expect(try String(contentsOf: runURL.appendingPathComponent("stderr.txt"), encoding: .utf8).contains("partial stderr"))
    #expect(FileManager.default.fileExists(atPath: runURL.appendingPathComponent("next_steps.md").path))
    #expect(result.artifacts.contains { $0.relativePath == "partial.txt" })
  }
}

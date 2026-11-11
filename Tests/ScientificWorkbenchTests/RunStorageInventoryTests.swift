import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func storageInventoryCountsLiveFilesOnlyInScopedRunFolders() throws {
    let fixture = try makeScenarioFixture(
      name: "storage-inventory",
      files: [
        "output/run/stdout.txt": "standard output",
        "output/run/stderr.txt": "failure",
        "output/run/logs/extra/trace.txt": "trace",
        "output/run/previews/report.pdf": "preview",
        "output/run/artifacts/result.csv": "value\n1\n",
        "output/originals/stdout.txt": "original",
        "output/unrecorded/stdout.txt": "unrecorded",
        "outside/logs/retained.txt": "outside",
      ]
    )
    defer { try? FileManager.default.removeItem(at: fixture) }
    let output = fixture.appendingPathComponent("output", isDirectory: true)
    let run = output.appendingPathComponent("run", isDirectory: true)
    let outside = fixture.appendingPathComponent("outside", isDirectory: true)
    let originals = output.appendingPathComponent("originals", isDirectory: true)
    let fileManager = FileManager.default
    try fileManager.createSymbolicLink(
      at: run.appendingPathComponent("logs/linked-folder"), withDestinationURL: outside
    )
    try fileManager.createSymbolicLink(
      at: run.appendingPathComponent("previews/linked-file.pdf"),
      withDestinationURL: originals.appendingPathComponent("stdout.txt")
    )
    try fileManager.createSymbolicLink(
      at: output.appendingPathComponent("linked-run"), withDestinationURL: outside
    )
    let jobs = [run, run, output, originals, outside, output.appendingPathComponent("linked-run"),
                output.appendingPathComponent("missing")].map {
      JobRecord(capability: sampleCapability(), runDirectory: $0.path)
    }
    let inventory = try RunStorageInventory.measure(outputRoot: output.path, jobs: jobs, inputPaths: [originals.path])

    #expect(inventory.retainedStreamBytes == 22)
    #expect(inventory.runLogBytes == 5)
    #expect(inventory.runPreviewBytes == 7)
    #expect(inventory.measuredFolders == 1)
    #expect(inventory.skippedFolders == 4)
    #expect(!inventory.hasUnreadableEntries)
    #expect(try String(contentsOf: run.appendingPathComponent("stderr.txt"), encoding: .utf8) == "failure")
    #expect(try String(contentsOf: originals.appendingPathComponent("stdout.txt"), encoding: .utf8) == "original")
    #expect(try String(contentsOf: run.appendingPathComponent("artifacts/result.csv"), encoding: .utf8) == "value\n1\n")
  }

  @Test
  func storageInventoryRejectsInputAsOutputRoot() throws {
    let fixture = try makeScenarioFixture(name: "storage-root-input", files: ["input.csv": "value\n1\n"])
    defer { try? FileManager.default.removeItem(at: fixture) }

    #expect(throws: FilesystemSafetyError.self) {
      try RunStorageInventory.measure(outputRoot: fixture.path, jobs: [], inputPaths: [fixture.path])
    }
  }
}

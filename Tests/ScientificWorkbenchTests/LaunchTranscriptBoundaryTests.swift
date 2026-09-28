import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func launchAutomationRejectsTranscriptOutsideDedicatedOutputParent() async throws {
    let base = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Launch-Boundary-\(UUID().uuidString)", isDirectory: true)
    let outputRoot = base.appendingPathComponent("run_output", isDirectory: true)
    let outsideTranscript = base
      .appendingPathComponent("outside", isDirectory: true)
      .appendingPathComponent("transcript.json")
    defer { try? FileManager.default.removeItem(at: base) }

    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    await store.runLaunchAutomation(
      LaunchAutomationOptions(
        prompt: "Plan a safe local workflow.",
        mode: .workflow,
        outputRootPath: outputRoot.path,
        forceLocalPlanner: true,
        transcriptPath: outsideTranscript.path
      )
    )

    #expect(!FileManager.default.fileExists(atPath: outsideTranscript.path))
    #expect(store.agentStatusMessage.contains("Launch transcript blocked"))
  }

  @Test
  @MainActor
  func launchAutomationRefusesToOverwriteExistingTranscript() async throws {
    let outputRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Launch-Overwrite-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: outputRoot) }
    let transcript = outputRoot.appendingPathComponent("transcript.json")
    try Data("historical evidence\n".utf8).write(to: transcript, options: [.atomic])

    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    await store.runLaunchAutomation(
      LaunchAutomationOptions(
        prompt: "Plan a safe local workflow.",
        mode: .workflow,
        outputRootPath: outputRoot.path,
        forceLocalPlanner: true,
        transcriptPath: transcript.path
      )
    )

    #expect(try String(contentsOf: transcript, encoding: .utf8) == "historical evidence\n")
    #expect(store.agentStatusMessage.contains("already exists"))
  }
}

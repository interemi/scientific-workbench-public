import Combine
import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func capturedOutputOverrideCannotWriteInsideOriginalInputs() async throws {
    let root = try makeScenarioFixture(name: "captured-output-boundary", files: ["inputs/table.csv": "x\n1\n"])
    defer { try? FileManager.default.removeItem(at: root) }
    let inputs = root.appendingPathComponent("inputs")
    let original = try Data(contentsOf: inputs.appendingPathComponent("table.csv"))
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Captured-Output-\(UUID())")!
    defaults.set(root.appendingPathComponent("safe-output").path, forKey: "outputRootPath")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    store.inputPaths = [inputs.path]

    let job = await store.run(capability: sampleCapability(), rawArguments: "",
      outputRootPathOverride: inputs.path)
    #expect(job == nil)
    #expect(store.jobs.isEmpty)
    #expect(store.agentStatusMessage.contains("Unsafe output root"))
    #expect(try Data(contentsOf: inputs.appendingPathComponent("table.csv")) == original)
    #expect(try FileManager.default.contentsOfDirectory(atPath: inputs.path) == ["table.csv"])
  }

  @Test
  @MainActor
  func workflowKeepsCapturedInputsAndOutputRootForLaterStepsAndSummaryWhenSelectionChanges() async throws {
    let root = try makeScenarioFixture(name: "workflow-input-context", files: [
      "inputs/original.csv": "x,y\n1,2\n",
      "inputs/another.csv": "x,y\n3,4\n",
      "skill/scripts/datanalysis_env.py": """
        import json
        import sys
        from pathlib import Path

        if len(sys.argv) != 6 or sys.argv[1:3] != ["run-tool", "profile_table"] or sys.argv[4] != "--summary-json":
            raise SystemExit(2)
        if not Path(sys.argv[3]).is_file():
            raise SystemExit(3)
        payload = {"status": "ok", "tool": "profile_table", "input_used": sys.argv[3]}
        Path(sys.argv[5]).write_text(json.dumps(payload), encoding="utf-8")
        print(json.dumps(payload))
        """
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let original = root.appendingPathComponent("inputs/original.csv")
    let another = root.appendingPathComponent("inputs/another.csv")
    let originalBytes = try Data(contentsOf: original)
    let anotherBytes = try Data(contentsOf: another)
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Captured-Inputs-\(UUID())")!
    let output = root.appendingPathComponent("output").path
    let futureOutput = root.appendingPathComponent("future-output").path
    defaults.set(output, forKey: "outputRootPath")
    defaults.set(root.appendingPathComponent("skill").path, forKey: "skillRootPath")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let capability = sampleCapability()
    store.capabilities = [capability]
    store.inputPaths = [original.path]
    let steps = ["First inspection", "Second inspection"].map {
      AgentPlanStep(capabilityID: capability.id, summary: $0,
        rawArguments: "{input0} --summary-json {summaryJson}", usesInputs: true, usesPreviousOutput: false)
    }
    store.agentPlan = AgentPlan(title: "Captured inputs", rationale: "Selection can change during a run",
      steps: steps, source: .local)
    var selectionChanged = false
    let observer = store.$jobs.sink { jobs in
      guard !selectionChanged, jobs.first?.status == .running else { return }
      selectionChanged = true
      store.inputPaths = [another.path]
      store.outputRootPath = futureOutput
    }
    defer { observer.cancel() }

    let result = await store.runAgentPlan()
    #expect(selectionChanged)
    #expect(result.contains("Workflow finished: 2/2"))
    #expect(store.inputPaths == [another.path])
    #expect(store.outputRootPath == futureOutput)
    #expect(store.jobs.count == 2)
    #expect(store.jobs.allSatisfy { $0.status == .succeeded && $0.requestInputPaths == [original.path] })
    #expect(store.jobs.allSatisfy { $0.command.contains(original.path) && !$0.command.contains(another.path) })
    #expect(store.jobs.allSatisfy { FilesystemPath.canonicalURL($0.runDirectory).path.hasPrefix(FilesystemPath.canonicalURL(output).path + "/") })
    let summaryPath = try #require(store.lastWorkflowSummaryPath)
    let summary = try String(contentsOfFile: summaryPath, encoding: .utf8)
    #expect(summary.contains("`\(original.path)` (read-only)"))
    #expect(!summary.contains(another.path))
    #expect(summary.contains(output))
    #expect(!summary.contains(futureOutput))
    #expect(FilesystemPath.canonicalURL(summaryPath).path.hasPrefix(FilesystemPath.canonicalURL(output).path + "/"))
    #expect(try Data(contentsOf: original) == originalBytes)
    #expect(try Data(contentsOf: another) == anotherBytes)
  }
}

import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func verifyRunRechecksInputsOutputsToolAndSelectedRuntimeWithoutRerunningTheJob() async throws {
    let root = try makeScenarioFixture(
      name: "verify-run",
      files: [
        "input/table.csv": "x,y\n1,2\n",
        "skills/public_surface_registry.yaml": """
          registry_schema_version: 1
          release: v2.8
          entries:
            - id: profile_table
              label: Table profile
              script: scripts/profile_table.py
              visible_block: notebooks + cross-domain
              kind: golden_path
              support_level: stable
              platform: datanalysis
              requires_datanalysis: true
              preflight_mode: none
              smoke_tier: core
              short_description: Profile a synthetic table.
          """,
        "skills/scripts/profile_table.py": "# Synthetic tool identity\n",
        "skills/scripts/datanalysis_env.py": """
          import json, os, platform, sys
          from importlib.metadata import PackageNotFoundError, version
          from pathlib import Path

          if sys.argv[1:4] == ["python", "-B", "-c"]:
              source = sys.argv[4]
              if Path("runtime-changed").exists():
                  print(json.dumps({"pythonImplementation": "cpython", "pythonVersion": "3.22.1",
                                    "architecture": platform.machine(), "profilePackages": {}}))
              else:
                  sys.argv = ["-c"] + sys.argv[5:]
                  exec(source)
              raise SystemExit(0)

          assert sys.argv[1:3] == ["run-tool", "profile_table"]
          with Path("execution-counter").open("a") as stream:
              stream.write("run\\n")
          summary = Path(sys.argv[sys.argv.index("--summary-json") + 1])
          summary.write_text(json.dumps({"tool": "profile_table", "app_status": "PASS"}))
          (summary.parent / "result.csv").write_text("value\\n1\\n")
          request = json.loads(os.environ["SCIENTIFIC_WORKBENCH_RUNTIME_EVIDENCE"])
          packages = {}
          for name in request["packages"]:
              try:
                  packages[name] = version(name)
              except PackageNotFoundError:
                  pass
          Path(request["destination"]).write_text(json.dumps({
              "schemaVersion": 1, "tool": "profile_table", "implementation": sys.implementation.name,
              "version": platform.python_version(), "architecture": platform.machine(), "packages": packages,
          }))
          """,
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let defaultsName = "Scientific-Workbench-Verify-\(UUID())"
    let defaults = try #require(UserDefaults(suiteName: defaultsName))
    defer { defaults.removePersistentDomain(forName: defaultsName) }
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let input = root.appendingPathComponent("input/table.csv")
    let skill = root.appendingPathComponent("skills")
    store.skillRootPath = skill.path
    store.outputRootPath = root.appendingPathComponent("runs").path
    store.pythonExecutable = "/usr/bin/python3"
    let entries = try CapabilityRegistryLoader().load(skillRoot: skill.path)
    store.capabilities = entries
    let capability = try #require(entries.first)
    let job = try #require(await store.run(capability: capability, rawArguments: "", inputPathsOverride: [input.path]))
    #expect(job.status == .succeeded)
    let output = URL(fileURLWithPath: job.runDirectory).appendingPathComponent("result.csv")
    let provenance = URL(fileURLWithPath: job.runDirectory).appendingPathComponent(JobRunProvenance.filename)
    let baseline = try Data(contentsOf: provenance)
    let completed = try #require(await store.verifyJob(job))
    for subject in ["Original run", "Inputs", "Retained outputs", "Skill", "Permissions", "Command", "Python runtime"] {
      #expect(completed.checks.first { $0.subject == subject }?.status == .matches)
    }
    #expect(completed.replayBlockReason == "The original run has no complete local execution record.")
    #expect(await store.replayJob(job) == completed.replayBlockReason)

    try Data("x,y\n1,3\n".utf8).write(to: input, options: .atomic)
    try Data("value\n9\n".utf8).write(to: output, options: .atomic)
    try Data("# Changed entrypoint\n".utf8).write(to: skill.appendingPathComponent("scripts/profile_table.py"), options: .atomic)
    try Data().write(to: skill.appendingPathComponent("runtime-changed"))
    let changed = try #require(await store.verifyJob(job))
    for subject in ["Inputs", "Retained outputs", "Skill", "Python runtime"] {
      #expect(changed.checks.first { $0.subject == subject }?.status == .changed)
    }
    #expect(!changed.matchesRecordedEvidence)
    #expect(store.jobs.map(\.id) == [job.id])
    #expect(try String(contentsOf: skill.appendingPathComponent("execution-counter"), encoding: .utf8) == "run\n")
    #expect(try Data(contentsOf: provenance) == baseline)
    #expect(try String(contentsOf: input, encoding: .utf8) == "x,y\n1,3\n")
  }

  @Test
  func replayRebasesOnlyAttachedInputsAndNewRunDestinations() throws {
    let root = try makeScenarioFixture(name: "replay-relative-paths", files: ["input/synthetic table.csv": "x\n1\n"])
    defer { try? FileManager.default.removeItem(at: root) }
    let base = FilesystemPath.canonicalURL(root.path)
    let original = base.appendingPathComponent("original")
    let replay = base.appendingPathComponent("replay")
    let input = base.appendingPathComponent("input/synthetic table.csv").path
    let copy = replay.appendingPathComponent("inputs/1/synthetic table.csv").path
    let capability = sampleCapability()
    let prefix = ["datanalysis_env.py", "run-tool", capability.scriptStem]
    let output = original.appendingPathComponent("summary.json").path
    let arguments = [input, "--summary-json=\(output)", "--max-columns", "3"]
    let command = ProcessCommand(executable: "/usr/bin/python3", arguments: prefix + arguments, workingDirectory: base.path)
    let rebased = try RunReplayService.remap(command, capability: capability, old: original, root: replay,
                                             inputLocations: [input: copy])
    #expect(rebased == [copy, "--summary-json=\(replay.appendingPathComponent("summary.json").path)", "--max-columns", "3"])
    for path in [base.appendingPathComponent("untracked.csv").path,
                 original.appendingPathComponent("inputs/protected.csv").path,
                 original.appendingPathComponent("replay-comparison.json").path] {
      let unsafe = ProcessCommand(executable: command.executable, arguments: prefix + [input, "--summary-json", path],
                                  workingDirectory: base.path)
      #expect(throws: RunReplayService.Unavailable.self) {
        try RunReplayService.remap(unsafe, capability: capability, old: original, root: replay, inputLocations: [input: copy])
      }
    }
    #expect(try String(contentsOfFile: input, encoding: .utf8) == "x\n1\n")
    #expect(!FileManager.default.fileExists(atPath: replay.path))
  }

  @Test
  func replayComparisonAppliesToleranceOnlyToMeasurementColumns() throws {
    let root = try makeScenarioFixture(
      name: "replay-numeric-comparison",
      files: [
        "original.csv": "id,match_sep_arcsec,label\r\n1234567890123456789,0.2,\"example, A\"\r\n",
        "rounded.csv": "id,match_sep_arcsec,label\n1234567890123456789,0.20000000002,\"example, A\"\n",
        "changed.csv": "id,match_sep_arcsec,label\n1234567890123456788,0.21,\"example, A\"\n",
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let original = root.appendingPathComponent("original.csv")
    let digest = RunFileFingerprint.read(original, maximumBytes: 1_024)
    for (name, expected) in [("rounded.csv", 0), ("changed.csv", 2)] {
      let new = root.appendingPathComponent(name)
      let measurement = try #require(RunReplayComparison.compareTable(
        original, new, original: digest, replay: RunFileFingerprint.read(new, maximumBytes: 1_024),
        columns: ["match_sep_arcsec"]
      ))
      #expect(measurement.compared == 1)
      #expect(measurement.differences == expected)
      #expect(measurement.maximum > 0)
    }
  }
}

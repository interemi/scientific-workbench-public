import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func workbenchRunRetainsPathNeutralFileFingerprints() async throws {
    let root = try makeScenarioFixture(
      name: "run-provenance",
      files: [
        "private-observer.csv": "hello",
        "skills/scripts/profile_table.py": "hello",
        "skills/fixtures/profile_table.py": "world",
        "skills/fixtures/datanalysis_env.py": "launcher body",
        "skills/fixtures/_internal/fixture_script_dispatch.py": "dispatcher body",
        "skills/scripts/_internal/fixture_script_dispatch.py": "dispatch shim",
        "skills/scripts/_internal/deferred_internal.py": "deferred helper",
        "skills/scripts/datanalysis_env.py": """
          import json
          import os
          from pathlib import Path
          import sys

          assert "--title=synthetic-secret-argument" in sys.argv
          summary = Path(sys.argv[sys.argv.index("--summary-json") + 1])
          output = summary.parent / "private-observer-product.csv"
          output.write_text("world")
          summary.write_text(json.dumps({"tool": "profile_table", "contract_version": "1.8", "app_status": "PASS"}))
          request = json.loads(os.environ["SCIENTIFIC_WORKBENCH_RUNTIME_EVIDENCE"])
          Path(request["destination"]).write_text(json.dumps({
              "schemaVersion": 1, "tool": request["tool"], "implementation": "cpython",
              "version": "3.11.14", "architecture": "arm64",
              "packages": {"pandas": "2.3.0", "numpy": "1.0+private-observer", "private-observer": "1.0"},
              "inventorySHA256": "a" * 64,
          }))
          """,
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let domain = "Scientific-Workbench-Tests-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: domain))
    defer { defaults.removePersistentDomain(forName: domain) }
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)
    let source = root.appendingPathComponent("private-observer.csv")
    store.skillRootPath = root.appendingPathComponent("skills").path
    store.outputRootPath = root.appendingPathComponent("runs").path
    store.pythonExecutable = "/usr/bin/python3"

    let job = try #require(await store.runGuided(
      capability: sampleCapability(), inputPathsOverride: [source.path], selectJobs: false
    ) { runURL in
      [
        source.path, "--title=synthetic-secret-argument",
        "--summary-json", runURL.appendingPathComponent("summary.json").path,
      ]
    })
    #expect(job.status == .succeeded)
    let provenance = try #require(job.artifacts.first { $0.relativePath == JobRunProvenance.filename })
    let received = root.appendingPathComponent("received")
    try FileManager.default.createDirectory(at: received, withIntermediateDirectories: false)
    let sharedCopy = received.appendingPathComponent(JobRunProvenance.filename)
    try FileManager.default.copyItem(at: provenance.url, to: sharedCopy)
    #expect(try FileManager.default.contentsOfDirectory(atPath: received.path) == [JobRunProvenance.filename])
    let retained = try Data(contentsOf: sharedCopy)
    let payload = try #require(JSONSerialization.jsonObject(with: retained) as? [String: Any])
    let normalized = try JSONSerialization.data(withJSONObject: payload, options: [.withoutEscapingSlashes])
    let text = String(decoding: normalized, as: UTF8.self)
    #expect(!text.contains(source.path))
    #expect(!text.contains("private-observer"))
    #expect(!text.contains("synthetic-secret-argument"))
    #expect(!text.contains(store.outputRootPath))
    #expect(!text.contains(store.skillRootPath))
    #expect(!text.contains(store.pythonExecutable))
    let record = try JSONDecoder.scientificWorkbench.decode(JobRunProvenance.self, from: retained)
    #expect(record.schemaVersion == 1)
    #expect(record.jobID == job.id)
    #expect(record.tool.capabilityID == "profile_table")
    #expect(record.reportedToolContractVersion == "1.8")
    #expect(record.hostMacOSVersion != nil)
    #expect(record.status == .succeeded)
    #expect(record.exitCode == 0)
    let command = try #require(record.command)
    #expect(command.arguments.map(\.kind) == [.input, .withheld, .runLocation])
    #expect(command.arguments.map(\.reference) == ["input-1", nil, "run-location-1"])
    #expect(command.arguments.map(\.option) == [nil, "--title", "--summary-json"])
    #expect(record.runtime?.pythonImplementation == "cpython")
    #expect(record.runtime?.pythonVersion == "3.11.14")
    #expect(record.runtime?.profilePackages == ["pandas": "2.3.0"])
    #expect(record.runtime?.inventorySHA256 == nil)
    #expect(!text.contains("inventorySHA256"))
    let receipt = try #require(RunExecutionEvidence.read(for: job))
    #expect(receipt.pythonInventorySHA256 == String(repeating: "a", count: 64))
    #expect(!job.artifacts.contains { $0.relativePath == RunExecutionEvidence.filename })
    let receiptURL = URL(fileURLWithPath: job.runDirectory).appendingPathComponent(RunExecutionEvidence.filename)
    let receiptText = try String(contentsOf: receiptURL, encoding: .utf8)
    #expect(!receiptText.contains("synthetic-secret-argument"))
    #expect(!receiptText.contains(source.path))
    let skillRoot = store.skillRootPath
    let builder = CapabilityCommandBuilder(
      pythonExecutable: store.pythonExecutable, timeoutSeconds: store.externalProcessTimeoutSeconds
    )
    let current = try builder.build(
      capability: sampleCapability(), request: .init(capabilityID: job.capabilityID, inputPaths: job.requestInputPaths,
        outputDirectory: job.runDirectory, rawArguments: job.requestRawArguments),
      skillRoot: skillRoot
    )
    #expect(RunExecutionEvidence.commandDigest(current, secrets: []) == receipt.commandSHA256)
    #expect(RunExecutionEvidence.commandDigest(current, secrets: ["synthetic-secret-argument"]) == nil)
    var changed = current
    changed.environmentOverrides["LC_ALL"] = "C"
    #expect(RunExecutionEvidence.commandDigest(changed, secrets: []) != receipt.commandSHA256)
    try Data("changed".utf8).write(to: URL(fileURLWithPath: skillRoot).appendingPathComponent("fixtures/datanalysis_env.py"))
    #expect(RunExecutionEvidence.commandDigest(current, secrets: []) != receipt.commandSHA256)
    #expect(!record.limits.contains(.runtimeAndDependencyVersionsNotCaptured))
    let runFiles = try FileManager.default.contentsOfDirectory(atPath: job.runDirectory)
    #expect(!runFiles.contains { $0.hasPrefix(".swb-runtime-") })
    #expect(record.startedAt != nil)
    #expect(record.finishedAt != nil)
    #expect(!record.outputRootConfirmationUsed)
    let hello = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    let world = "486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7"
    #expect(record.tool.entryPointSHA256 == hello)
    #expect(record.tool.implementationSHA256 == world)
    #expect(record.inputs.map(\.id) == ["input-1"])
    let input = try #require(record.inputs.first)
    #expect(input.before.sha256 == hello)
    #expect(input.after.sha256 == hello)
    #expect(input.contentUnchanged == true)
    #expect(record.outputs.contains { $0.fingerprint.sha256 == world })
    #expect(record.outputs.filter { $0.commandReference == "run-location-1" }.count == 1)
    #expect(record.limits.contains(.localArgumentsRequired))
    #expect(record.limits.contains(.runtimeInventoryPartial))
    #expect(record.limits.contains(.skillReleaseNotRecorded))
    #expect(record.limits.contains(.skillCodeIdentityIncomplete))
    let requirements = try #require(record.reproductionRequirements)
    #expect(requirements.map(\.limit) == record.limits)
    #expect(requirements.first { $0.limit == .fileContentsNotIncluded }?.guidance.contains("SHA-256") == true)
    #expect(requirements.first { $0.limit == .localArgumentsRequired }?.guidance.contains("withheld") == true)
    var earlierPayload = payload
    for key in ["hostMacOSVersion", "reportedToolContractVersion", "reproductionRequirements"] {
      earlierPayload.removeValue(forKey: key)
    }
    earlierPayload["limits"] = ["attached_input_scope", "local_arguments_required", "backend_and_model_not_captured"]
    let earlierRecord = try JSONDecoder.scientificWorkbench.decode(
      JobRunProvenance.self, from: JSONSerialization.data(withJSONObject: earlierPayload)
    )
    #expect(earlierRecord.jobID == record.jobID)
    #expect(earlierRecord.reproductionRequirements == nil)
    #expect(earlierRecord.limits.contains(.backendAndModelNotCaptured))
    #expect(try String(contentsOf: source, encoding: .utf8) == "hello")
  }

  @Test
  func runProvenanceDistinguishesChangedInputsAndPreservesAnExistingRecord() async throws {
    let root = try makeScenarioFixture(
      name: "run-provenance-changed-input",
      files: [
        "attached.csv": "hello",
        "relinked.csv": "hello",
        "folder/nested.csv": "world",
        "run/summary.json": "{}",
        "run/inputs/staged.csv": "staged",
        "outside.csv": "outside",
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let source = root.appendingPathComponent("attached.csv")
    let directory = root.appendingPathComponent("folder")
    let missing = root.appendingPathComponent("missing.csv")
    let relinked = root.appendingPathComponent("relinked.csv")
    let run = root.appendingPathComponent("run")
    let capability = sampleCapability()
    let request = RunRequest(
      capabilityID: capability.id, inputPaths: [source.path, directory.path, missing.path, relinked.path],
      outputDirectory: run.path, rawArguments: ""
    )
    let service = RunProvenanceService()
    let start = await service.captureStart(
      request: request, capability: capability, skillRoot: root.path,
      outputRootConfirmationUsed: true, secrets: []
    )
    try Data("world".utf8).write(to: source, options: .atomic)
    try FileManager.default.moveItem(at: relinked, to: root.appendingPathComponent("retained.csv"))
    try FileManager.default.createSymbolicLink(at: relinked, withDestinationURL: root.appendingPathComponent("outside.csv"))

    let realOutputs = ArtifactDiscovery().discover(in: run.path)
    var job = JobRecord(capability: capability, runDirectory: run.path)
    job.artifacts = realOutputs + [
      Artifact(path: root.appendingPathComponent("outside.csv").path, relativePath: "outside.csv", byteCount: 7)
    ]
    job.status = .failed
    let artifact = try service.write(start: start, job: job)
    let retained = try Data(contentsOf: artifact.url)
    let record = try JSONDecoder.scientificWorkbench.decode(JobRunProvenance.self, from: retained)
    #expect(record.status == .failed)
    #expect(record.outputRootConfirmationUsed)
    #expect(record.approvals == [.outputRoot])
    #expect(record.inputs.map { $0.before.state } == [.recorded, .directory, .missing, .recorded])
    #expect(record.inputs.map { $0.after.state } == [.recorded, .directory, .missing, .changed])
    #expect(record.inputs.map(\.contentUnchanged) == [false, nil, nil, nil])
    #expect(record.outputs.count == 1)
    #expect(record.limits.contains(.directoryContentsNotCaptured))
    #expect(record.limits.contains(.incompleteFingerprints))
    #expect(record.limits.contains(.inputContentChanged))
    #expect(record.runtime == nil)
    #expect(record.limits.contains(.runtimeAndDependencyVersionsNotCaptured))
    #expect(record.limits.contains(.unsuccessfulRun))
    #expect(record.limits.contains(.commandNotRecorded))
    #expect(throws: (any Error).self) { try service.write(start: start, job: job) }
    #expect(try Data(contentsOf: artifact.url) == retained)
    #expect(RunFileFingerprint.read(source, maximumBytes: 4).state == .overBudget)
  }

  @Test
  func runRuntimePackageAllowlistMatchesBundledProfiles() throws {
    let checkout = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent()
    let root = checkout.appendingPathComponent("skills/scientific-data-analysis")
    let declared = try ["core", "full"].flatMap { profile in
      let text = try String(contentsOf: root.appendingPathComponent("requirements-\(profile).txt"), encoding: .utf8)
      return text.split(whereSeparator: \.isNewline).filter { !$0.hasPrefix("#") && !$0.hasPrefix("-r ") }.map(String.init)
    }
    #expect(Set(RunRuntimeEvidence.profilePackageNames) == Set(declared))
  }

  @Test
  func runCommandEvidenceProjectsVersionedScientificValuesAndWithholdsFreeText() throws {
    let checkout = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent()
    let mother = checkout.appendingPathComponent("skills/scientific-data-analysis").path
    let entries = try CapabilityRegistryLoader().load(skillRoot: mother)
    let fixture = try makeScenarioFixture(
      name: "typed-run-command",
      files: ["private catalogue.csv": "ra,dec\n1,2\n", "comparison.tsv": "ra\tdec\n1\t2\n"]
    )
    defer { try? FileManager.default.removeItem(at: fixture) }
    let run = FilesystemPath.canonicalURL(fixture.appendingPathComponent("fresh run").path)
    let first = FilesystemPath.canonicalURL(fixture.appendingPathComponent("private catalogue.csv").path)
    let second = FilesystemPath.canonicalURL(fixture.appendingPathComponent("comparison.tsv").path)
    let output = run.appendingPathComponent("products/private-observer.csv").path

    func capture(_ id: String, _ argv: [String], secrets: [String] = []) throws -> RunCommandEvidence {
      let entry = try #require(entries.first { $0.id == id })
      let command = ProcessCommand(
        executable: "/private/python", arguments: ["/private/wrapper.py", "run-tool", entry.scriptStem] + argv,
        workingDirectory: "/private"
      )
      let record = try #require(RunCommandEvidence.capture(
        command: command, capability: entry, inputURLs: [first, second], runRoot: run, secrets: secrets
      ))
      return record.evidence
    }

    let crossmatch = try capture("catalog_workbench.crossmatch-sky", [
      "crossmatch-sky", first.path, second.path, output, "--left-ra=private-observer",
      "--left-ra-unit", "hourangle", "--left-dec-unit", "rad",
      "--coordinate-epoch-jyear", "2016.25", "--radius-arcsec=1.25", "--summary-json", output,
    ])
    #expect(crossmatch.operation == "crossmatch-sky")
    #expect(crossmatch.arguments.prefix(3).map(\.reference) == ["input-1", "input-2", "run-location-1"])
    #expect(crossmatch.arguments[3].kind == .withheld)
    #expect(crossmatch.arguments[4].choice == "hourangle")
    #expect(crossmatch.arguments[5].choice == "rad")
    #expect(crossmatch.arguments[6].numbers == [2016.25])
    #expect(crossmatch.arguments[7].numbers == [1.25])
    #expect(crossmatch.arguments[8].reference == "run-location-1")
    #expect(crossmatch.requiresLocalArguments)
    let redacted = String(decoding: try JSONEncoder.scientificWorkbench.encode(crossmatch), as: UTF8.self)
    #expect(!redacted.contains("private-observer"))
    #expect(!redacted.contains("private catalogue"))
    #expect(!redacted.contains(run.path))
    #expect(!redacted.contains("wrapper.py"))

    let fits = try capture("inspect_fits", [
      first.path, "--extension", "2", "--crop=1,2,16,24", "--pixel", "4,5", "--preview-if-available",
      "--header-key", "CDELT1",
    ])
    #expect(fits.arguments[1].integers == [2])
    #expect(fits.arguments[2].integers == [1, 2, 16, 24])
    #expect(fits.arguments[3].integers == [4, 5])
    #expect(fits.arguments[4].kind == .flag)
    #expect(fits.arguments[5].choice == "CDELT1")
    #expect(!fits.requiresLocalArguments)

    let noise = try capture("photometry_noise_budget", [
      "--source", "87654321", "--n-frames", "2", "--read-noise", "inf", "--units", "adu",
      "--private-column", "--sky-per-pixel=98765", "--n-pixels", "40",
    ], secrets: ["87654321"])
    #expect(noise.arguments.map(\.kind) == [.withheld, .integer, .withheld, .choice, .withheld])
    #expect(noise.arguments[1].integers == [2])
    let safeNoise = String(decoding: try JSONEncoder.scientificWorkbench.encode(noise), as: UTF8.self)
    #expect(!safeNoise.contains("87654321"))
    #expect(!safeNoise.contains("private-column"))
    #expect(!safeNoise.contains("98765"))

    let lithium = try capture("li6708_equivalent_width_workbench.measure", [
      "measure", first.path, "--continuum-window", "-1.25", "2.5", "--target-name", "Private target",
    ])
    #expect(lithium.arguments[1].numbers == [-1.25, 2.5])
    #expect(lithium.arguments[2].kind == .withheld)
  }

  @Test
  func runProvenanceMatchesBackendReceiptsToTheSelectedTool() async throws {
    let checkout = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent()
    let mother = checkout.appendingPathComponent("skills/scientific-data-analysis").path
    let entries = try CapabilityRegistryLoader().load(skillRoot: mother)
    let apt = try #require(entries.first { $0.id == "apt_workbench" })
    let fixture = try makeScenarioFixture(name: "backend-run-evidence", files: [:])
    defer { try? FileManager.default.removeItem(at: fixture) }

    for (reportedTool, backend) in [("apt_workbench.run-batch", RunBackendEvidence.Backend.apt),
                                    ("stilts_workbench.convert", nil)] {
      let run = fixture.appendingPathComponent(reportedTool)
      try FileManager.default.createDirectory(at: run.appendingPathComponent("reports"), withIntermediateDirectories: true)
      let summary = run.appendingPathComponent("reports/selected-summary.json")
      try """
        {"tool":"apt_workbench.run-batch","app_status":"PASS","results":{"dry_run":false,"returncode":42}}
        """.write(to: run.appendingPathComponent("summary.json"), atomically: true, encoding: .utf8)
      let payload = """
        {"tool":"\(reportedTool)","contract_version":"1.8","app_status":"FAIL","results":{
          "dry_run":false,"returncode":7,"command":["/Users/private-person/native-backend"]
        }}
        """
      try payload.write(to: summary, atomically: true, encoding: .utf8)
      let request = RunRequest(capabilityID: apt.id, inputPaths: [], outputDirectory: run.path, rawArguments: "")
      let command = ProcessCommand(
        executable: "/private/python", arguments: ["/private/wrapper.py", "run-tool", apt.scriptStem,
                                                     "run-batch", "--summary-json", summary.path],
        workingDirectory: "/private"
      )
      let start = await RunProvenanceService().captureStart(
        request: request, capability: apt, skillRoot: mother, outputRootConfirmationUsed: false,
        secrets: [], command: command, appliedApproval: .capabilityAccess, declaredPlanSource: .openAI
      )
      let job = JobRecord(capability: apt, runDirectory: run.path)
      let result = ProcessResult(exitCode: 2, stdout: "", stderr: "", startedAt: Date(), finishedAt: Date())
      let completed = await JobRunBundleService().finalize(
        job, completion: .finished(result, cancellationRequested: false), secrets: [], provenance: start
      )
      let artifact = try #require(completed.artifacts.first { $0.relativePath == JobRunProvenance.filename })
      let data = try Data(contentsOf: artifact.url)
      let record = try JSONDecoder.scientificWorkbench.decode(JobRunProvenance.self, from: data)
      #expect(record.reportedBackend?.backend == backend)
      #expect(record.reportedBackend?.reportedExitCodes == (backend == nil ? nil : [7]))
      #expect(record.limits.contains(.backendNotReported) == (backend == nil))
      #expect(record.limits.contains(.backendVersionNotRecorded) == (backend != nil))
      #expect(record.reportedToolContractVersion == (backend == nil ? nil : "1.8"))
      #expect(record.tool.registryDeclaredRelease == "v2.8")
      #expect(!record.limits.contains(.skillCodeIdentityIncomplete))
      #expect(record.declaredPlanSource == .openAI)
      #expect(record.limits.contains(.planningModelNotRecorded))
      #expect(record.approvals == [.capabilityAccess])
      #expect(!String(decoding: data, as: UTF8.self).contains("private-person"))
    }
  }

  @Test
  func toolEnvelopeSeparatesBackendUseFromPreflightAndDryRun() {
    func backend(_ tool: String, _ details: String, qa: String = "{}") -> RunBackendEvidence? {
      ToolEnvelopeParser().parse(
        #"{"tool":"\#(tool)","app_status":"PASS","results":\#(details),"qa":\#(qa)}"#
      )?.reportedBackend
    }
    #expect(backend("stilts_workbench.preflight", #"{"dry_run":false,"returncode":0}"#) == nil)
    #expect(backend("stilts_workbench.convert", #"{"dry_run":true,"returncode":0}"#) == nil)
    #expect(backend("stilts_workbench.convert", #"{"dry_run":false,"returncode":true}"#) == nil)
    #expect(backend("stilts_workbench.convert", #"{"dry_run":false,"returncode":0}"#)?.backend == .stilts)
    #expect(backend("latex_workbench.compile", #"{"engine":"pdflatex","attempted":true,"pass_count":1}"#)?.backend == .pdflatex)
    #expect(backend("latex_workbench.compile", #"{"engine":"pdflatex","attempted":false,"pass_count":0}"#) == nil)
    #expect(backend("keynote_export", #"{"capabilities":{"keynote_app":true}}"#) == nil)
    #expect(backend("keynote_export", "{}", qa: #"{"metrics":{"used_gui_path":true}}"#)?.backend == .keynote)
    #expect(backend("quicklook_bridge", #"{"method":"pdf_first_page","used_fallback":true}"#)?.backend == .pdfFirstPage)
    #expect(backend("iwork_workbench", #"{"native_preview":"/private/preview.png","native_preview_method":"qlmanage"}"#)?.backend == .quickLook)
    #expect(backend("fxcor_iraf_workbench.run-auto", #"{"case_runs":[{"outcome":{"returncode":1}}]}"#)?.backend == .iraf)
    #expect(backend("presentation_workbench.inspect",
                    #"{"inspection":{"preview_export":{"success":true,"backend_used":"soffice"}}}"#)?.backend == .libreOffice)
    #expect(backend("presentation_workbench.inspect",
                    #"{"inspection":{"preview_export":{"success":false,"backend_used":"soffice"}}}"#) == nil)
    #expect(backend("presentation_workbench.existing-deck-style-audit",
                    #"{"reference_preview":{"success":true,"export_result":{"success":true,"backend_used":"keynote"}}}"#)?.backend == .keynote)
  }
}

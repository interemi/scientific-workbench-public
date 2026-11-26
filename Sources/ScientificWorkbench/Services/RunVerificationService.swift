import Foundation

struct RunVerificationReport: Sendable {
  struct Check: Identifiable, Sendable {
    enum Status: String, Sendable {
      case matches = "Matches"
      case changed = "Changed"
      case unavailable = "Unavailable"
    }

    let subject: String
    let status: Status
    let detail: String
    var id: String { subject }
  }

  let jobID: UUID
  let checks: [Check]
  var matchesRecordedEvidence: Bool { checks.allSatisfy { $0.status == .matches } }
}

struct RunVerificationService {
  struct Settings: Equatable, Sendable {
    let skillRoot: String
    let pythonExecutable: String
    let outputRoot: String
    let secrets: [String]
  }

  private typealias Check = RunVerificationReport.Check
  private let runner = ProcessRunner()

  func verify(job: JobRecord, settings: Settings) async -> RunVerificationReport {
    guard let record = RunOutputEvidence.provenance(for: job) else {
      return .init(jobID: job.id, checks: [
        .init(subject: "Original run", status: .unavailable, detail: "No readable provenance record matches this job and tool.")
      ])
    }
    let succeeded = job.status == .succeeded && record.status == .succeeded
    var checks = [
      Check(subject: "Original run", status: succeeded ? .matches : .changed,
            detail: succeeded ? "The original job reports successful completion." : "A successful original run is required."),
      verifyApp(record),
    ]
    let inputs = job.requestInputPaths.map(FilesystemPath.canonicalURL)
    let currentInputs = RunProvenanceService.fingerprints(inputs.map(Optional.some))
    if record.inputs.contains(where: { $0.contentUnchanged == false }) {
      checks.append(.init(subject: "Inputs", status: .changed, detail: "The original execution changed at least one input."))
    } else {
      let inputCheck = compareFiles(subject: "Inputs", recorded: record.inputs.map(\.before), current: currentInputs)
      if inputCheck.status == .matches && record.inputs.contains(where: { $0.contentUnchanged == nil }) {
        checks.append(.init(subject: "Inputs", status: .unavailable, detail: "The original run did not confirm that all inputs stayed unchanged."))
      } else {
        checks.append(inputCheck)
      }
    }
    let directories = zip(inputs, record.inputs).compactMap { url, input in
      input.before.state == .directory ? url : nil
    }
    let files = RunProvenanceService.retainedOutputFiles(for: job, excluding: Set(inputs), attachedDirectories: directories)
    if record.outputs.isEmpty && files.isEmpty {
      checks.append(.init(subject: "Retained outputs", status: .unavailable, detail: "No output fingerprints were retained."))
    } else {
      checks.append(compareFiles(subject: "Retained outputs", recorded: record.outputs.map(\.fingerprint),
                                 current: RunProvenanceService.fingerprints(files.map(Optional.some))))
    }

    let capability = (try? CapabilityRegistryLoader().load(skillRoot: settings.skillRoot))?
      .first { $0.id == job.capabilityID }
    checks.append(verifySkill(record, capability: capability, settings: settings))
    checks.append(verifyPermissions(job: job, record: record, capability: capability, settings: settings))
    let command = capability.flatMap { capability in
      try? CapabilityCommandBuilder(pythonExecutable: settings.pythonExecutable).build(
        capability: capability, request: RunRequest(capabilityID: capability.id, inputPaths: job.requestInputPaths,
          outputDirectory: job.runDirectory, rawArguments: job.requestRawArguments),
        skillRoot: settings.skillRoot
      )
    }
    let currentCommand = command.flatMap { command in
      capability.flatMap {
        RunCommandEvidence.capture(command: command, capability: $0, inputURLs: inputs,
                                   runRoot: FilesystemPath.canonicalURL(job.runDirectory), secrets: settings.secrets)?.evidence
      }
    }
    checks.append(verifyCommand(record.command, currentCommand))
    let runtime: RunRuntimeEvidence?
    if record.runtime != nil, let command { runtime = await observeRuntime(for: command) } else { runtime = nil }
    checks.append(compareRuntime(record.runtime, runtime))
    return .init(jobID: job.id, checks: checks)
  }

  private func compareFiles(
    subject: String, recorded: [RunFileFingerprint], current: [RunFileFingerprint]
  ) -> Check {
    guard recorded.count == current.count else {
      return .init(subject: subject, status: .changed,
                   detail: "Recorded \(recorded.count) locations. Found \(current.count) current locations.")
    }
    var changed: [Int] = []
    var unavailable: [Int] = []
    for (index, pair) in zip(recorded, current).enumerated() {
      let (before, now) = pair
      if now.state == .missing && before.state == .recorded {
        changed.append(index + 1)
      } else if before.state != .recorded || now.state != .recorded || before.sha256 == nil || now.sha256 == nil {
        unavailable.append(index + 1)
      } else if before != now {
        changed.append(index + 1)
      }
    }
    if !changed.isEmpty || !unavailable.isEmpty {
      let differences = changed.isEmpty ? "" : "Changed or missing locations \(fileOrdinals(changed))."
      let gaps = unavailable.isEmpty ? "" : " No complete hashes at locations \(fileOrdinals(unavailable))."
      return .init(subject: subject, status: changed.isEmpty ? .unavailable : .changed,
                   detail: (differences + gaps).trimmingCharacters(in: .whitespaces))
    }
    return .init(subject: subject, status: .matches, detail: "\(recorded.count) recorded file fingerprints match.")
  }

  private func fileOrdinals(_ values: [Int]) -> String {
    values.prefix(12).map(String.init).joined(separator: ", ") + (values.count > 12 ? ", …" : "")
  }

  private func verifyApp(_ record: JobRunProvenance) -> Check {
    let host = ProcessInfo.processInfo.operatingSystemVersion
    let current = "\(host.majorVersion).\(host.minorVersion).\(host.patchVersion)"
    let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
    let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
    if let recordedOS = record.hostMacOSVersion, current != recordedOS {
      return .init(subject: "App and macOS", status: .changed, detail: "The macOS version changed.")
    }
    guard let recordedVersion = record.appVersion, let recordedBuild = record.appBuild,
          let version, let build, record.hostMacOSVersion != nil else {
      return .init(subject: "App and macOS", status: .unavailable, detail: "Some app version, build, or macOS metadata is missing.")
    }
    let matches = version == recordedVersion && build == recordedBuild
    return .init(subject: "App and macOS", status: matches ? .matches : .changed,
                 detail: matches ? "The recorded app version, build, and macOS match." : "The app version or build changed.")
  }

  private func verifySkill(_ record: JobRunProvenance, capability: CapabilityEntry?, settings: Settings) -> Check {
    guard let capability else {
      return .init(subject: "Skill", status: .unavailable, detail: "The tool could not be resolved from the current registry.")
    }
    let current = RunProvenanceService.toolIdentity(capability: capability, skillRoot: settings.skillRoot, secrets: settings.secrets)
    guard record.tool.registrySHA256 != nil, record.tool.entryPointSHA256 != nil else {
      return .init(subject: "Skill", status: .unavailable, detail: "The original registry or entry point did not have a recorded hash.")
    }
    let matches = record.tool == current
    return .init(subject: "Skill", status: matches ? .matches : .changed,
                 detail: matches ? "The available registry and script hashes match."
                                 : "The registry, entry point, implementation evidence, or contract changed.")
  }

  private func verifyPermissions(
    job: JobRecord, record: JobRunProvenance, capability: CapabilityEntry?, settings: Settings
  ) -> Check {
    guard let capability, let approvals = record.approvals else {
      return .init(subject: "Permissions", status: .unavailable, detail: "The capability or original approvals could not be established.")
    }
    guard case .safe = FilesystemSafetyPolicy().assessOutputRoot(settings.outputRoot, inputPaths: job.requestInputPaths) else {
      return .init(subject: "Permissions", status: .changed, detail: "The current output folder requires a separate filesystem review.")
    }
    if !approvals.isEmpty || record.outputRootConfirmationUsed || capability.requiresPlannerConfirmation
      || capability.isMaintainerOnly || record.limits.contains(.furtherConsentEvidenceRequired) {
      return .init(subject: "Permissions", status: .unavailable, detail: "The run or current capability requires a separate approval review.")
    }
    if record.reportedBackend != nil || record.limits.contains(.backendNotReported) {
      return .init(subject: "Permissions", status: .unavailable, detail: "The external backend and its settings require separate verification.")
    }
    return .init(subject: "Permissions", status: .matches, detail: "The recorded run and current settings require no special approval.")
  }

  private func verifyCommand(_ recorded: RunCommandEvidence?, _ current: RunCommandEvidence?) -> Check {
    guard let recorded, let current, !recorded.requiresLocalArguments, !current.requiresLocalArguments else {
      return .init(subject: "Command", status: .unavailable, detail: "Some original or current arguments lack complete recorded evidence.")
    }
    let matches = recorded == current
    return .init(subject: "Command", status: matches ? .matches : .changed,
                 detail: matches ? "The recorded typed arguments match." : "The operation or its recorded arguments changed.")
  }

  private func observeRuntime(for command: ProcessCommand) async -> RunRuntimeEvidence? {
    guard let wrapper = command.arguments.first, !Task.isCancelled else { return nil }
    let script = """
      import json, platform, sys
      from importlib.metadata import PackageNotFoundError, version
      packages = {}
      for name in sys.argv[1:]:
          try:
              packages[name] = version(name)
          except PackageNotFoundError:
              pass
      print(json.dumps({"pythonImplementation": sys.implementation.name, "pythonVersion": platform.python_version(),
                        "architecture": platform.machine(), "profilePackages": packages}))
      """
    var overrides = command.environmentOverrides
    overrides["PYTHONDONTWRITEBYTECODE"] = "1"
    let probe = ProcessCommand(
      executable: command.executable,
      arguments: ["-B", wrapper, "python", "-B", "-c", script] + RunRuntimeEvidence.profilePackageNames,
      workingDirectory: command.workingDirectory, timeoutSeconds: 15,
      environmentPolicy: command.environmentPolicy, environmentOverrides: overrides, redirectStandardInputToNull: true
    )
    guard let result = try? await runner.run(probe), result.exitCode == 0, !result.stdoutWasTruncated else { return nil }
    return (try? JSONDecoder().decode(RunRuntimeEvidence.self, from: Data(result.stdout.utf8)))?.validated()
  }

  private func compareRuntime(_ recorded: RunRuntimeEvidence?, _ current: RunRuntimeEvidence?) -> Check {
    guard let recorded, let current else {
      return .init(subject: "Python runtime", status: .unavailable, detail: "The original or currently selected Python inventory is unavailable.")
    }
    if recorded == current {
      return .init(subject: "Python runtime", status: .matches, detail: "The interpreter, architecture, and recorded direct packages match.")
    }
    let changed = Set(recorded.profilePackages.keys).union(current.profilePackages.keys)
      .filter { recorded.profilePackages[$0] != current.profilePackages[$0] }.sorted()
    let packages = changed.isEmpty ? "" : " Packages with differences: \(changed.joined(separator: ", "))."
    let interpreter = recorded.pythonImplementation == current.pythonImplementation
      && recorded.pythonVersion == current.pythonVersion && recorded.architecture == current.architecture
    return .init(subject: "Python runtime", status: .changed,
                 detail: (interpreter ? "The direct package inventory changed." : "The interpreter or architecture changed.") + packages)
  }
}

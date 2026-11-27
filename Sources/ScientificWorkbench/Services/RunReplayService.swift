import Darwin
import Foundation

struct RunReplayService {
  private static let stagingDirectory = ".swb-replay-inputs"

  enum Unavailable: LocalizedError {
    case reason(String)

    var errorDescription: String? {
      switch self {
      case .reason(let message): message
      }
    }
  }

  struct Output: Sendable {
    let relativePath: String
    let fingerprint: RunFileFingerprint
  }

  struct Plan: Sendable {
    let original: JobRecord
    let originalOutputs: [Output]
    let capability: CapabilityEntry
    let settings: RunVerificationService.Settings
    let directory: URL
    let device: dev_t
    let inode: ino_t
    let inputPaths: [String]
    let inputFingerprints: [RunFileFingerprint]
    let rawArguments: String
    let commandDigest: String
    let tool: JobRunProvenance.Tool
    let approvals: [RunApproval]
    let pythonInventorySHA256: String

    func ownsDirectory() -> Bool {
      guard FilesystemPath.canonicalURL(directory.path).path == directory.path else { return false }
      var info = stat()
      return lstat(directory.path, &info) == 0 && (info.st_mode & S_IFMT) == S_IFDIR
        && info.st_dev == device && info.st_ino == inode && info.st_uid == getuid()
        && info.st_mode & 0o777 == 0o700
    }

    func checkBeforeLaunch(_ command: ProcessCommand) async throws {
      guard ownsDirectory(),
            let current = try CapabilityRegistryLoader().load(skillRoot: settings.skillRoot).first(where: { $0.id == capability.id }),
            RunProvenanceService.toolIdentity(capability: current, skillRoot: settings.skillRoot, secrets: settings.secrets) == tool,
            RunExecutionEvidence.commandDigest(command, secrets: settings.secrets) == commandDigest else {
        throw Unavailable.reason("The replay folder, skill code, or execution settings changed.")
      }
      let runtime = await RunVerificationService().observeRuntime(for: command)
      guard runtime?.inventorySHA256 == pythonInventorySHA256 else {
        throw Unavailable.reason("The Python inventory changed before execution.")
      }
      let copied = inputPaths.map { URL(fileURLWithPath: $0) }
      guard ownsDirectory(), copied.allSatisfy({ FilesystemPath.canonicalURL($0.path).path == $0.path }),
            RunProvenanceService.fingerprints(copied.map(Optional.some)) == inputFingerprints else {
        throw Unavailable.reason("An input copy no longer matches the original run.")
      }
      let artifacts = directory.appendingPathComponent("artifacts", isDirectory: true)
      guard Set(try FileManager.default.contentsOfDirectory(atPath: directory.path))
              == [RunReplayService.stagingDirectory, "artifacts"],
            FilesystemPath.canonicalURL(artifacts.path).path == artifacts.path,
            try FileManager.default.contentsOfDirectory(atPath: artifacts.path).isEmpty else {
        throw Unavailable.reason("The replay folder contains unexpected output files.")
      }
      try Task.checkCancellation()
    }
  }

  // These local commands have a reviewed file-only invocation. Commands with
  // subprocess, network, directory, automation or executable-code inputs need
  // their own replay contract.
  private static let positionalInputCount = [
    "profile_table": 1,
    "inspect_fits": 1,
    "photometric_solution": 1,
    "li6708_equivalent_width_workbench.measure": 1,
    "catalog_workbench.crossmatch-sky": 2,
  ]

  static func supports(_ capabilityID: String) -> Bool {
    positionalInputCount[capabilityID] != nil
  }

  func prepare(
    job: JobRecord, settings: RunVerificationService.Settings, destination: String
  ) async throws -> Plan {
    let report = await RunVerificationService().verify(job: job, settings: settings)
    if let reason = report.replayBlockReason { throw Unavailable.reason(reason) }
    try Task.checkCancellation()
    guard let record = RunOutputEvidence.provenance(for: job),
          let receipt = RunExecutionEvidence.read(for: job), let approvals = record.approvals,
          let capability = try CapabilityRegistryLoader().load(skillRoot: settings.skillRoot)
            .first(where: { $0.id == job.capabilityID }) else {
      throw Unavailable.reason("The original execution record or current capability is unavailable.")
    }
    let builder = CapabilityCommandBuilder(pythonExecutable: settings.pythonExecutable, timeoutSeconds: settings.timeoutSeconds)
    let old = FilesystemPath.canonicalURL(job.runDirectory)
    let root = FilesystemPath.canonicalURL(destination)
    let allowedRoot = LegacyWorkspacePolicy().runRoot(for: capability.id, preferredOutputRoot: settings.outputRoot)
    try FilesystemSafetyPolicy().validateRunDirectory(root.path, inputPaths: job.requestInputPaths, allowedRoots: [allowedRoot])
    guard Self.relativePath(root, under: old) == nil, Self.relativePath(old, under: root) == nil,
          (root.deletingLastPathComponent().path == FilesystemPath.canonicalURL(allowedRoot).path) else {
      throw Unavailable.reason("The replay folder must be a new sibling under the configured runs root.")
    }
    let inputs = job.requestInputPaths.map(FilesystemPath.canonicalURL)
    let fileFingerprints = record.inputs.map(\.before)
    guard Set(inputs.map(\.path)).count == inputs.count, record.inputs.count == inputs.count,
          record.inputs.allSatisfy({ $0.contentUnchanged == true && $0.before.sha256 != nil }) else {
      throw Unavailable.reason("Replay needs distinct attached files with complete original fingerprints.")
    }
    let outputs = RunProvenanceService.retainedOutputFiles(for: job, excluding: Set(inputs), attachedDirectories: [])
    let names = outputs.compactMap { Self.relativePath($0, under: old) }
    guard names.count == record.outputs.count, !names.isEmpty,
          RunProvenanceService.fingerprints(outputs.map(Optional.some)) == record.outputs.map(\.fingerprint) else {
      throw Unavailable.reason("The original outputs changed after review.")
    }
    let originalOutputs = zip(names, record.outputs).map { Output(relativePath: $0, fingerprint: $1.fingerprint) }
    let originalCommand = try builder.build(
      capability: capability, request: .init(capabilityID: capability.id, inputPaths: job.requestInputPaths,
        outputDirectory: job.runDirectory, rawArguments: job.requestRawArguments), skillRoot: settings.skillRoot
    )
    guard RunExecutionEvidence.commandDigest(originalCommand, secrets: settings.secrets) == receipt.commandSHA256 else {
      throw Unavailable.reason("The original command changed after review.")
    }
    let copies = inputs.enumerated().map { index, source in
      root.appendingPathComponent("\(Self.stagingDirectory)/\(index + 1)/\(source.lastPathComponent)")
    }
    let arguments = try Self.remap(
      originalCommand, capability: capability, old: old, root: root,
      inputLocations: Dictionary(uniqueKeysWithValues: zip(inputs.map(\.path), copies.map(\.path)))
    )
    let raw = arguments.map(ShellWords.quote).joined(separator: " ")
    let inputPaths = copies.map(\.path)
    let command = try builder.build(
      capability: capability, request: .init(capabilityID: capability.id, inputPaths: inputPaths,
        outputDirectory: root.path, rawArguments: raw), skillRoot: settings.skillRoot
    )
    guard let digest = RunExecutionEvidence.commandDigest(command, secrets: settings.secrets) else {
      throw Unavailable.reason("The replay command could not be verified.")
    }

    try Task.checkCancellation()
    try FileManager.default.createDirectory(at: root.deletingLastPathComponent(), withIntermediateDirectories: true)
    guard mkdir(root.path, 0o700) == 0 else {
      throw Unavailable.reason("The replay folder already exists or could not be created exclusively.")
    }
    var info = stat()
    guard lstat(root.path, &info) == 0 else { throw Unavailable.reason("Could not verify the new replay folder.") }
    for (index, source) in inputs.enumerated() {
      try Task.checkCancellation()
      let expected = fileFingerprints[index]
      guard let size = expected.byteCount, size >= 0, size <= RunFileFingerprint.defaultReadBudget else {
        throw Unavailable.reason("An input exceeds the replay fingerprint budget.")
      }
      let captured = RunFileFingerprint.readSample(source, maximumBytes: size, range: 0..<size)
      guard captured.fingerprint == expected else {
        throw Unavailable.reason("An original input changed before it could be copied.")
      }
      let copy = copies[index]
      try FileManager.default.createDirectory(at: copy.deletingLastPathComponent(), withIntermediateDirectories: true)
      try captured.bytes.write(to: copy, options: .withoutOverwriting)
    }
    return Plan(original: job, originalOutputs: originalOutputs, capability: capability, settings: settings,
                directory: root, device: info.st_dev, inode: info.st_ino, inputPaths: inputPaths,
                inputFingerprints: fileFingerprints, rawArguments: raw, commandDigest: digest, tool: record.tool,
                approvals: approvals,
                pythonInventorySHA256: receipt.pythonInventorySHA256)
  }

  static func remap(
    _ command: ProcessCommand, capability: CapabilityEntry, old: URL, root: URL, inputLocations: [String: String]
  ) throws -> [String] {
    let selector = ["run-tool", capability.scriptStem] + [capability.inferredSubcommand].compactMap { $0 }
    let arguments = Array(command.arguments.dropFirst(1 + selector.count))
    guard let count = positionalInputCount[capability.id],
          Array(command.arguments.dropFirst().prefix(selector.count)) == selector, arguments.count >= count,
          arguments.prefix(count).allSatisfy({
            $0.hasPrefix("/") && inputLocations[FilesystemPath.canonicalURL($0).path] != nil
          }) else {
      throw Unavailable.reason("The command does not begin with the expected attached file arguments.")
    }
    func mapPath(_ value: String) throws -> String {
      guard value.hasPrefix("/") || value.hasPrefix("~/") else { return value }
      let path = FilesystemPath.canonicalURL(value)
      if let copy = inputLocations[path.path] { return copy }
      if let relative = relativePath(path, under: old), !relative.isEmpty,
         let first = relative.split(separator: "/").first, first != "inputs", !first.hasPrefix("."),
         !["command.txt", "stdout.txt", "stderr.txt", JobRunProvenance.filename, RunReplayComparison.filename].contains(String(first)) {
        return root.appendingPathComponent(relative).path
      }
      throw Unavailable.reason("An argument points outside the attached files and permitted run destinations.")
    }
    return try arguments.map { token in
      if token.hasPrefix("--"), let equal = token.firstIndex(of: "=") {
        let valueStart = token.index(after: equal)
        return String(token[..<valueStart]) + (try mapPath(String(token[valueStart...])))
      }
      return try mapPath(token)
    }
  }

  static func relativePath(_ url: URL, under root: URL) -> String? {
    if url.path == root.path { return "" }
    let prefix = root.path + "/"
    return url.path.hasPrefix(prefix) ? String(url.path.dropFirst(prefix.count)) : nil
  }

}

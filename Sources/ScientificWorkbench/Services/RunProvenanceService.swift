import Foundation

enum RunApproval: String, Codable, Sendable {
  case outputRoot = "output_root"
  case capabilityAccess = "capability_access"
  case reviewedDOCXReplacement = "reviewed_docx_replacement"
  case confirmedKeynoteExport = "confirmed_keynote_export"
  case restrictedLocalAutomation = "restricted_local_automation"
}

struct JobRunProvenance: Codable, Sendable {
  static let filename = "run-provenance.json"

  struct Tool: Codable, Sendable {
    let capabilityID: String?
    let skillRole: SkillRootRole?
    let contractRevision: Int?
    let registrySHA256: String?
    let entryPointSHA256: String?
    let implementationSHA256: String?
  }

  struct Input: Codable, Sendable {
    let id: String
    let before: RunFileFingerprint
    let after: RunFileFingerprint
    let contentUnchanged: Bool?
  }

  struct Output: Codable, Sendable {
    let id: String
    let fingerprint: RunFileFingerprint
    let commandReference: String?
  }

  enum Limit: String, Codable, Sendable {
    case attachedInputScope = "attached_input_scope"
    case directoryContentsNotCaptured = "directory_contents_not_captured"
    case incompleteFingerprints = "incomplete_fingerprints"
    case inputContentChanged = "input_content_changed"
    case localArgumentsRequired = "local_arguments_required"
    case runtimeAndDependencyVersionsNotCaptured = "runtime_and_dependency_versions_not_captured"
    case backendAndModelNotCaptured = "backend_and_model_not_captured"
    case backendNotReported = "backend_not_reported"
    case planningModelNotRecorded = "planning_model_not_recorded"
    case furtherConsentEvidenceRequired = "further_consent_evidence_required"
  }

  let schemaVersion: Int
  let jobID: UUID
  let appVersion: String?
  let appBuild: String?
  let tool: Tool
  let status: JobStatus
  let exitCode: Int32?
  let startedAt: Date?
  let finishedAt: Date?
  let outputRootConfirmationUsed: Bool
  let runtime: RunRuntimeEvidence?
  let command: RunCommandEvidence?
  let reportedBackend: RunBackendEvidence?
  let approvals: [RunApproval]?
  let declaredPlanSource: AgentPlanSource?
  let inputs: [Input]
  let outputs: [Output]
  let limits: [Limit]
}

struct RunProvenanceService {
  struct Start: Sendable {
    fileprivate let inputPaths: [String]
    fileprivate let inputURLs: [URL]
    fileprivate let fingerprints: [RunFileFingerprint]
    fileprivate let runRoot: URL
    fileprivate let tool: JobRunProvenance.Tool
    fileprivate let appVersion: String?
    fileprivate let appBuild: String?
    fileprivate let outputRootConfirmationUsed: Bool
    fileprivate let command: RunCommandEvidence?
    fileprivate let runLocations: [URL: String]
    fileprivate let approvals: [RunApproval]
    fileprivate let missingCapabilityApproval: Bool
    fileprivate let declaredPlanSource: AgentPlanSource?
    let runtimeChannel: RunRuntimeEvidence.Channel
  }

  func captureStart(
    request: RunRequest, capability: CapabilityEntry, skillRoot: String,
    outputRootConfirmationUsed: Bool, secrets: [String], command: ProcessCommand? = nil,
    appliedApproval: RunApproval? = nil, declaredPlanSource: AgentPlanSource? = nil
  ) async -> Start {
    await Task.detached(priority: .utility) {
      let owner = FilesystemPath.canonicalURL(capability.resolvedSkillRoot(fallback: skillRoot))
      let entryPoint = owner.appendingPathComponent(capability.script)
      let implementation = owner.appendingPathComponent("fixtures", isDirectory: true)
        .appendingPathComponent(entryPoint.lastPathComponent)
      let registry = capability.registryFingerprint
      let tool = JobRunProvenance.Tool(
        capabilityID: Self.safeIdentifier(capability.id, secrets: secrets),
        skillRole: capability.owningSkillRole.flatMap(SkillRootRole.init(rawValue:)),
        contractRevision: capability.ioContract?.revision,
        registrySHA256: registry.flatMap { value in
          value.utf8.count == 64 && value.utf8.allSatisfy(Self.isHexDigit) ? value.lowercased() : nil
        },
        entryPointSHA256: Self.digest(entryPoint, inside: owner),
        implementationSHA256: Self.digest(implementation, inside: owner)
      )
      let inputURLs = request.inputPaths.map(FilesystemPath.canonicalURL)
      let runRoot = FilesystemPath.canonicalURL(request.outputDirectory)
      let capturedCommand = command.flatMap {
        RunCommandEvidence.capture(
          command: $0, capability: capability, inputURLs: inputURLs, runRoot: runRoot, secrets: secrets
        )
      }
      let isPreflight = capturedCommand?.evidence.operation == "preflight"
        || capturedCommand?.evidence.arguments.contains { $0.option == "--preflight-only" && $0.kind == .flag } == true
      let approvals: [RunApproval?] = [outputRootConfirmationUsed ? .outputRoot : nil, appliedApproval]
      return Start(
        inputPaths: request.inputPaths,
        inputURLs: inputURLs,
        fingerprints: Self.fingerprints(inputURLs),
        runRoot: runRoot,
        tool: tool,
        appVersion: Self.appVersion("CFBundleShortVersionString"),
        appBuild: Self.appVersion("CFBundleVersion"),
        outputRootConfirmationUsed: outputRootConfirmationUsed,
        command: capturedCommand?.evidence,
        runLocations: capturedCommand?.runLocations ?? [:],
        approvals: approvals.compactMap { $0 },
        missingCapabilityApproval: capability.requiresPlannerConfirmation && !isPreflight && appliedApproval == nil,
        declaredPlanSource: declaredPlanSource,
        runtimeChannel: RunRuntimeEvidence.Channel(runRoot: runRoot, tool: capability.scriptStem)
      )
    }.value
  }

  func write(start: Start, job: JobRecord, envelope: ToolEnvelope? = nil) throws -> Artifact {
    let root = FilesystemPath.canonicalURL(job.runDirectory)
    guard root == start.runRoot else { throw CocoaError(.fileWriteInvalidFileName) }
    let runtime = start.runtimeChannel.consume()
    let updatedURLs = start.inputPaths.map(FilesystemPath.canonicalURL)
    let after = Self.fingerprints(zip(start.inputURLs, updatedURLs).map { $0 == $1 ? $0 : nil })
    let inputs = zip(start.fingerprints, after).enumerated().map { index, pair in
      let (before, after) = pair
      let unchanged = before.sha256.flatMap { digest in after.sha256.map { $0 == digest } }
      return JobRunProvenance.Input(
        id: "input-\(index + 1)", before: before, after: after, contentUnchanged: unchanged
      )
    }

    let stagedInputs = root.appendingPathComponent("inputs", isDirectory: true)
    let inputURLs = Set(start.inputURLs + updatedURLs)
    let inputDirectories = zip(start.inputURLs, start.fingerprints).compactMap { url, digest in
      digest.state == .directory ? url : nil
    }
    let outputURLs = Set(job.artifacts.map { FilesystemPath.canonicalURL($0.path) }).filter { url in
      Self.isInside(url, root: root) && !Self.isInside(url, root: stagedInputs)
        && url != root.appendingPathComponent(JobRunProvenance.filename)
        && !inputURLs.contains(url) && !inputDirectories.contains { Self.isInside(url, root: $0) }
    }
    let sortedOutputs = outputURLs.sorted { $0.path < $1.path }
    let outputs = zip(sortedOutputs, Self.fingerprints(sortedOutputs)).enumerated().map { index, item in
      let (url, digest) = item
      return JobRunProvenance.Output(
        id: "output-\(index + 1)", fingerprint: digest, commandReference: start.runLocations[url]
      )
    }
    let fingerprints = inputs.flatMap { [$0.before, $0.after] } + outputs.map(\.fingerprint)
    let reportedTool = start.tool.capabilityID.map { id in
      guard let operation = start.command?.operation, !id.hasSuffix(".\(operation)") else { return id }
      return "\(id).\(operation)"
    }
    let checksOnly = start.command?.arguments.contains {
      $0.kind == .flag && ($0.option == "--preflight-only" || $0.option == "--dry-run")
    } == true
    let backend: RunBackendEvidence?
    if !checksOnly, let reportedTool, RunBackendEvidence.tracks(reportedTool) {
      let report = Self.commandSummary(start: start, root: root) ?? envelope
      backend = report?.tool == reportedTool ? report?.reportedBackend : nil
    } else {
      backend = nil
    }
    var limits: [JobRunProvenance.Limit] = [.attachedInputScope]
    if backend == nil, !checksOnly, let reportedTool, RunBackendEvidence.tracks(reportedTool) {
      limits.append(.backendNotReported)
    }
    if let source = start.declaredPlanSource, source != .local && source != .skillRouter {
      limits.append(.planningModelNotRecorded)
    }
    if start.missingCapabilityApproval { limits.append(.furtherConsentEvidenceRequired) }
    if start.command?.requiresLocalArguments != false { limits.append(.localArgumentsRequired) }
    if runtime == nil { limits.append(.runtimeAndDependencyVersionsNotCaptured) }
    if fingerprints.contains(where: { $0.state == .directory }) { limits.append(.directoryContentsNotCaptured) }
    if fingerprints.contains(where: { $0.state != .recorded }) { limits.append(.incompleteFingerprints) }
    if inputs.contains(where: { $0.contentUnchanged == false }) { limits.append(.inputContentChanged) }

    let provenance = JobRunProvenance(
      schemaVersion: 1, jobID: job.id, appVersion: start.appVersion, appBuild: start.appBuild,
      tool: start.tool, status: job.status, exitCode: job.exitCode, startedAt: job.startedAt,
      finishedAt: job.finishedAt, outputRootConfirmationUsed: start.outputRootConfirmationUsed, runtime: runtime,
      command: start.command, reportedBackend: backend, approvals: start.approvals,
      declaredPlanSource: start.declaredPlanSource, inputs: inputs, outputs: outputs, limits: limits
    )
    let data = try JSONEncoder.scientificWorkbench.encode(provenance)
    let destination = root.appendingPathComponent(JobRunProvenance.filename)
    let staging = root.appendingPathComponent(".run-provenance-\(UUID().uuidString).tmp")
    try data.write(to: staging, options: .withoutOverwriting)
    defer { try? FileManager.default.removeItem(at: staging) }
    try FileManager.default.moveItem(at: staging, to: destination)
    return Artifact(path: destination.path, relativePath: JobRunProvenance.filename,
                    byteCount: Int64(data.count), artifactType: "metadata_json")
  }

  private static func fingerprints(_ urls: [URL?]) -> [RunFileFingerprint] {
    // Each pass has its own budget so a large input cannot hide the outputs.
    var remaining = RunFileFingerprint.defaultReadBudget
    return urls.map { url in
      guard let url else { return RunFileFingerprint(state: .changed, byteCount: nil, sha256: nil) }
      let digest = RunFileFingerprint.read(url, maximumBytes: remaining)
      if let size = digest.byteCount, size >= 0, size <= remaining { remaining -= size }
      return digest
    }
  }

  private static func commandSummary(start: Start, root: URL) -> ToolEnvelope? {
    let arguments = start.command?.arguments ?? []
    let argument = arguments.last { $0.option == "--summary-json" }
      ?? arguments.last { $0.option == "--output-json" }
    guard let reference = argument?.reference,
          let url = start.runLocations.first(where: { $0.value == reference })?.key,
          isInside(url, root: root), FilesystemPath.canonicalURL(url.path) == url,
          let capture = BoundedProcessOutput.read(at: url, maximumBytes: 512_000),
          !capture.wasTruncated else { return nil }
    return ToolEnvelopeParser().parse(capture.text)
  }

  private static func digest(_ url: URL, inside root: URL) -> String? {
    let resolved = FilesystemPath.canonicalURL(url.path)
    guard isInside(resolved, root: root) else { return nil }
    return RunFileFingerprint.read(resolved, maximumBytes: RunFileFingerprint.defaultReadBudget).sha256
  }

  private static func isInside(_ url: URL, root: URL) -> Bool {
    url.path.hasPrefix(root.path.hasSuffix("/") ? root.path : root.path + "/")
  }

  private static func safeIdentifier(_ value: String, secrets: [String]) -> String? {
    guard value.range(of: #"^[a-z][a-z0-9_.-]{0,127}$"#, options: .regularExpression) != nil,
          SecretsRedactor.redact(value, secrets: secrets) == value else { return nil }
    return value
  }

  private static func appVersion(_ key: String) -> String? {
    guard let value = Bundle.main.object(forInfoDictionaryKey: key) as? String,
          value.range(of: #"^[0-9]+(?:\.[0-9]+){0,3}$"#, options: .regularExpression) != nil else { return nil }
    return value
  }

  private static func isHexDigit(_ byte: UInt8) -> Bool {
    (48...57).contains(byte) || (65...70).contains(byte) || (97...102).contains(byte)
  }
}

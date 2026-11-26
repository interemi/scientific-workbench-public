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

  struct Tool: Codable, Equatable, Sendable {
    let capabilityID: String?
    let skillRole: SkillRootRole?
    let registryDeclaredRelease: String?
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
    case fileContentsNotIncluded = "file_contents_not_included"
    case directoryContentsNotCaptured = "directory_contents_not_captured"
    case incompleteFingerprints = "incomplete_fingerprints"
    case inputContentChanged = "input_content_changed"
    case unsuccessfulRun = "unsuccessful_run"
    case commandNotRecorded = "command_not_recorded"
    case localArgumentsRequired = "local_arguments_required"
    case appIdentityNotRecorded = "app_identity_not_recorded"
    case skillReleaseNotRecorded = "skill_release_not_recorded"
    case skillCodeIdentityIncomplete = "skill_code_identity_incomplete"
    case runtimeAndDependencyVersionsNotCaptured = "runtime_and_dependency_versions_not_captured"
    case runtimeInventoryPartial = "runtime_inventory_partial"
    case backendAndModelNotCaptured = "backend_and_model_not_captured"
    case backendNotReported = "backend_not_reported"
    case backendVersionNotRecorded = "backend_version_not_recorded"
    case planningModelNotRecorded = "planning_model_not_recorded"
    case planningReportedModelNotRecorded = "planning_reported_model_not_recorded"
    case planningConsentNotRecorded = "planning_consent_not_recorded"
    case furtherConsentEvidenceRequired = "further_consent_evidence_required"

    var guidance: String {
      switch self {
      case .attachedInputScope:
        "Check whether the operation also read files outside the attached inputs."
      case .fileContentsNotIncluded:
        "Obtain the inputs separately. Match them by SHA-256 and use a new directory for the outputs."
      case .directoryContentsNotCaptured:
        "Obtain an independent inventory with hashes for the contents of attached directories."
      case .incompleteFingerprints:
        "Check the fingerprint states and verify the missing or unreadable files separately."
      case .inputContentChanged:
        "Recover inputs matching the before-run hashes before attempting reproduction."
      case .unsuccessfulRun:
        "Resolve the reported job outcome before treating its products as complete."
      case .commandNotRecorded:
        "Recover the original command from the local run and review it for sensitive values."
      case .localArgumentsRequired:
        "Supply withheld arguments locally. Use the argument order and references to locate them."
      case .appIdentityNotRecorded:
        "Identify the application version and build from the original installation or source revision."
      case .skillReleaseNotRecorded:
        "Identify the original skill release. Compare the available registry and script hashes."
      case .skillCodeIdentityIncomplete:
        "Obtain the original skill snapshot and compare the registry and entry point."
      case .runtimeAndDependencyVersionsNotCaptured:
        "Identify the interpreter and installed dependency versions from the original environment."
      case .runtimeInventoryPartial:
        "Check the transitive dependencies, subprocess environments and skill snapshot separately."
      case .backendAndModelNotCaptured:
        "Identify the external backend and planning model using the original run evidence."
      case .backendNotReported:
        "Check the original tool report for evidence that an external backend ran."
      case .backendVersionNotRecorded:
        "Identify the external backend version and any separately configured preferences."
      case .planningModelNotRecorded:
        "Check the original planning environment for the model identifier."
      case .planningReportedModelNotRecorded:
        "Check the original provider response for the model that actually served the request."
      case .planningConsentNotRecorded:
        "Review and authorize a new cloud request using its own provider and data scope."
      case .furtherConsentEvidenceRequired:
        "Review the capability and obtain any required approval before a new execution."
      }
    }
  }

  struct ReproductionRequirement: Codable, Sendable {
    let limit: Limit
    let guidance: String
  }

  let schemaVersion: Int
  let jobID: UUID
  let appVersion: String?
  let appBuild: String?
  let hostMacOSVersion: String?
  let tool: Tool
  let status: JobStatus
  let exitCode: Int32?
  let startedAt: Date?
  let finishedAt: Date?
  let outputRootConfirmationUsed: Bool
  let runtime: RunRuntimeEvidence?
  let command: RunCommandEvidence?
  let reportedToolContractVersion: String?
  let reportedBackend: RunBackendEvidence?
  let approvals: [RunApproval]?
  let declaredPlanSource: AgentPlanSource?
  let planningEvidence: WorkflowPlanningEvidence?
  let inputs: [Input]
  let outputs: [Output]
  let limits: [Limit]
  let reproductionRequirements: [ReproductionRequirement]?
}

struct RunProvenanceService {
  static func toolIdentity(capability: CapabilityEntry, skillRoot: String, secrets: [String]) -> JobRunProvenance.Tool {
    let owner = FilesystemPath.canonicalURL(capability.resolvedSkillRoot(fallback: skillRoot))
    let entryPoint = owner.appendingPathComponent(capability.script)
    let implementation = owner.appendingPathComponent("fixtures", isDirectory: true)
      .appendingPathComponent(entryPoint.lastPathComponent)
    return .init(
      capabilityID: safeIdentifier(capability.id, secrets: secrets),
      skillRole: capability.owningSkillRole.flatMap(SkillRootRole.init(rawValue:)),
      registryDeclaredRelease: publicVersion(capability.registryDeclaredRelease, secrets: secrets),
      contractRevision: capability.ioContract?.revision,
      registrySHA256: capability.registryFingerprint.flatMap { value in
        value.utf8.count == 64 && value.utf8.allSatisfy(isHexDigit) ? value.lowercased() : nil
      },
      entryPointSHA256: digest(entryPoint, inside: owner),
      implementationSHA256: digest(implementation, inside: owner)
    )
  }

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
    fileprivate let commandSHA256: String?
    fileprivate let runLocations: [URL: String]
    fileprivate let approvals: [RunApproval]
    fileprivate let missingCapabilityApproval: Bool
    fileprivate let declaredPlanSource: AgentPlanSource?
    fileprivate let planningEvidence: WorkflowPlanningEvidence?
    fileprivate let secrets: [String]
    let runtimeChannel: RunRuntimeEvidence.Channel
  }

  func captureStart(
    request: RunRequest, capability: CapabilityEntry, skillRoot: String,
    outputRootConfirmationUsed: Bool, secrets: [String], command: ProcessCommand? = nil,
    appliedApproval: RunApproval? = nil, declaredPlanSource: AgentPlanSource? = nil,
    planningEvidence: WorkflowPlanningEvidence? = nil
  ) async -> Start {
    await Task.detached(priority: .utility) {
      let tool = Self.toolIdentity(capability: capability, skillRoot: skillRoot, secrets: secrets)
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
      let appVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
      let appBuild = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
      return Start(
        inputPaths: request.inputPaths,
        inputURLs: inputURLs,
        fingerprints: Self.fingerprints(inputURLs),
        runRoot: runRoot,
        tool: tool,
        appVersion: Self.publicVersion(appVersion, secrets: secrets),
        appBuild: Self.publicVersion(appBuild, secrets: secrets),
        outputRootConfirmationUsed: outputRootConfirmationUsed,
        command: capturedCommand?.evidence,
        commandSHA256: command.flatMap { RunExecutionEvidence.commandDigest($0, secrets: secrets) },
        runLocations: capturedCommand?.runLocations ?? [:],
        approvals: approvals.compactMap { $0 },
        missingCapabilityApproval: capability.requiresPlannerConfirmation && !isPreflight && appliedApproval == nil,
        declaredPlanSource: declaredPlanSource,
        planningEvidence: planningEvidence?.sanitized(secrets: secrets),
        secrets: secrets,
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

    let inputURLs = Set(start.inputURLs + updatedURLs)
    let inputDirectories = zip(start.inputURLs, start.fingerprints).compactMap { url, digest in
      digest.state == .directory ? url : nil
    }
    let sortedOutputs = Self.retainedOutputFiles(for: job, excluding: inputURLs, attachedDirectories: inputDirectories)
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
    let report = reportedTool.flatMap { expectedTool in
      let candidate = Self.commandSummary(start: start, root: root) ?? envelope
      return candidate?.tool == expectedTool ? candidate : nil
    }
    let backend = checksOnly ? nil : report?.reportedBackend
    let reportedToolContractVersion = Self.publicVersion(report?.contractVersion, secrets: start.secrets)
    var limits: [JobRunProvenance.Limit] = [.attachedInputScope, .fileContentsNotIncluded]
    if job.status != .succeeded { limits.append(.unsuccessfulRun) }
    if start.appVersion == nil || start.appBuild == nil { limits.append(.appIdentityNotRecorded) }
    if start.tool.registryDeclaredRelease == nil { limits.append(.skillReleaseNotRecorded) }
    if start.tool.registrySHA256 == nil || start.tool.entryPointSHA256 == nil {
      limits.append(.skillCodeIdentityIncomplete)
    }
    if backend == nil, !checksOnly, let reportedTool, RunBackendEvidence.tracks(reportedTool) {
      limits.append(.backendNotReported)
    }
    if backend != nil { limits.append(.backendVersionNotRecorded) }
    if let evidence = start.planningEvidence {
      if evidence.requestedModel == nil && evidence.reportedModel == nil { limits.append(.planningModelNotRecorded) }
      if evidence.outcome == .usedForPlan && evidence.reportedModel == nil {
        limits.append(.planningReportedModelNotRecorded)
      }
      if evidence.provider.requiresAPIKey && evidence.consent == nil { limits.append(.planningConsentNotRecorded) }
    } else if let source = start.declaredPlanSource, source != .local && source != .skillRouter {
      limits.append(.planningModelNotRecorded)
      if source != .ollama { limits.append(.planningConsentNotRecorded) }
    }
    if start.missingCapabilityApproval { limits.append(.furtherConsentEvidenceRequired) }
    if let command = start.command {
      if command.requiresLocalArguments { limits.append(.localArgumentsRequired) }
    } else {
      limits.append(.commandNotRecorded)
    }
    limits.append(runtime == nil ? .runtimeAndDependencyVersionsNotCaptured : .runtimeInventoryPartial)
    if fingerprints.contains(where: { $0.state == .directory }) { limits.append(.directoryContentsNotCaptured) }
    if fingerprints.contains(where: { $0.state != .recorded }) { limits.append(.incompleteFingerprints) }
    if inputs.contains(where: { $0.contentUnchanged == false }) { limits.append(.inputContentChanged) }

    let host = ProcessInfo.processInfo.operatingSystemVersion
    let hostVersion = "\(host.majorVersion).\(host.minorVersion).\(host.patchVersion)"
    let provenance = JobRunProvenance(
      schemaVersion: 1, jobID: job.id, appVersion: start.appVersion, appBuild: start.appBuild,
      hostMacOSVersion: Self.publicVersion(hostVersion, secrets: start.secrets),
      tool: start.tool, status: job.status, exitCode: job.exitCode, startedAt: job.startedAt,
      finishedAt: job.finishedAt, outputRootConfirmationUsed: start.outputRootConfirmationUsed, runtime: runtime?.shareable,
      command: start.command, reportedToolContractVersion: reportedToolContractVersion,
      reportedBackend: backend, approvals: start.approvals,
      declaredPlanSource: start.declaredPlanSource, planningEvidence: start.planningEvidence,
      inputs: inputs, outputs: outputs, limits: limits,
      reproductionRequirements: limits.map { .init(limit: $0, guidance: $0.guidance) }
    )
    let data = try JSONEncoder.scientificWorkbench.encode(provenance)
    let destination = root.appendingPathComponent(JobRunProvenance.filename)
    let staging = root.appendingPathComponent(".run-provenance-\(UUID().uuidString).tmp")
    try data.write(to: staging, options: .withoutOverwriting)
    defer { try? FileManager.default.removeItem(at: staging) }
    try FileManager.default.moveItem(at: staging, to: destination)
    if job.status == .succeeded, let commandHash = start.commandSHA256, let inventory = runtime?.inventorySHA256 {
      // Private replay evidence supplements provenance. Its absence does not invalidate retained artifacts.
      try? RunExecutionEvidence.retain(jobID: job.id, root: root, command: commandHash, pythonInventory: inventory)
    }
    return Artifact(path: destination.path, relativePath: JobRunProvenance.filename,
                    byteCount: Int64(data.count), artifactType: "metadata_json")
  }

  static func fingerprints(_ urls: [URL?]) -> [RunFileFingerprint] {
    // Each pass has its own budget so a large input cannot hide the outputs.
    var remaining = RunFileFingerprint.defaultReadBudget
    return urls.map { url in
      guard let url else { return RunFileFingerprint(state: .changed, byteCount: nil, sha256: nil) }
      let digest = RunFileFingerprint.read(url, maximumBytes: remaining)
      if let size = digest.byteCount, size >= 0, size <= remaining { remaining -= size }
      return digest
    }
  }

  static func retainedOutputFiles(
    for job: JobRecord, excluding inputs: Set<URL>, attachedDirectories: [URL]
  ) -> [URL] {
    let root = FilesystemPath.canonicalURL(job.runDirectory)
    let stagedInputs = root.appendingPathComponent("inputs", isDirectory: true)
    return Set(job.artifacts.map { FilesystemPath.canonicalURL($0.path) }).filter { url in
      isInside(url, root: root) && !isInside(url, root: stagedInputs)
        && url != root.appendingPathComponent(JobRunProvenance.filename)
        && url != root.appendingPathComponent(RunExecutionEvidence.filename)
        && !inputs.contains(url) && !attachedDirectories.contains { isInside(url, root: $0) }
    }.sorted { $0.path < $1.path }
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

  private static func publicVersion(_ value: String?, secrets: [String]) -> String? {
    guard let value, value.range(of: #"\Av?[0-9]{1,5}(?:\.[0-9]{1,5}){0,3}\z"#, options: .regularExpression) != nil,
          !secrets.contains(where: { !$0.isEmpty && value.contains($0) }) else { return nil }
    return value
  }

  private static func isHexDigit(_ byte: UInt8) -> Bool {
    (48...57).contains(byte) || (65...70).contains(byte) || (97...102).contains(byte)
  }
}
